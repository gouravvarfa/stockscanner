"""
Orchestrates the Top-Bottom Futures Backtesting module: resolves the
futures contract, fetches its real Angel One historical candles ONCE,
clips to the requested date range, runs the pure backtest engine, and
caches the finished result in-process so the GET endpoints (trades/equity/
export) can serve it back without recomputing or re-fetching.

Completely independent of scan_service.py / universe_loader.py — this
module never touches the NSE cash/A-Group universe or any existing
strategy's data path.
"""
from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass

import pandas as pd

from backend.config.cup_config import DEFAULT_CUP_CONFIG
from backend.indicators.resample import resample_ohlcv
from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.angelone_scrip_master import FutureContract
from backend.providers.cup_history import _fetch_chunked
from backend.services import equity_instrument_service as equity_service
from backend.services import futures_instrument_service as futures_service
from backend.services.equity_instrument_service import NotAnAGroupEquityError
from backend.services.futures_instrument_service import NotAFutureError
from backend.strategies.top_bottom.models import BacktestResult, InstrumentClass
from backend.strategies.top_bottom.strategy import run_backtest

_NATIVE_INTERVAL = {
    "1m": "ONE_MINUTE",
    "5m": "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE",
    "1H": "ONE_HOUR",
    "1D": "ONE_DAY",
}
_AGGREGATE_FROM = {
    "4H": ("ONE_HOUR", "4h"),
    "1W": ("ONE_DAY", "W-FRI"),
}
VALID_TIMEFRAMES = set(_NATIVE_INTERVAL) | set(_AGGREGATE_FROM)

# Generous enough to cover a multi-year request; the actual usable range is
# whatever Angel One genuinely returns for that specific contract token —
# never padded or assumed beyond that (see DataCoverage in models.py).
_LOOKBACK_DAYS = {
    "1m": 5, "5m": 10, "15m": 20, "30m": 40, "1H": 400,
    "4H": 800, "1D": 1500, "1W": 1500,
}


class TopBottomValidationError(ValueError):
    """A request-shape problem (bad instrument type, bad timeframe, bad
    date range) — always a 4xx at the API layer, never a 500."""


class InsufficientDataError(RuntimeError):
    """Angel One returned no usable candles for this contract/date range at
    all — never silently swapped for fabricated data."""


# In-process result store — a backtest is comparatively expensive (a real
# Angel One fetch + a full event-loop simulation), so GET .../trades,
# .../equity and .../export all read the SAME already-computed result
# rather than re-running anything. Cleared on process restart; this module
# has no requirement to persist backtests across restarts.
_results: dict[str, BacktestResult] = {}
_results_lock = threading.Lock()


def _instrument_class(contract: FutureContract) -> InstrumentClass:
    return "INDEX" if contract.is_index else "STOCK"


@dataclass(frozen=True)
class ResolvedInstrument:
    """One uniform shape the engine is driven from, whichever segment the
    user picked — so the Top-Bottom state machine itself stays completely
    unaware of equity-vs-futures."""
    underlying: str
    trading_symbol: str
    token: str
    exch_seg: str
    expiry: str  # "" for cash equity (no expiry)
    instrument_class: InstrumentClass
    lot_size: int  # 1 for cash equity (P&L per share); real exchange lot size for futures


async def _resolve_instrument(symbol: str, instrument_type: str, expiry: str | None) -> ResolvedInstrument:
    if instrument_type == "EQUITY":
        # Restricted to the A Group universe (the same list the main
        # scanner uses), and must also resolve to a real NSE cash listing.
        try:
            equity = await equity_service.resolve_equity(symbol)
        except NotAnAGroupEquityError as exc:
            raise TopBottomValidationError(str(exc)) from exc
        return ResolvedInstrument(
            underlying=equity.symbol,
            trading_symbol=equity.trading_symbol,
            token=equity.token,
            exch_seg=equity.exch_seg,
            expiry="",
            instrument_class="STOCK",
            lot_size=1,  # cash equity trades in single shares — not a guessed multiplier
        )

    if instrument_type == "FUTURES":
        try:
            contract = await futures_service.resolve_contract(symbol, expiry)
        except NotAFutureError as exc:
            raise TopBottomValidationError(str(exc)) from exc
        return ResolvedInstrument(
            underlying=contract.underlying,
            trading_symbol=contract.trading_symbol,
            token=contract.token,
            exch_seg=contract.exch_seg,
            expiry=contract.expiry,
            instrument_class=_instrument_class(contract),
            lot_size=contract.lot_size,
        )

    raise TopBottomValidationError(
        f"Unsupported instrument_type '{instrument_type}'. Must be 'EQUITY' or 'FUTURES'."
    )


# A single Angel One ONE_DAY call reliably returns this much history
# without silently truncating — this is the pre-existing _LOOKBACK_DAYS
# default itself, already proven safe everywhere else in this app,
# deliberately NOT lowered here (a lower threshold would start chunking —
# and paying its per-chunk delay — for every ordinary request, not just
# the genuinely-longer ones this change is for). Beyond it, use the same
# chunked date-range fetch (backend/providers/cup_history.py) Cup's own
# 10-year history uses, instead of duplicating that chunking logic here.
_SAFE_SINGLE_CALL_DAYS = _LOOKBACK_DAYS["1D"]


async def _fetch_ohlcv(
    angelone: AngelOneProvider, instrument: ResolvedInstrument, timeframe: str, from_date: dt.datetime | None = None,
) -> pd.DataFrame:
    """
    `from_date` (the requested backtest start) is optional so every existing
    caller/test keeps working unchanged. When given, and the requested range
    reaches further back than `_LOOKBACK_DAYS[timeframe]` (e.g. a backtest
    starting before ~2022 — per explicit user direction, 2026-09-24, "purana
    data ho tab bhi poora backtesting chalna chahiye"), the needed lookback
    grows to actually cover it, chunked-fetching instead of a single call
    once that exceeds what one call reliably returns.
    """
    if timeframe not in VALID_TIMEFRAMES:
        raise TopBottomValidationError(f"Unsupported timeframe '{timeframe}'. Must be one of {sorted(VALID_TIMEFRAMES)}.")

    days = _LOOKBACK_DAYS[timeframe]
    if timeframe in ("1D", "1W") and from_date is not None:
        now = dt.datetime.now()
        days = max(days, (now - from_date).days + 5)

    async def _fetch_daily_base(days_needed: int) -> pd.DataFrame:
        if days_needed > _SAFE_SINGLE_CALL_DAYS:
            now = dt.datetime.now()
            return await _fetch_chunked(
                angelone, instrument.exch_seg, instrument.token, now - dt.timedelta(days=days_needed), now, DEFAULT_CUP_CONFIG,
            )
        return await angelone.get_intraday_ohlc(instrument.exch_seg, instrument.token, "ONE_DAY", days_needed)

    if timeframe in _NATIVE_INTERVAL:
        if timeframe == "1D":
            return await _fetch_daily_base(days)
        return await angelone.get_intraday_ohlc(instrument.exch_seg, instrument.token, _NATIVE_INTERVAL[timeframe], days)

    base_interval, rule = _AGGREGATE_FROM[timeframe]
    base_bars = await _fetch_daily_base(days) if timeframe == "1W" else await angelone.get_intraday_ohlc(
        instrument.exch_seg, instrument.token, base_interval, days
    )
    if base_bars.empty:
        return base_bars
    resampled = resample_ohlcv(base_bars, rule)
    return resampled.dropna(subset=["open", "high", "low", "close"])


async def run_futures_backtest(
    angelone: AngelOneProvider,
    symbol: str,
    instrument_type: str,
    timeframe: str,
    from_date: dt.datetime,
    to_date: dt.datetime,
    expiry: str | None = None,
    starting_capital: float = 100.0,
) -> BacktestResult:
    if from_date > to_date:
        raise TopBottomValidationError("from_date must not be after to_date.")

    instrument = await _resolve_instrument(symbol.strip().upper(), instrument_type, expiry)

    ohlcv = await _fetch_ohlcv(angelone, instrument, timeframe, from_date)
    if ohlcv.empty:
        raise InsufficientDataError(
            f"Historical data unavailable for {instrument.trading_symbol}/{timeframe}."
        )
    if ohlcv.index[-1] < from_date or ohlcv.index[0] > to_date:
        raise InsufficientDataError(
            f"Insufficient historical data for the selected symbol/date range. "
            f"{instrument.trading_symbol} data is only available from "
            f"{ohlcv.index[0].date()} to {ohlcv.index[-1].date()}."
        )

    # Clipped to EXACTLY the requested window — per explicit user direction,
    # the backtest starts FLAT at from_date and structure detection never
    # uses any bar before it. No warm-up from earlier history, and no
    # position can be "already open" carried in from before the selected
    # range (this used to happen: a trade opened before from_date, using
    # full history as context, would show as already-in-progress at the
    # start of the reported window).
    windowed = ohlcv.loc[(ohlcv.index >= from_date) & (ohlcv.index <= to_date)]
    if windowed.empty:
        raise InsufficientDataError(
            f"Insufficient historical data for the selected symbol/date range. "
            f"{instrument.trading_symbol} data is only available from "
            f"{ohlcv.index[0].date()} to {ohlcv.index[-1].date()}."
        )
    dates = list(windowed.index.to_pydatetime())
    closes = windowed["close"].tolist()
    opens = windowed["open"].tolist()

    result = run_backtest(
        symbol=instrument.underlying,
        trading_symbol=instrument.trading_symbol,
        expiry=instrument.expiry,
        instrument_class=instrument.instrument_class,
        lot_size=instrument.lot_size,
        exch_seg=instrument.exch_seg,
        timeframe=timeframe,
        dates=dates,
        closes=closes,
        opens=opens,
        requested_from=from_date,
        requested_to=to_date,
        starting_capital=starting_capital,
        data_available_from=ohlcv.index[0].to_pydatetime(),
        data_available_to=ohlcv.index[-1].to_pydatetime(),
    )

    with _results_lock:
        _results[result.backtest_id] = result
    return result


def get_result(backtest_id: str) -> BacktestResult | None:
    with _results_lock:
        return _results.get(backtest_id)

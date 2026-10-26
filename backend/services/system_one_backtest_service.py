"""
Runs the System One trade backtest (backend/strategies/system_one_backtest.py)
for one A Group stock: resolves the NSE listing, fetches its Angel One daily
candles ONCE, rolls them up to completed weekly candles, runs the pure
engine, and keeps the finished result in memory so the export endpoint
serves exactly what the UI showed.

Reuses the Top-Bottom module's instrument resolution and weekly fetch rather
than duplicating Angel One plumbing; it does not touch scan_service or any
other strategy's data path.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import threading
import uuid
from collections import OrderedDict

from backend.config.strategy_config import DEFAULT_SYSTEM_ONE_BACKTEST_CONFIG, SystemOneBacktestConfig
from backend.providers.angelone_provider import AngelOneProvider
from backend.services.top_bottom_backtest_service import (
    InsufficientDataError,
    TopBottomValidationError,
    _fetch_ohlcv,
    _resolve_instrument,
)
from backend.strategies.system_one_backtest import SystemOneBacktestResult, run_system_one_backtest

TIMEFRAME = "1W"

# RSI(14) and the 20 SMA need earlier candles to be meaningful on the first
# day of the requested window; ~58 weeks of warm-up is fetched before it.
_WARMUP_DAYS = 400

_MAX_STORED_RESULTS = 50

PNL_NOTE = (
    "P&L is gross: before brokerage, taxes, slippage and other transaction costs. "
    "Open trades have no exit and no realised P&L."
)


@dataclasses.dataclass
class StoredSystemOneBacktest:
    backtest_id: str
    symbol: str
    trading_symbol: str
    timeframe: str
    from_date: dt.datetime
    to_date: dt.datetime
    data_available_from: dt.datetime
    data_available_to: dt.datetime
    config: SystemOneBacktestConfig
    created_at: dt.datetime
    result: SystemOneBacktestResult


_results: "OrderedDict[str, StoredSystemOneBacktest]" = OrderedDict()
_results_lock = threading.Lock()


def _store(item: StoredSystemOneBacktest) -> None:
    with _results_lock:
        _results[item.backtest_id] = item
        while len(_results) > _MAX_STORED_RESULTS:
            _results.popitem(last=False)


def get_result(backtest_id: str) -> StoredSystemOneBacktest | None:
    with _results_lock:
        return _results.get(backtest_id)


async def run_for_symbol(
    angelone: AngelOneProvider,
    symbol: str,
    from_date: dt.datetime,
    to_date: dt.datetime,
    config: SystemOneBacktestConfig = DEFAULT_SYSTEM_ONE_BACKTEST_CONFIG,
) -> StoredSystemOneBacktest:
    if from_date > to_date:
        raise TopBottomValidationError("from_date must not be after to_date.")

    instrument = await _resolve_instrument(symbol.strip().upper(), "EQUITY", None)

    weekly = await _fetch_ohlcv(angelone, instrument, TIMEFRAME, from_date - dt.timedelta(days=_WARMUP_DAYS))
    if weekly.empty:
        raise InsufficientDataError(f"Historical data unavailable for {instrument.trading_symbol}.")
    if weekly.index[-1] < from_date or weekly.index[0] > to_date:
        raise InsufficientDataError(
            f"Insufficient historical data for the selected date range. {instrument.trading_symbol} data is only "
            f"available from {weekly.index[0].date()} to {weekly.index[-1].date()}."
        )

    result = run_system_one_backtest(weekly, config, from_date=from_date, to_date=to_date)
    stored = StoredSystemOneBacktest(
        backtest_id=uuid.uuid4().hex,
        symbol=instrument.underlying,
        trading_symbol=instrument.trading_symbol,
        timeframe=TIMEFRAME,
        from_date=from_date,
        to_date=to_date,
        data_available_from=weekly.index[0].to_pydatetime(),
        data_available_to=weekly.index[-1].to_pydatetime(),
        config=config,
        created_at=dt.datetime.utcnow(),
        result=result,
    )
    _store(stored)
    return stored

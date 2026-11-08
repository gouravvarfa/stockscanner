"""
Runs the GFS trade backtest (backend/strategies/gfs_backtest.py) for one A Group
stock on DAILY candles. Weekly and monthly RSI are derived from those same daily
candles inside the engine, so one fetch is enough.

Reuses the System One service's stored-result shape and the Top-Bottom module's
instrument resolution / candle fetch; it touches no other strategy's data path.
"""
from __future__ import annotations

import datetime as dt
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from backend.config.strategy_config import DEFAULT_GFS_BACKTEST_CONFIG, GFSBacktestConfig
from backend.providers.angelone_provider import AngelOneProvider
from backend.services.gfs_universe_service import backtest_priority
from backend.services.system_one_backtest_service import PNL_NOTE, StoredSystemOneBacktest, _store
from backend.services.top_bottom_backtest_service import (
    InsufficientDataError,
    TopBottomValidationError,
    _fetch_ohlcv,
    _resolve_instrument,
)
from backend.strategies.gfs_backtest import run_gfs_backtest
from backend.strategies.system_one_backtest import SystemOneBacktestResult

BacktestRunner = Callable[..., SystemOneBacktestResult]

TIMEFRAME = "1D"

# Monthly RSI(14) needs years of monthly bars before it means anything, so the
# daily fetch reaches well before the requested start.
_WARMUP_DAYS = 1500

_COVERAGE_SLACK = dt.timedelta(days=7)

__all__ = ["PNL_NOTE", "run_for_symbol", "export_response"]

# Fetching ~10 years of daily candles takes ~25s (Angel One needs the request split into
# chunks 3s apart), so a fetched stock is remembered for a short while: re-running or
# changing dates, or opening a stock from the All Stocks list again, is then instant.
# Short TTL, because the latest daily candle changes while the market is open.
_CANDLE_CACHE_TTL = dt.timedelta(minutes=15)
_CANDLE_CACHE_MAX = 40


@dataclass
class _CachedCandles:
    instrument: object
    candles: pd.DataFrame
    fetched_from: dt.datetime  # the start that was requested (the stock may list later than this)
    fetched_at: dt.datetime

    def covers(self, need_from: dt.datetime) -> bool:
        return dt.datetime.now() - self.fetched_at < _CANDLE_CACHE_TTL and self.fetched_from <= need_from


_candle_cache: "OrderedDict[str, _CachedCandles]" = OrderedDict()


async def run_for_symbol(
    angelone: AngelOneProvider,
    symbol: str,
    from_date: dt.datetime,
    to_date: dt.datetime,
    config: GFSBacktestConfig = DEFAULT_GFS_BACKTEST_CONFIG,
    runner: BacktestRunner = run_gfs_backtest,
) -> StoredSystemOneBacktest:
    if from_date > to_date:
        raise TopBottomValidationError("from_date must not be after to_date.")

    key = symbol.strip().upper()
    need_from = from_date - dt.timedelta(days=_WARMUP_DAYS)
    cached = _candle_cache.get(key)
    if cached is not None and cached.covers(need_from):
        instrument, candles = cached.instrument, cached.candles.copy()
    else:
        # The all-stocks scan shares Angel One's rate limit; it pauses while this fetch runs.
        with backtest_priority():
            instrument = await _resolve_instrument(key, "EQUITY", None)
            candles = await _fetch_ohlcv(angelone, instrument, TIMEFRAME, need_from)
        if not candles.empty:
            _candle_cache[key] = _CachedCandles(instrument, candles.copy(), need_from, dt.datetime.now())
            _candle_cache.move_to_end(key)
            while len(_candle_cache) > _CANDLE_CACHE_MAX:
                _candle_cache.popitem(last=False)
    if candles.empty:
        raise InsufficientDataError(f"Historical data unavailable for {instrument.trading_symbol}.")
    if candles.index[-1] < from_date or candles.index[0] > to_date:
        raise InsufficientDataError(
            f"Insufficient historical data for the selected date range. {instrument.trading_symbol} data is only "
            f"available from {candles.index[0].date()} to {candles.index[-1].date()}."
        )

    result = runner(candles, config, from_date=from_date, to_date=to_date)
    if candles.index[0] > from_date + _COVERAGE_SLACK:
        result.warnings.append(
            f"Daily data is only available from {candles.index[0].date()}, so the backtest starts there, "
            f"not on the requested {from_date.date()}."
        )
    stored = StoredSystemOneBacktest(
        backtest_id=uuid.uuid4().hex,
        symbol=instrument.underlying,
        trading_symbol=instrument.trading_symbol,
        timeframe=TIMEFRAME,
        from_date=from_date,
        to_date=to_date,
        data_available_from=candles.index[0].to_pydatetime(),
        data_available_to=candles.index[-1].to_pydatetime(),
        config=config,
        created_at=dt.datetime.utcnow(),
        result=result,
    )
    _store(stored)  # kept in memory so the Excel export serves exactly what the UI showed
    return stored


def export_response(backtest_id: str, strategy: str, file_prefix: str):
    """Excel download for a stored GFS-family backtest (shared by GFS / Advanced GFS / 50 GFS)."""
    from fastapi import HTTPException, Response

    from backend.services import system_one_backtest_service as so_service
    from backend.services import system_one_excel_export as excel_export

    stored = so_service.get_result(backtest_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Backtest not found (it may have been cleared by a backend restart).")
    return Response(
        content=excel_export.build_excel(stored, strategy=strategy),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{excel_export.file_name(stored, file_prefix)}"'},
    )

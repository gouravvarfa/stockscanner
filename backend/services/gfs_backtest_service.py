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
from collections.abc import Callable

from backend.config.strategy_config import DEFAULT_GFS_BACKTEST_CONFIG, GFSBacktestConfig
from backend.providers.angelone_provider import AngelOneProvider
from backend.services.system_one_backtest_service import PNL_NOTE, StoredSystemOneBacktest
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

__all__ = ["PNL_NOTE", "run_for_symbol"]


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

    instrument = await _resolve_instrument(symbol.strip().upper(), "EQUITY", None)

    candles = await _fetch_ohlcv(angelone, instrument, TIMEFRAME, from_date - dt.timedelta(days=_WARMUP_DAYS))
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
    return StoredSystemOneBacktest(
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

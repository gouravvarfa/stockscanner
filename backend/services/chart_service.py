"""
Chart datafeed adapter: Frontend (lightweight-charts) -> this module ->
the existing AngelOneProvider -> real Angel One market data. Angel One
remains the only market-data source; no second provider is introduced.

Timeframes with no native Angel One interval (4H/1W/1M) are built by
resampling real fetched bars (backend/indicators/resample.py — the same
resampling already used by the main scan pipeline for weekly/monthly RSI).
Never fabricates candles: a resampled timeframe is only ever built from
bars Angel One actually returned, and an in-progress trailing period is
dropped rather than shown as if it were a completed bar.
"""
from __future__ import annotations

import pandas as pd

from backend.indicators.resample import resample_ohlcv
from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.market_data_router import DataUnavailableError

# Timeframes Angel One's historical-candle endpoint supports natively.
_NATIVE_INTERVAL = {
    "1m": "ONE_MINUTE",
    "5m": "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE",
    "1H": "ONE_HOUR",
    "1D": "ONE_DAY",
}

# Timeframes built by resampling a native base interval's real bars.
_AGGREGATE_FROM = {
    "4H": ("ONE_HOUR", "4h"),
    "1W": ("ONE_DAY", "W-FRI"),
    "1M": ("ONE_DAY", "ME"),
}

VALID_TIMEFRAMES = set(_NATIVE_INTERVAL) | set(_AGGREGATE_FROM)

# How many calendar days of history to request per timeframe — generous
# enough for a useful chart without requesting more than Angel One is
# likely to actually hold for intraday granularities.
_LOOKBACK_DAYS = {
    "1m": 5, "5m": 10, "15m": 20, "30m": 40, "1H": 90,
    "4H": 180, "1D": 800, "1W": 800, "1M": 1500,
}


class ChartUnsupportedTimeframeError(RuntimeError):
    pass


async def get_candles(angelone: AngelOneProvider, symbol: str, timeframe: str) -> pd.DataFrame:
    if timeframe not in VALID_TIMEFRAMES:
        raise ChartUnsupportedTimeframeError(
            f"Unsupported timeframe '{timeframe}'. Must be one of {sorted(VALID_TIMEFRAMES)}."
        )

    match = await angelone.resolve_equity(symbol)
    if match is None:
        raise DataUnavailableError(f"Angel One has no equity listing for '{symbol}'.")

    days = _LOOKBACK_DAYS[timeframe]

    if timeframe in _NATIVE_INTERVAL:
        return await angelone.get_intraday_ohlc(match.exch_seg, match.token, _NATIVE_INTERVAL[timeframe], days)

    base_interval, rule = _AGGREGATE_FROM[timeframe]
    base_bars = await angelone.get_intraday_ohlc(match.exch_seg, match.token, base_interval, days)
    if base_bars.empty:
        return base_bars

    resampled = resample_ohlcv(base_bars, rule)
    # resample_ohlcv only drops a bucket when EVERY column is NaN, but a
    # calendar-fixed bucket (e.g. "4h") that falls entirely outside market
    # hours/on a non-trading day still gets a real volume SUM of 0 (not
    # NaN) while open/high/low/close are NaN — that row must still be
    # dropped rather than shown as a null/fabricated candle.
    return resampled.dropna(subset=["open", "high", "low", "close"])

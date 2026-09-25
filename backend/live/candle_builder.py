"""
Pure tick -> multi-timeframe candle aggregation for the live market-data
engine. No Angel One / WebSocket code here on purpose — this module only
knows how to fold a (timestamp, price, cumulative_day_volume) tick into
15m/1H/1D/1W/1M candles, so it can be unit-tested deterministically and
reused unchanged regardless of transport.

Bucket keys are computed the SAME way backend/indicators/resample.py
labels its historical candles (label="right": a period's key is its own
end — e.g. a monthly candle's key is that month's last calendar day,
exactly like to_monthly()'s row index) so a live candle and a historical
one for the same period always agree on identity: no duplicate, no gap
when a chart's series is historical-then-live.

Memory is bounded on purpose (2026-09-25 spec, after this project's real
Render OOM incidents): only the CURRENT candle plus a small, fixed-size
rolling history (`history_maxlen`) are ever kept per timeframe per
symbol — raw ticks are never retained past the single on_tick() call that
folds them into the current candle.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

Timeframe = Literal["15m", "1H", "1D", "1W", "1M"]

ALL_TIMEFRAMES: tuple[Timeframe, ...] = ("15m", "1H", "1D", "1W", "1M")

_INTRADAY_FREQ: dict[Timeframe, str] = {"15m": "15min", "1H": "1h"}


@dataclass
class LiveCandle:
    period_key: pd.Timestamp  # identity — matches the historical resample's row label exactly
    period_start: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float
    complete: bool = False

    def as_dict(self) -> dict:
        return {
            "time": int(self.period_key.timestamp()),
            "open": self.open, "high": self.high, "low": self.low, "close": self.close,
            "volume": self.volume, "complete": self.complete,
        }


def bucket_key(timeframe: Timeframe, ts: pd.Timestamp) -> pd.Timestamp:
    """The period identity `ts` falls into, for `timeframe` — see module
    docstring for why this must match backend/indicators/resample.py's
    "label=right" convention exactly."""
    ts = pd.Timestamp(ts)
    if ts.tzinfo is not None:
        # Historical candles (backend/indicators/resample.py) are always
        # tz-naive IST wall-clock timestamps; live ticks arrive tz-aware
        # (Asia/Kolkata) — stripping tz here (not converting) keeps both
        # sides' bucket keys identical for the same wall-clock moment.
        ts = ts.tz_localize(None)
    if timeframe in _INTRADAY_FREQ:
        return ts.ceil(_INTRADAY_FREQ[timeframe])
    if timeframe == "1D":
        return ts.normalize()
    if timeframe == "1W":
        return ts.to_period("W-FRI").end_time.normalize()
    if timeframe == "1M":
        return (ts + pd.offsets.MonthEnd(0)).normalize()
    raise ValueError(f"Unknown timeframe {timeframe!r}")


class CandleBuilder:
    """Builds ONE timeframe's live candle series from a tick stream for a
    single symbol. `history_maxlen` bounds memory — this is a live-display
    aid, not a source of historical truth (that remains the existing
    Angel One historical fetch + resample pipeline)."""

    def __init__(self, timeframe: Timeframe, history_maxlen: int = 5):
        self.timeframe = timeframe
        self._current: LiveCandle | None = None
        self._history: deque[LiveCandle] = deque(maxlen=history_maxlen)
        self._last_cumulative_volume: float | None = None

    def on_tick(self, ts: pd.Timestamp, price: float, cumulative_day_volume: float | None = None) -> LiveCandle:
        ts = pd.Timestamp(ts)
        key = bucket_key(self.timeframe, ts)

        volume_delta = 0.0
        if cumulative_day_volume is not None:
            if self._last_cumulative_volume is None or cumulative_day_volume < self._last_cumulative_volume:
                # First tick, or a new trading day's cumulative counter reset —
                # this tick's own cumulative value is what this candle has seen so far.
                volume_delta = cumulative_day_volume
            else:
                volume_delta = cumulative_day_volume - self._last_cumulative_volume
            self._last_cumulative_volume = cumulative_day_volume

        if self._current is None or self._current.period_key != key:
            if self._current is not None:
                self._current.complete = True
                self._history.append(self._current)
            self._current = LiveCandle(
                period_key=key, period_start=ts, open=price, high=price, low=price, close=price,
                volume=max(volume_delta, 0.0),
            )
        else:
            c = self._current
            c.high = max(c.high, price)
            c.low = min(c.low, price)
            c.close = price
            c.volume += max(volume_delta, 0.0)
        return self._current

    def finalize_if_period_ended(self, now: pd.Timestamp) -> LiveCandle | None:
        """Called on the market-close/period-boundary tick (see
        market_data_service.py's finalize hooks) — marks the current
        candle complete WITHOUT waiting for the next tick to arrive (which
        may never come before the next trading session, e.g. at 15:30
        market close). Returns the finalized candle, or None if there was
        nothing to finalize."""
        if self._current is None:
            return None
        key = bucket_key(self.timeframe, now)
        if key != self._current.period_key:
            return None  # already rolled over naturally
        self._current.complete = True
        return self._current

    @property
    def current(self) -> LiveCandle | None:
        return self._current

    @property
    def history(self) -> list[LiveCandle]:
        return list(self._history)


@dataclass
class SymbolCandleSet:
    """All five live timeframes for one symbol, sharing the same tick
    stream (per spec: "Do not create another WebSocket connection for
    each timeframe" / "same live ticks")."""

    symbol: str
    builders: dict[Timeframe, CandleBuilder] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.builders:
            self.builders = {tf: CandleBuilder(tf) for tf in ALL_TIMEFRAMES}

    def on_tick(self, ts: pd.Timestamp, price: float, cumulative_day_volume: float | None = None) -> dict[Timeframe, LiveCandle]:
        return {tf: builder.on_tick(ts, price, cumulative_day_volume) for tf, builder in self.builders.items()}

    def finalize_at(self, now: pd.Timestamp, timeframes: tuple[Timeframe, ...] = ALL_TIMEFRAMES) -> dict[Timeframe, LiveCandle]:
        finalized = {}
        for tf in timeframes:
            candle = self.builders[tf].finalize_if_period_ended(now)
            if candle is not None:
                finalized[tf] = candle
        return finalized

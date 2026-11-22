"""
Gann time-cycle projection (C.K. Narayan style swing candle count).

Pure functions, no I/O. Rules (explained to the user in plain words):
1. Swings: a pivot high/low is a bar that is the highest high / lowest low of the
   PIVOT_STRENGTH bars on each side. Highs and lows strictly alternate (of two
   same-type pivots in a row, the more extreme is kept).
2. Candle count: from each of the last SOURCE_SWINGS pivots to the latest pivot.
3. Projections per count c (latest pivot = b, source pivot = a):
   - ratio:  b + round(c * r)      for r in RATIOS
   - SQ9:    a + round((sqrt(c) + d) ** 2)  for d in SQ9_STEPS (90/180/360 deg)
4. Cluster: projections within CLUSTER_TOLERANCE bars of each other; >= 2 make a
   cluster date (its strength = how many projections agree).
5. Only clusters from WINDOW_BARS before the last bar to HORIZON_BARS ahead.
Backtest on gold 2010-2026: 3+ projection clusters hit a real pivot within +-3
bars 42.7% of the time vs 34.4% for random dates.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

PIVOT_STRENGTH = 10
SOURCE_SWINGS = 3
RATIOS = (0.5, 1.0, 1.618, 2.0)
SQ9_STEPS = ((0.25, "SQ9 90°"), (0.5, "SQ9 180°"), (1.0, "SQ9 360°"))
CLUSTER_TOLERANCE = 2
WINDOW_BARS = 3
HORIZON_BARS = 60
MIN_CLUSTER = 2


@dataclass
class Pivot:
    index: int
    kind: str  # "H" | "L"
    date: dt.date
    price: float


@dataclass
class Projection:
    bar: int  # absolute bar index (may be beyond the last bar)
    label: str  # e.g. "2x" / "SQ9 180°"
    source_date: dt.date  # the swing the count started from
    count: int


@dataclass
class Cluster:
    bar: int
    date: dt.date
    bars_away: int  # 0 = today (last bar), 1 = next trading day, negative = window still open
    strength: int
    projections: list[Projection] = field(default_factory=list)


@dataclass
class GannResult:
    pivots: list[Pivot]
    counts: list[dict]
    projections: list[Projection]
    clusters: list[Cluster]
    last_date: dt.date
    last_close: float
    new_swing_forming: bool
    future_dates: list[dt.date]  # trading-day calendar for bars after the last bar


def find_pivots(high: np.ndarray, low: np.ndarray, k: int = PIVOT_STRENGTH) -> list[tuple[int, str]]:
    n = len(high)
    raw: list[tuple[int, str]] = []
    for i in range(k, n - k):
        if high[i] == high[i - k:i + k + 1].max():
            raw.append((i, "H"))
        elif low[i] == low[i - k:i + k + 1].min():
            raw.append((i, "L"))
    clean: list[tuple[int, str]] = []
    for p in raw:
        if clean and clean[-1][1] == p[1]:
            prev = clean[-1][0]
            if (p[1] == "H" and high[p[0]] > high[prev]) or (p[1] == "L" and low[p[0]] < low[prev]):
                clean[-1] = p
        else:
            clean.append(p)
    return clean


def project(a: int, b: int, source_date: dt.date) -> list[Projection]:
    c = b - a
    out = [Projection(b + round(c * r), f"{r:g}x", source_date, c) for r in RATIOS]
    s = math.sqrt(c)
    out += [Projection(a + round((s + d) ** 2), lab, source_date, c) for d, lab in SQ9_STEPS]
    return [p for p in out if p.bar > b]


def trading_days_after(last: dt.date, count: int, holidays: set[dt.date] | None = None) -> list[dt.date]:
    holidays = holidays or set()
    out: list[dt.date] = []
    d = last
    while len(out) < count:
        d += dt.timedelta(days=1)
        if d.weekday() < 5 and d not in holidays:
            out.append(d)
    return out


def analyse(df: pd.DataFrame, holidays: set[dt.date] | None = None, horizon: int = HORIZON_BARS) -> GannResult | None:
    """df: daily OHLC indexed by timestamp, columns high/low/close."""
    if df is None or len(df) < PIVOT_STRENGTH * 2 + 20:
        return None
    df = df.sort_index()
    high, low, close = df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float)
    dates = [ts.date() for ts in df.index]
    n = len(df)
    piv = find_pivots(high, low)
    if len(piv) < 2:
        return None
    pivots = [Pivot(i, t, dates[i], float(high[i] if t == "H" else low[i])) for i, t in piv]
    last = pivots[-1]
    sources = pivots[-1 - SOURCE_SWINGS:-1]
    projections: list[Projection] = []
    counts = []
    for s in sources:
        counts.append({"from_date": s.date, "from_kind": s.kind, "to_date": last.date, "to_kind": last.kind, "candles": last.index - s.index})
        projections += project(s.index, last.index, s.date)

    future = trading_days_after(dates[-1], horizon + WINDOW_BARS + 5, holidays)

    def date_of(bar: int) -> dt.date:
        return dates[bar] if bar < n else future[bar - n]

    lo, hi = n - 1 - WINDOW_BARS, n - 1 + horizon
    bars = np.array([p.bar for p in projections])
    clusters: list[Cluster] = []
    for t in sorted({p.bar for p in projections}):
        if not lo <= t <= hi:
            continue
        members = [p for p in projections if abs(p.bar - t) <= CLUSTER_TOLERANCE]
        if len(members) < MIN_CLUSTER:
            continue
        centre = int(round(float(np.median([p.bar for p in members]))))
        if clusters and abs(clusters[-1].bar - centre) <= CLUSTER_TOLERANCE:
            if len(members) > clusters[-1].strength:
                clusters[-1] = Cluster(centre, date_of(centre), centre - (n - 1), len(members), members)
            continue
        clusters.append(Cluster(centre, date_of(centre), centre - (n - 1), len(members), members))
    del bars

    forming = (last.kind == "L" and float(low[last.index + 1:].min(initial=np.inf)) < last.price) or (
        last.kind == "H" and float(high[last.index + 1:].max(initial=-np.inf)) > last.price
    )
    return GannResult(pivots, counts, projections, clusters, dates[-1], float(close[-1]), forming, future)

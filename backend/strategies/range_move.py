"""
% Range Move: how far a stock (or index) moved inside each calendar month, laid out year x month like the user's
"top range performance" sheet (2026-11-21).

The formula was reverse-engineered from the user's CGPOWER sheet and matches 163 of its 166 months exactly
(the other 3 differ only because their data vendor adjusted one corporate action differently):

    month closed at or above the previous month's close (an up month):   (High - Low) / Low  x 100
    month closed below the previous month's close (a down month):        (High - Low) / High x 100

i.e. the size of the month's range measured from the side the month started its move. The very first month of a
stock's history has no previous close, so its own open decides.

Colours follow the sheet: 30% and more is green, 20% to 30% orange, below 20% plain. In January-March a 30%+
month is boxed and counted (the sheet's "JAN-MAR BEST" note). The month still in progress is shown but is never
part of an average or a count. "Avg monthly range move" is the plain average of a year's complete months.
"""
from __future__ import annotations

import datetime as dt
import statistics
from typing import Any

import pandas as pd

ORANGE_MIN = 20.0
GREEN_MIN = 30.0
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def level(pct: float | None) -> str:
    """'green' (>= 30%), 'orange' (20-30%), 'plain' (< 20%) or 'none' (no value)."""
    if pct is None:
        return "none"
    if pct >= GREEN_MIN:
        return "green"
    if pct >= ORANGE_MIN:
        return "orange"
    return "plain"


def monthly_bars(daily: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar month: open, high, low, close, the previous month's close, first/last trading day."""
    d = daily.sort_index()
    d = d[~d.index.duplicated(keep="last")]
    g = d.groupby([d.index.year, d.index.month])
    mo = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
        "first_day": g.apply(lambda x: x.index[0]), "last_day": g.apply(lambda x: x.index[-1]),
    })
    mo.index.names = ["year", "month"]
    mo["prev_close"] = mo["close"].shift(1)
    return mo


def move_pct(high: float, low: float, close: float, prev_close: float | None, open_: float) -> tuple[float, str]:
    """The month's % range move and its direction ('up' / 'down')."""
    ref = prev_close if prev_close is not None and prev_close == prev_close else open_
    up = close >= ref
    base = low if up else high
    if not base or base <= 0:
        return 0.0, "up" if up else "down"
    return round((high - low) / base * 100, 2), "up" if up else "down"


def _month_key(d: dt.date) -> tuple[int, int]:
    return d.year, d.month


def build_table(
    daily: pd.DataFrame,
    symbol: str,
    today: dt.date | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> dict[str, Any]:
    """The whole sheet for one instrument. `start` / `end` filter whole months (the previous month's close still
    comes from the full history, so the first filtered month keeps its correct direction)."""
    today = today or dt.date.today()
    if daily is None or daily.empty:
        raise ValueError(f"No daily candles for {symbol}.")
    mo = monthly_bars(daily)
    lo_key = _month_key(start) if start else None
    hi_key = _month_key(end) if end else None

    cells: dict[tuple[int, int], dict[str, Any]] = {}
    monthly_rows: list[dict[str, Any]] = []
    for (y, m), r in mo.iterrows():
        key = (int(y), int(m))
        if lo_key and key < lo_key or hi_key and key > hi_key:
            continue
        prev = None if pd.isna(r.prev_close) else float(r.prev_close)
        pct, direction = move_pct(float(r.high), float(r.low), float(r.close), prev, float(r.open))
        in_progress = key == (today.year, today.month)
        cell = {"pct": pct, "direction": direction, "level": level(pct), "in_progress": in_progress,
                "boxed": m <= 3 and pct >= GREEN_MIN and not in_progress}
        cells[key] = cell
        monthly_rows.append({
            "year": key[0], "month": key[1], "label": f"{MONTHS[m - 1]} {key[0]}",
            "open": round(float(r.open), 2), "high": round(float(r.high), 2), "low": round(float(r.low), 2),
            "close": round(float(r.close), 2), "prev_close": None if prev is None else round(prev, 2),
            "direction": direction, "pct": pct, "in_progress": in_progress,
            "first_day": r.first_day.date().isoformat(), "last_day": r.last_day.date().isoformat(),
        })
    if not cells:
        raise ValueError(f"No months of {symbol} fall inside the chosen dates.")

    years = sorted({y for y, _ in cells})
    rows = []
    for y in years:
        months = [cells.get((y, m)) for m in range(1, 13)]
        complete = [c["pct"] for c in months if c and not c["in_progress"]]
        rows.append({"year": y, "months": months,
                     "avg": round(sum(complete) / len(complete), 2) if complete else None,
                     "complete_months": len(complete)})

    month_stats = []
    for m in range(1, 13):
        vals = [cells[(y, m)]["pct"] for y in years if (y, m) in cells and not cells[(y, m)]["in_progress"]]
        month_stats.append({
            "month": MONTHS[m - 1], "years": len(vals),
            "avg": round(statistics.mean(vals), 2) if vals else None,
            "median": round(statistics.median(vals), 2) if vals else None,
            "ge20": sum(v >= ORANGE_MIN for v in vals), "ge30": sum(v >= GREEN_MIN for v in vals),
            "max": max(vals) if vals else None, "min": min(vals) if vals else None,
        })

    complete_all = [c["pct"] for c in cells.values() if not c["in_progress"]]
    with_median = [s for s in month_stats if s["median"] is not None]
    jan_mar = {s["month"]: s["ge30"] for s in month_stats[:3]}
    best_count = max(jan_mar.values()) if jan_mar else 0
    first_day = daily.index.min().date()
    last_day = daily.index.max().date()
    return {
        "symbol": symbol,
        "thresholds": {"orange": ORANGE_MIN, "green": GREEN_MIN},
        "data_from": first_day.isoformat(),
        "data_to": last_day.isoformat(),
        "filter_from": f"{years[0]}-{min(m for (y, m) in cells if y == years[0]):02d}",
        "filter_to": f"{years[-1]}-{max(m for (y, m) in cells if y == years[-1]):02d}",
        "rows": rows,
        "month_stats": month_stats,
        "jan_mar": {"ge30": jan_mar, "best": [k for k, v in jan_mar.items() if v == best_count and best_count > 0]},
        "overall": {
            "months": len(complete_all),
            "avg": round(statistics.mean(complete_all), 2) if complete_all else None,
            "median": round(statistics.median(complete_all), 2) if complete_all else None,
            "ge20": sum(v >= ORANGE_MIN for v in complete_all),
            "ge30": sum(v >= GREEN_MIN for v in complete_all),
            "most_active": max(with_median, key=lambda s: s["median"])["month"] if with_median else None,
            "quietest": min(with_median, key=lambda s: s["median"])["month"] if with_median else None,
        },
        "monthly": monthly_rows,
    }

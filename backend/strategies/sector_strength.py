"""
Weekly sector & stock relative strength (2026-11-21), modelled on the "Sector & Stock Relative Performance" weekly
report the user shared, with its data problems fixed: every return is computed from Angel One daily closes on ONE
set of dates (that report read numbers off chart snapshots, so the same stock showed two different 1M returns).

* 1W return  = last close on/before the as-of date vs the last close on/before (as-of - 7 days).
* 1M return  = the same vs the last close on/before (as-of - 1 calendar month).
* vs 1W / vs 1M = stock return minus its sector's return, in percentage points.
* Signal: Leader = beats the sector on 1W and 1M; Turning up = 1W only; Fading = 1M only; Laggard = neither.
  Near-leader = beats on one horizon and is within 1.5 pp on the other; bounce-only = beats on 1W but trails the
  month by more than 1.5 pp.
* Sector verdict (the user's rule): STRONG when the sector index's daily, weekly AND monthly RSI(14) are all above
  60; WEAK when all three are below 40; otherwise MIXED. Weekly / monthly RSI include the period in progress,
  exactly like the scanner's GFS RSI.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from backend.indicators.resample import to_monthly, to_weekly
from backend.indicators.rsi import rsi

STRONG_RSI = 60.0
WEAK_RSI = 40.0
NEAR_PP = 1.5


def last_close_on_or_before(closes: pd.Series, day: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    s = closes[closes.index <= day]
    if s.empty:
        return None
    return s.index[-1], float(s.iloc[-1])


def period_returns(closes: pd.Series, as_of: pd.Timestamp) -> dict[str, Any] | None:
    """1W and 1M % returns ending on the last close on/before `as_of`."""
    closes = closes.dropna().sort_index()
    end = last_close_on_or_before(closes, as_of)
    if end is None:
        return None
    end_day, end_close = end
    w = last_close_on_or_before(closes, end_day - pd.Timedelta(days=7))
    m = last_close_on_or_before(closes, end_day - pd.DateOffset(months=1))
    pct = lambda base: None if base is None or not base[1] else round((end_close / base[1] - 1) * 100, 2)  # noqa: E731
    return {"end_date": end_day.date().isoformat(), "close": round(end_close, 2), "r1w": pct(w), "r1m": pct(m),
            "w_base_date": w[0].date().isoformat() if w else None, "m_base_date": m[0].date().isoformat() if m else None}


def rsi_levels(daily: pd.DataFrame, as_of: pd.Timestamp) -> dict[str, float | None]:
    """Latest daily, weekly and monthly RSI(14) up to `as_of` (weekly / monthly include the period in progress)."""
    d = daily[daily.index <= as_of]
    out: dict[str, float | None] = {"d": None, "w": None, "m": None}
    if len(d) < 20:
        return out

    def last(series: pd.Series) -> float | None:
        v = rsi(series.astype(float), period=14)
        v = v.dropna()
        return round(float(v.iloc[-1]), 2) if len(v) else None

    out["d"] = last(d["close"])
    out["w"] = last(to_weekly(d, include_partial=True)["close"])
    out["m"] = last(to_monthly(d, include_partial=True)["close"])
    return out


def verdict(levels: dict[str, float | None]) -> str:
    vals = [levels.get(k) for k in ("d", "w", "m")]
    if any(v is None for v in vals):
        return "N/A"
    if all(v > STRONG_RSI for v in vals):
        return "STRONG"
    if all(v < WEAK_RSI for v in vals):
        return "WEAK"
    return "MIXED"


def signal(vs1w: float | None, vs1m: float | None) -> str:
    if vs1w is None or vs1m is None:
        return "N/A"
    if vs1w > 0 and vs1m > 0:
        return "Leader"
    if vs1w > 0:
        return "Turning up"
    if vs1m > 0:
        return "Fading"
    return "Laggard"


def group(vs1w: float | None, vs1m: float | None) -> str | None:
    """'Near-leader' or 'Bounce-only' (the report's extra groups), else None."""
    if vs1w is None or vs1m is None:
        return None
    if (vs1w > 0) != (vs1m > 0) and min(vs1w, vs1m) >= -NEAR_PP:
        return "Near-leader"
    if vs1w > 0 and vs1m < -NEAR_PP:
        return "Bounce-only"
    return None


def _rank(values: dict[str, float | None]) -> dict[str, int | None]:
    order = sorted((k for k, v in values.items() if v is not None), key=lambda k: -values[k])
    ranks = {k: i + 1 for i, k in enumerate(order)}
    return {k: ranks.get(k) for k in values}


def build_report(
    as_of: pd.Timestamp,
    sectors: list[dict[str, Any]],
    index_data: dict[str, pd.DataFrame],
    stock_data: dict[str, pd.DataFrame],
    constituents: dict[str, list[dict[str, str]]],
    benchmark: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """`sectors`: [{key, label, index_label, equal_weight}], `index_data[key]` = the sector index's daily candles
    (absent for an equal-weight sector), `stock_data[symbol]` = daily candles, `constituents[key]` = NSE list."""
    stock_returns = {sym: period_returns(df["close"], as_of) for sym, df in stock_data.items() if df is not None and not df.empty}
    rows = []
    missing: set[str] = set()
    for s in sectors:
        key = s["key"]
        members = constituents.get(key, [])
        member_returns = [(m, stock_returns.get(m["symbol"])) for m in members]
        for m, r in member_returns:
            if r is None or r["r1w"] is None or r["r1m"] is None:
                missing.add(m["symbol"])
        if s.get("equal_weight"):
            valid = [r for _, r in member_returns if r and r["r1w"] is not None and r["r1m"] is not None]
            r1w = round(sum(r["r1w"] for r in valid) / len(valid), 2) if valid else None
            r1m = round(sum(r["r1m"] for r in valid) / len(valid), 2) if valid else None
            levels = {"d": None, "w": None, "m": None}
            end_date = valid[0]["end_date"] if valid else None
        else:
            idx = index_data.get(key)
            pr = period_returns(idx["close"], as_of) if idx is not None and not idx.empty else None
            r1w, r1m = (pr["r1w"], pr["r1m"]) if pr else (None, None)
            levels = rsi_levels(idx, as_of) if idx is not None and not idx.empty else {"d": None, "w": None, "m": None}
            end_date = pr["end_date"] if pr else None
        stocks = []
        for m, r in member_returns:
            if r is None or r["r1w"] is None or r["r1m"] is None or r1w is None or r1m is None:
                continue
            vs1w, vs1m = round(r["r1w"] - r1w, 2), round(r["r1m"] - r1m, 2)
            stocks.append({"symbol": m["symbol"], "name": m.get("name"), "industry": m.get("industry"),
                           "r1w": r["r1w"], "r1m": r["r1m"], "vs1w": vs1w, "vs1m": vs1m,
                           "signal": signal(vs1w, vs1m), "group": group(vs1w, vs1m), "combined": round(vs1w + vs1m, 2)})
        stocks.sort(key=lambda x: -x["r1m"])
        counts = {sig: sum(st["signal"] == sig for st in stocks) for sig in ("Leader", "Turning up", "Fading", "Laggard")}
        rows.append({
            "key": key, "label": s["label"], "index_label": s.get("index_label"), "equal_weight": bool(s.get("equal_weight")),
            "end_date": end_date, "r1w": r1w, "r1m": r1m, "rsi": levels, "verdict": verdict(levels),
            "stocks": stocks, "counts": counts, "members": len(members),
            "beat_1w": sum(st["vs1w"] > 0 for st in stocks), "beat_1m": sum(st["vs1m"] > 0 for st in stocks),
        })

    r1w_rank = _rank({r["key"]: r["r1w"] for r in rows})
    r1m_rank = _rank({r["key"]: r["r1m"] for r in rows})
    for r in rows:
        r["rank_1w"], r["rank_1m"] = r1w_rank[r["key"]], r1m_rank[r["key"]]
    order = {"STRONG": 0, "MIXED": 1, "WEAK": 2, "N/A": 3}
    rows.sort(key=lambda r: (order[r["verdict"]], ((r["rank_1w"] or 99) + (r["rank_1m"] or 99)) / 2))

    all_rows = [dict(st, sector=r["label"]) for r in rows for st in r["stocks"]]
    leaders = sorted((x for x in all_rows if x["signal"] == "Leader"), key=lambda x: -x["combined"])
    laggards = sorted((x for x in all_rows if x["signal"] == "Laggard"), key=lambda x: x["combined"])
    strong = [r for r in rows if r["verdict"] == "STRONG"]
    others = [r for r in rows if r["verdict"] != "STRONG"]
    buckets = {
        "strength_leaders": {r["label"]: [x["symbol"] for x in r["stocks"] if x["signal"] == "Leader"] for r in strong},
        "watch": {r["label"]: [x["symbol"] for x in r["stocks"] if x["group"] == "Near-leader" or x["signal"] == "Fading"] for r in strong},
        "stock_specific": {r["label"]: [x["symbol"] for x in r["stocks"] if x["signal"] == "Leader"] for r in others},
        "relative_weakness": {r["label"]: [x["symbol"] for x in r["stocks"] if x["signal"] == "Laggard" or x["group"] == "Bounce-only"] for r in strong},
    }
    buckets = {k: {sec: syms for sec, syms in v.items() if syms} for k, v in buckets.items()}

    bench = period_returns(benchmark["close"], as_of) if benchmark is not None and not benchmark.empty else None
    by_avg = sorted((r for r in rows if r["rank_1w"] and r["rank_1m"]), key=lambda r: (r["rank_1w"] + r["rank_1m"]) / 2)
    unique_stocks = {x["symbol"] for x in all_rows}
    return {
        "as_of": as_of.date().isoformat(),
        "end_date": max((r["end_date"] for r in rows if r["end_date"]), default=None),
        "benchmark": {"label": "Nifty 50", "r1w": bench["r1w"] if bench else None, "r1m": bench["r1m"] if bench else None},
        "rules": {"strong_rsi": STRONG_RSI, "weak_rsi": WEAK_RSI, "near_pp": NEAR_PP},
        "sectors": rows,
        "top_movers": leaders[:15],
        "laggards": laggards[:12],
        "buckets": buckets,
        "summary": {
            "top_sector": by_avg[0]["label"] if by_avg else None,
            "top_sector_r1w": by_avg[0]["r1w"] if by_avg else None,
            "top_sector_r1m": by_avg[0]["r1m"] if by_avg else None,
            "strong_sectors": [r["label"] for r in strong],
            "leaders": len(leaders), "laggards": len(laggards), "rows": len(all_rows), "stocks": len(unique_stocks),
        },
        "missing": sorted(missing),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }

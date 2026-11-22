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

2026-11-22 additions (all from the same price history, nothing stored anywhere):
* Last week: every sector's 1W / 1M return, rank, verdict and quadrant one week earlier (as-of - 7 days), so the
  report says what changed - which sector became STRONG, which stopped being STRONG, who moved up or down the ranks.
* Rotation: each sector's 1W and 1M return minus the Nifty 50's puts it in a quadrant - Leading (ahead on both),
  Improving (ahead on the week only), Weakening (ahead on the month only), Lagging (behind on both) - with its path
  over the last 4 weeks.
* Breadth: how many of a sector's stocks are above their 50-day and 200-day average, have a daily RSI above 60, and
  made a new 52-week high this week. An index can be lifted by two or three heavyweights; breadth shows whether the
  sector as a whole is strong: Broad (70%+ of its stocks above the 50-day average), Moderate (40-70%), Narrow (<40%).
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
WEEKS_BACK = 4            # the rotation path: this week and the 4 before it
BROAD_PCT, NARROW_PCT = 70, 40


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
    prev = closes[closes.index < end_day]
    d = (prev.index[-1], float(prev.iloc[-1])) if len(prev) else None
    pct = lambda base: None if base is None or not base[1] else round((end_close / base[1] - 1) * 100, 2)  # noqa: E731
    return {"end_date": end_day.date().isoformat(), "close": round(end_close, 2), "r1d": pct(d), "r1w": pct(w), "r1m": pct(m),
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


def quadrant(rel_1w: float | None, rel_1m: float | None) -> str | None:
    """Where a sector sits against the Nifty 50: its 1W and 1M return minus the Nifty's."""
    if rel_1w is None or rel_1m is None:
        return None
    if rel_1w > 0 and rel_1m > 0:
        return "Leading"
    if rel_1w > 0:
        return "Improving"
    if rel_1m > 0:
        return "Weakening"
    return "Lagging"


def stock_breadth(daily: pd.DataFrame, as_of: pd.Timestamp) -> dict[str, Any]:
    """One stock on `as_of`: above its 50 / 200-day average?, daily RSI(14), a new 52-week high this week?"""
    d = daily[daily.index <= as_of]
    close = d["close"].astype(float)
    out: dict[str, Any] = {"above_50dma": None, "above_200dma": None, "rsi_d": None, "high_52w": None}
    if len(close) >= 50:
        out["above_50dma"] = bool(close.iloc[-1] > close.iloc[-50:].mean())
    if len(close) >= 200:
        out["above_200dma"] = bool(close.iloc[-1] > close.iloc[-200:].mean())
    if len(close) >= 20:
        r = rsi(close, period=14).dropna()
        out["rsi_d"] = round(float(r.iloc[-1]), 2) if len(r) else None
    if len(d) >= 240:  # about a year of sessions; a newer listing has no meaningful 52-week high
        highs = d["high"].astype(float).iloc[-252:]
        out["high_52w"] = bool(highs.iloc[-5:].max() >= highs.max())
    return out


def sector_breadth(stocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Share of a sector's stocks above the 50 / 200-day average and with RSI above 60, the new 52-week highs, and
    a plain label: Broad / Moderate / Narrow (by the share above the 50-day average)."""
    def share(values: list[bool]) -> int | None:
        return round(100 * sum(values) / len(values)) if values else None

    above50 = share([x["above_50dma"] for x in stocks if x.get("above_50dma") is not None])
    above200 = share([x["above_200dma"] for x in stocks if x.get("above_200dma") is not None])
    rsi60 = share([x["rsi_d"] > STRONG_RSI for x in stocks if x.get("rsi_d") is not None])
    label = None if above50 is None else "Broad" if above50 >= BROAD_PCT else "Moderate" if above50 >= NARROW_PCT else "Narrow"
    return {"above_50dma": above50, "above_200dma": above200, "rsi_above_60": rsi60,
            "new_52w_highs": sum(1 for x in stocks if x.get("high_52w")), "stocks": len(stocks), "label": label}


def _sector_line(s: dict[str, Any], day: pd.Timestamp, index_data: dict[str, pd.DataFrame],
                 stock_closes: dict[str, pd.Series], members: list[dict[str, str]]) -> dict[str, Any] | None:
    """The sector's 1D / 1W / 1M return on `day`: its index, or the equal-weight average of its stocks."""
    if s.get("equal_weight"):
        rs = [period_returns(stock_closes[m["symbol"]], day) for m in members if m["symbol"] in stock_closes]
        valid = [r for r in rs if r and r["r1w"] is not None and r["r1m"] is not None]
        if not valid:
            return None
        avg = lambda k: round(sum(r[k] for r in valid if r[k] is not None) / max(1, sum(r[k] is not None for r in valid)), 2)  # noqa: E731
        return {"end_date": valid[0]["end_date"], "r1d": avg("r1d"), "r1w": avg("r1w"), "r1m": avg("r1m")}
    idx = index_data.get(s["key"])
    if idx is None or idx.empty:
        return None
    return period_returns(idx["close"], day)


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
    stock_closes = {sym: df["close"].dropna().sort_index() for sym, df in stock_data.items() if df is not None and not df.empty}
    stock_returns = {sym: period_returns(c, as_of) for sym, c in stock_closes.items()}
    stock_marks = {sym: stock_breadth(stock_data[sym], as_of) for sym in stock_closes}
    rows = []
    missing: set[str] = set()
    for s in sectors:
        key = s["key"]
        members = constituents.get(key, [])
        member_returns = [(m, stock_returns.get(m["symbol"])) for m in members]
        for m, r in member_returns:
            if r is None or r["r1w"] is None or r["r1m"] is None:
                missing.add(m["symbol"])
        line = _sector_line(s, as_of, index_data, stock_closes, members)
        r1d, r1w, r1m = (line["r1d"], line["r1w"], line["r1m"]) if line else (None, None, None)
        end_date = line["end_date"] if line else None
        idx = index_data.get(key)
        has_index = not s.get("equal_weight") and idx is not None and not idx.empty
        levels = rsi_levels(idx, as_of) if has_index else {"d": None, "w": None, "m": None}
        stocks = []
        for m, r in member_returns:
            if r is None or r["r1w"] is None or r["r1m"] is None or r1w is None or r1m is None:
                continue
            vs1w, vs1m = round(r["r1w"] - r1w, 2), round(r["r1m"] - r1m, 2)
            stocks.append({"symbol": m["symbol"], "name": m.get("name"), "industry": m.get("industry"),
                           "r1d": r["r1d"], "r1w": r["r1w"], "r1m": r["r1m"], "vs1w": vs1w, "vs1m": vs1m,
                           "signal": signal(vs1w, vs1m), "group": group(vs1w, vs1m), "combined": round(vs1w + vs1m, 2),
                           **stock_marks.get(m["symbol"], {})})
        stocks.sort(key=lambda x: -x["r1m"])
        counts = {sig: sum(st["signal"] == sig for st in stocks) for sig in ("Leader", "Turning up", "Fading", "Laggard")}
        member_marks = [stock_marks[m["symbol"]] for m in members if m["symbol"] in stock_marks]
        rows.append({
            "key": key, "label": s["label"], "index_label": s.get("index_label"), "equal_weight": bool(s.get("equal_weight")),
            "end_date": end_date, "r1d": r1d, "r1w": r1w, "r1m": r1m, "rsi": levels, "verdict": verdict(levels),
            "stocks": stocks, "counts": counts, "members": len(members),
            "beat_1w": sum(st["vs1w"] > 0 for st in stocks), "beat_1m": sum(st["vs1m"] > 0 for st in stocks),
            "breadth": sector_breadth(member_marks),
        })

    r1w_rank = _rank({r["key"]: r["r1w"] for r in rows})
    r1m_rank = _rank({r["key"]: r["r1m"] for r in rows})
    for r in rows:
        r["rank_1w"], r["rank_1m"] = r1w_rank[r["key"]], r1m_rank[r["key"]]

    # ---- last week and the rotation path (the same history, ending 7, 14, 21 and 28 days earlier) ----
    by_key = {s["key"]: s for s in sectors}
    bench_closes = benchmark["close"].dropna().sort_index() if benchmark is not None and not benchmark.empty else None
    trails: dict[str, list[dict[str, Any]]] = {r["key"]: [] for r in rows}
    prev_lines: dict[str, dict[str, Any] | None] = {}
    quad_now: dict[str, str | None] = {}
    quad_prev: dict[str, str | None] = {}
    for w in range(WEEKS_BACK, -1, -1):
        day = as_of - pd.Timedelta(days=7 * w)
        b = period_returns(bench_closes, day) if bench_closes is not None else None
        for r in rows:
            line = _sector_line(by_key[r["key"]], day, index_data, stock_closes, constituents.get(r["key"], [])) if w else                 {"end_date": r["end_date"], "r1w": r["r1w"], "r1m": r["r1m"]}
            if w == 1:
                prev_lines[r["key"]] = line
            if not line or line["r1w"] is None or line["r1m"] is None:
                continue
            rel_1w = round(line["r1w"] - (b["r1w"] if b and b["r1w"] is not None else 0), 2)
            rel_1m = round(line["r1m"] - (b["r1m"] if b and b["r1m"] is not None else 0), 2)
            q = quadrant(rel_1w, rel_1m)
            if w == 0:
                quad_now[r["key"]] = q
            elif w == 1:
                quad_prev[r["key"]] = q
            trails[r["key"]].append({"date": line["end_date"], "r1w": line["r1w"], "r1m": line["r1m"],
                                     "rel_1w": rel_1w, "rel_1m": rel_1m, "quadrant": q})
    prev_day = as_of - pd.Timedelta(days=7)
    prev_rank_1w = _rank({k: (v or {}).get("r1w") for k, v in prev_lines.items()})
    prev_rank_1m = _rank({k: (v or {}).get("r1m") for k, v in prev_lines.items()})
    for r in rows:
        idx = index_data.get(r["key"])
        prev_verdict = verdict(rsi_levels(idx, prev_day)) if not r["equal_weight"] and idx is not None and not idx.empty else "N/A"
        prev_line = prev_lines.get(r["key"]) or {}
        r["trail"] = trails[r["key"]]
        r["quadrant"] = quad_now.get(r["key"])
        r["prev"] = {"rank_1w": prev_rank_1w.get(r["key"]), "rank_1m": prev_rank_1m.get(r["key"]), "verdict": prev_verdict,
                     "quadrant": quad_prev.get(r["key"]), "r1w": prev_line.get("r1w"), "r1m": prev_line.get("r1m")}
        r["rank_change_1w"] = (r["prev"]["rank_1w"] - r["rank_1w"]) if r["prev"]["rank_1w"] and r["rank_1w"] else None
        r["rank_change_1m"] = (r["prev"]["rank_1m"] - r["rank_1m"]) if r["prev"]["rank_1m"] and r["rank_1m"] else None
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

    bench = period_returns(bench_closes, as_of) if bench_closes is not None else None
    moves = [r for r in rows if r["rank_change_1w"]]
    changes = {
        "prev_date": (bench_closes is not None and (period_returns(bench_closes, prev_day) or {}).get("end_date")) or prev_day.date().isoformat(),
        "new_strong": [r["label"] for r in rows if r["verdict"] == "STRONG" and r["prev"]["verdict"] not in ("STRONG", "N/A")],
        "dropped_strong": [r["label"] for r in rows if r["prev"]["verdict"] == "STRONG" and r["verdict"] != "STRONG"],
        "risers": [{"label": r["label"], "from": r["prev"]["rank_1w"], "to": r["rank_1w"]}
                   for r in sorted(moves, key=lambda r: -r["rank_change_1w"]) if r["rank_change_1w"] >= 2][:3],
        "fallers": [{"label": r["label"], "from": r["prev"]["rank_1w"], "to": r["rank_1w"]}
                    for r in sorted(moves, key=lambda r: r["rank_change_1w"]) if r["rank_change_1w"] <= -2][:3],
        "quadrant_moves": [{"label": r["label"], "from": r["prev"]["quadrant"], "to": r["quadrant"]} for r in rows
                           if r["quadrant"] and r["prev"]["quadrant"] and r["quadrant"] != r["prev"]["quadrant"]],
    }
    by_avg = sorted((r for r in rows if r["rank_1w"] and r["rank_1m"]), key=lambda r: (r["rank_1w"] + r["rank_1m"]) / 2)
    unique_stocks = {x["symbol"] for x in all_rows}
    return {
        "as_of": as_of.date().isoformat(),
        "end_date": max((r["end_date"] for r in rows if r["end_date"]), default=None),
        "benchmark": {"label": "Nifty 50", "r1d": bench["r1d"] if bench else None, "r1w": bench["r1w"] if bench else None,
                      "r1m": bench["r1m"] if bench else None},
        "changes": changes,
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

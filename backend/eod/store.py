"""Per-stock adjusted daily history from the cached bhavcopy day files (2026-11-23).

Splits and bonuses: the bhavcopy prices are raw, but NSE's PREVCLOSE on an ex-date is already adjusted. So on each day
factor = PREVCLOSE(today) / CLOSE(yesterday); a factor away from 1 marks a corporate action, and every earlier
price is multiplied by the product of the later factors (volume divided). Ordinary dividends move PREVCLOSE by well
under ADJUST_MIN, so they are left alone. A stock that changed its symbol starts fresh under the new symbol.
"""
from __future__ import annotations

import datetime as dt
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

ADJUST_MIN = 0.03  # |factor - 1| below this is not a split/bonus (dividends, rounding)
SERIES_RANK = {"EQ": 0, "BE": 1, "BZ": 2}


def _load_days(raw: Path) -> pd.DataFrame:
    """All day files in one compact frame: categorical symbol/series and float32 prices keep ~10 million rows in a few
    hundred MB (an 8 GB laptop could not hold the plain-object version)."""
    num = {"open": "float32", "high": "float32", "low": "float32", "close": "float32", "prevclose": "float32", "volume": "float64"}
    frames = []
    for p in sorted(raw.glob("*/*.csv")):
        try:
            df = pd.read_csv(p, dtype={"symbol": "string", "series": "string", **num})
        except (pd.errors.EmptyDataError, ValueError):
            continue
        if df.empty:
            continue
        df["date"] = np.datetime64(dt.datetime.strptime(p.stem, "%Y%m%d").date(), "D")
        frames.append(df)
    allrows = pd.concat(frames, ignore_index=True)
    del frames
    allrows["symbol"] = allrows["symbol"].astype("category")
    allrows["rank"] = allrows["series"].map(SERIES_RANK).fillna(9).astype("int8")
    allrows = allrows.drop(columns=["series"])
    # one row per stock per day: EQ before BE before BZ
    allrows = allrows.sort_values(["symbol", "date", "rank"], kind="stable").drop_duplicates(["symbol", "date"], keep="first")
    return allrows.drop(columns=["rank"])


def _adjust(g: pd.DataFrame) -> pd.DataFrame:
    close, prev = g["close"].to_numpy(float), g["prevclose"].to_numpy(float)
    factor = np.ones(len(g))
    with np.errstate(divide="ignore", invalid="ignore"):
        f = prev[1:] / close[:-1]
    f = np.where(np.isfinite(f) & (f > 0), f, 1.0)
    f = np.where(np.abs(f - 1) >= ADJUST_MIN, f, 1.0)
    factor[:-1] = f  # the factor of day i+1 applies to day i and everything before it
    cum = np.cumprod(factor[::-1])[::-1]  # product of all factors from this day onward
    out = g[["open", "high", "low", "close", "volume"]].copy()
    for c in ("open", "high", "low", "close"):
        out[c] = (out[c].to_numpy(float) * cum).astype("float32")
    out["volume"] = out["volume"].to_numpy(float) / cum
    out.index = pd.DatetimeIndex(g["date"].to_numpy())
    return out


def _symbol_changes(root: Path) -> dict[str, str]:
    """NSE's symbol-change list (old -> new, chains followed), e.g. IIFLWAM -> 360ONE, SSLT -> VEDL, so a renamed
    stock keeps its whole history under today's symbol."""
    path = root / "symbolchange.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, encoding="latin-1")
    df.columns = [c.strip().upper() for c in df.columns]
    pairs = {o.strip(): n.strip() for o, n in zip(df["OLD SYMBOL"], df["NEW SYMBOL"]) if isinstance(o, str) and isinstance(n, str)}
    final = {}
    for old in pairs:
        cur, seen = old, set()
        while cur in pairs and cur not in seen:
            seen.add(cur)
            cur = pairs[cur]
        final[old] = cur
    return final


def build(root: Path) -> dict[str, pd.DataFrame]:
    rows = _load_days(root / "raw")
    changes = _symbol_changes(root)
    if changes:
        sym = rows["symbol"].astype(str).map(lambda x: changes.get(x, x))
        rows["symbol"] = sym.astype("category")
        # an old and a new symbol trading on the same day (rare overlap): keep the new symbol's own row
        rows = rows.drop_duplicates(["symbol", "date"], keep="last").sort_values(["symbol", "date"], kind="stable")
    store = {str(sym): _adjust(g) for sym, g in rows.groupby("symbol", sort=False, observed=True)}
    del rows
    with open(root / "history.pkl", "wb") as fh:
        pickle.dump(store, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return store


def load(root: Path) -> dict[str, pd.DataFrame]:
    with open(root / "history.pkl", "rb") as fh:
        return pickle.load(fh)

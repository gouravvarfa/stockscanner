"""Weekly Sectors report from end-of-day data (2026-11-26, user: it must update on its own, even with the app closed).

The evening job builds the same report the Weekly Sectors page builds through Angel One - same sectors, same
constituents, same build_report() - but from NSE's daily index files (raw_idx) and the adjusted stock history, and
writes it to weekly.json. The site shows it at once; a newer report run from the page still takes over.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pandas as pd

from backend.eod.sectors import NSE_INDEX_NAME

BENCH = "Nifty 50"
STOCK_DAYS = 400
COLS = {"Open Index Value": "open", "High Index Value": "high", "Low Index Value": "low", "Closing Index Value": "close", "Volume": "volume"}


def load_index_ohlc(root: Path, names: set[str]) -> dict[str, pd.DataFrame]:
    """NSE index name -> daily OHLC frame from the cached ind_close_all files."""
    want = {n.lower(): n for n in names}
    rows: dict[str, list] = {n: [] for n in names}
    for p in sorted((root / "raw_idx").glob("*/*.csv")):
        try:
            df = pd.read_csv(p)
        except (ValueError, pd.errors.EmptyDataError):
            continue
        df = df[df["Index Name"].astype(str).str.strip().str.lower().isin(want)]
        for _, r in df.iterrows():
            try:
                rows[want[str(r["Index Name"]).strip().lower()]].append(
                    (pd.to_datetime(r["Index Date"], dayfirst=True), *(pd.to_numeric(r[c], errors="coerce") for c in COLS)))
            except (ValueError, TypeError):
                continue
    out = {}
    for n, rs in rows.items():
        if rs:
            f = pd.DataFrame(rs, columns=["date", *COLS.values()]).dropna(subset=["close"]).drop_duplicates("date").set_index("date").sort_index()
            out[n] = f.astype(float)
    return out


def build(root: Path, store: dict[str, pd.DataFrame]) -> dict:
    from backend.services.sector_strength_service import SECTORS, load_constituents
    from backend.strategies.sector_strength import build_report

    constituents, source = asyncio.run(load_constituents())
    names = {NSE_INDEX_NAME[s["key"]] for s in SECTORS if s["index"] and s["key"] in NSE_INDEX_NAME} | {BENCH}
    idx = load_index_ohlc(root, names)
    index_data = {s["key"]: idx[NSE_INDEX_NAME[s["key"]]] for s in SECTORS if s["index"] and NSE_INDEX_NAME.get(s["key"]) in idx}
    bench = idx.get(BENCH)
    as_of = max(df.index[-1] for df in store.values() if len(df))
    if bench is not None:
        as_of = min(as_of, bench.index[-1])  # never past the last index file
    start = as_of - pd.Timedelta(days=STOCK_DAYS)
    symbols = {m["symbol"] for members in constituents.values() for m in members}
    stock_data = {sym: store[sym].loc[start:as_of] for sym in symbols if sym in store and len(store[sym].loc[start:as_of])}
    sectors = [{"key": s["key"], "label": s["label"], "index_label": s["index"], "equal_weight": s["index"] is None, "tv_symbol": s.get("tv")} for s in SECTORS]
    report = build_report(pd.Timestamp(as_of), sectors, index_data, stock_data, constituents, bench)
    report["constituents_source"] = source
    report["data_source"] = "NSE end-of-day"
    return report


def write(out_dir: Path, root: Path, store: dict[str, pd.DataFrame]) -> None:
    report = build(root, store)
    (out_dir / "weekly.json").write_text(json.dumps(report, separators=(",", ":"), default=str), encoding="utf-8")

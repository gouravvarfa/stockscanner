"""
Isolated, per-symbol on-disk cache for Cup Breakout's ~10-year daily
history ONLY — completely separate from backend.core.cache's shared
FileCache (never imports or touches it; every other strategy's caching
is unaffected).

WHY THIS EXISTS (2026-09-24, real Render 512MB OOM restart):
The shared FileCache keeps EVERY cached value in one process-wide dict
that is never evicted, and re-pickles that ENTIRE growing dict to disk
on every single `.set()` call. That is fine for the small payloads
every other cache use in this project stores, but Cup's ~2,400-row
daily history for up to 615 stocks meant, by the end of a scan, 615
DataFrames permanently resident in memory AND each new stock's write
re-serializing every previously-cached stock's data all over again — a
memory footprint AND a write cost both growing without bound across a
single scan. That combination is the most likely cause of the OOM.

THIS MODULE: one file per symbol (`.cache/cup_history/{SYMBOL}.pkl`).
A write touches only that one file. A read loads only that one
symbol's DataFrame — nothing else is ever held in memory, and nothing
akin to a single shared "everything" store exists here at all, so nothing
here can grow unbounded across a scan the way the old shared-cache
usage did.

FORMAT: pickle (Python stdlib) — this project does not have pyarrow/
parquet installed (checked before writing this), and adding a new
dependency for this fix would be broader than the "smallest safe fix"
this task calls for. Each file is a small dict (metadata header + one
DataFrame), never a shared multi-symbol store.
"""
from __future__ import annotations

import datetime as dt
import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger("scanner.cup_disk_cache")

CACHE_DIR = Path(".cache/cup_history")
SCHEMA_VERSION = 1


@dataclass
class CupCacheEntry:
    symbol: str
    oldest_date: pd.Timestamp | None
    newest_date: pd.Timestamp | None
    rows: int
    fetched_at: str
    data: pd.DataFrame


def _path_for(symbol: str) -> Path:
    # Symbols are already normalized upstream (A-Group universe, uppercase
    # tickers), but strip anything that isn't filesystem-safe defensively.
    safe = "".join(c for c in symbol.upper() if c.isalnum() or c in ("-", "_")) or "UNKNOWN"
    return CACHE_DIR / f"{safe}.pkl"


def load(symbol: str) -> CupCacheEntry | None:
    """
    Returns the cached entry for exactly this one symbol, or None on a
    cache miss, a corrupt/unreadable file, a schema-version mismatch, or a
    malformed payload — every one of those is treated identically to "no
    cache" (safe refetch), never a crash or a stale/wrong result.
    """
    path = _path_for(symbol)
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            raw = pickle.load(f)
    except Exception:  # noqa: BLE001 — corrupt/partial file -> refetch, not a crash
        logger.warning("Cup history cache file for %s is unreadable — refetching.", symbol)
        return None
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        return None
    df = raw.get("data")
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    return CupCacheEntry(
        symbol=raw.get("symbol", symbol),
        oldest_date=df.index.min(),
        newest_date=df.index.max(),
        rows=len(df),
        fetched_at=raw.get("fetched_at", ""),
        data=df,
    )


def save(symbol: str, df: pd.DataFrame) -> None:
    """Writes ONLY this symbol's own file — never reads, holds, or
    re-serializes any other symbol's cached data."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "data": df,
    }
    path = _path_for(symbol)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp_path.replace(path)  # atomic on POSIX/NTFS — never leaves a half-written cache file


def delete(symbol: str) -> None:
    _path_for(symbol).unlink(missing_ok=True)

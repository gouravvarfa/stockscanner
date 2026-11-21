"""
Range Analysis (2026-11-21): the year x month "% range move" sheet for ANY NSE stock or index the user searches,
from the oldest daily candle Angel One has (back to the mid-1990s for long-listed stocks) - see
backend/strategies/range_move.py for the formula and colours.

Angel One's ONE_DAY endpoint returns ~5 years per request, so 30+ years arrive in about 7 requests. A local run
keeps each instrument's history on disk (`.cache/range_history`) and only fetches the missing days afterwards; on
Render (512 MB, disk wiped on restart) nothing is written and only the last few instruments stay in memory.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import pickle
from collections import OrderedDict
from pathlib import Path

import pandas as pd

from backend.core.runtime import STATELESS_SERVER, keep
from backend.providers import angelone_scrip_master as scrip_master
from backend.providers.angelone_provider import AngelOneProvider
from backend.services import universe_loader
from backend.strategies.range_move import build_table

logger = logging.getLogger("scanner.range_analysis")

EARLIEST = dt.datetime(1990, 1, 1)
CHUNK_DAYS = 1900  # Angel One returns up to ~2000 daily candles per request
CHUNK_PAUSE_S = 0.4
CACHE_DIR = Path(".cache/range_history")
_memory: "OrderedDict[str, tuple[dt.date, pd.DataFrame]]" = OrderedDict()
_MEMORY_MAX = keep(30, 4)
_locks: dict[str, asyncio.Lock] = {}


class InstrumentNotFound(ValueError):
    pass


async def resolve(symbol: str) -> tuple[scrip_master.ScripMatch, str]:
    """An NSE cash listing first (EQ, BE or BZ), else an NSE index (e.g. NIFTY, BANKNIFTY)."""
    sym = symbol.strip().upper()
    match = await scrip_master.resolve_equity(sym)
    if match is not None:
        return match, "EQUITY"
    match = await scrip_master.resolve_index(sym)
    if match is not None:
        return match, "INDEX"
    raise InstrumentNotFound(f"'{sym}' is not an NSE stock or index Angel One knows.")


async def _fetch_range(provider: AngelOneProvider, match: scrip_master.ScripMatch, start: dt.datetime,
                       end: dt.datetime) -> pd.DataFrame:
    frames = []
    cur = start
    first = True
    while cur < end:
        stop = min(cur + dt.timedelta(days=CHUNK_DAYS), end)
        if not first:
            await asyncio.sleep(CHUNK_PAUSE_S)
        first = False
        frames.append(await provider.get_daily_ohlc_range(match.exch_seg, match.token, cur, stop))
        cur = stop + dt.timedelta(days=1)
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.concat(frames)
    return df[~df.index.duplicated(keep="last")].sort_index()


def _disk_path(key: str) -> Path:
    return CACHE_DIR / f"{key.replace('/', '_')}.pkl"


def _load_disk(key: str) -> tuple[dt.date, pd.DataFrame] | None:
    if STATELESS_SERVER:
        return None
    try:
        with open(_disk_path(key), "rb") as f:
            saved = pickle.load(f)
        return saved["fetched_on"], saved["data"]
    except (OSError, pickle.UnpicklingError, KeyError, EOFError):
        return None


def _save_disk(key: str, fetched_on: dt.date, df: pd.DataFrame) -> None:
    if STATELESS_SERVER:
        return
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_disk_path(key), "wb") as f:
            pickle.dump({"fetched_on": fetched_on, "data": df}, f)
    except OSError as exc:  # caching is best-effort
        logger.warning("could not cache %s range history: %s", key, exc)


def _remember(key: str, fetched_on: dt.date, df: pd.DataFrame) -> None:
    _memory[key] = (fetched_on, df)
    _memory.move_to_end(key)
    while len(_memory) > max(_MEMORY_MAX, 1):
        _memory.popitem(last=False)


async def daily_history(provider: AngelOneProvider, symbol: str) -> tuple[pd.DataFrame, str]:
    """Every daily candle Angel One has for `symbol`, refreshed once a day (only the missing tail is fetched)."""
    match, kind = await resolve(symbol)
    key = f"{kind}_{symbol.strip().upper()}"
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        today = dt.date.today()
        cached = _memory.get(key) or _load_disk(key)
        if cached is not None and cached[0] == today and not cached[1].empty:
            _remember(key, *cached)
            return cached[1], kind
        now = dt.datetime.now()
        if cached is not None and not cached[1].empty:
            tail = await _fetch_range(provider, match, cached[1].index.max().to_pydatetime() - dt.timedelta(days=7), now)
            df = pd.concat([cached[1], tail]) if not tail.empty else cached[1]
            df = df[~df.index.duplicated(keep="last")].sort_index()
        else:
            df = await _fetch_range(provider, match, EARLIEST, now)
        if df.empty:
            raise InstrumentNotFound(f"Angel One returned no daily candles for '{symbol.upper()}'.")
        _remember(key, today, df)
        _save_disk(key, today, df)
        return df, kind


async def analyse(provider: AngelOneProvider, symbol: str, start: dt.date | None = None,
                  end: dt.date | None = None) -> dict:
    df, kind = await daily_history(provider, symbol)
    table = build_table(df, symbol.strip().upper(), start=start, end=end)
    table["kind"] = kind
    table["name"] = universe_loader.company_name_for(table["symbol"]) if kind == "EQUITY" else None
    return table


async def search(query: str, limit: int = 15) -> list[dict]:
    """NSE stocks and indices whose symbol (or, for A Group stocks, company name) matches `query`."""
    q = query.strip().upper()
    if not q:
        return []
    rows = await scrip_master._fetch_scrip_master()
    seen: dict[str, dict] = {}
    for row in rows:
        if row.get("exch_seg") != "NSE":
            continue
        name = str(row.get("name", "")).upper()
        if not name or name in seen:
            continue
        typ = row.get("instrumenttype")
        if typ == "":
            if str(row.get("symbol", "")).rpartition("-")[2] not in scrip_master.EQUITY_SERIES:
                continue
            seen[name] = {"symbol": name, "name": universe_loader.company_name_for(name), "kind": "EQUITY"}
        elif typ == "AMXIDX":
            seen[name] = {"symbol": name, "name": str(row.get("symbol", "")), "kind": "INDEX"}

    def score(item: dict) -> tuple[int, int, int, str]:
        sym, company = item["symbol"], (item["name"] or "").upper()
        if sym == q:
            rank = 0
        elif sym.startswith(q):
            rank = 1
        elif company.startswith(q):
            rank = 2
        elif q in sym or q in company:
            rank = 3
        else:
            rank = 9
        # well-known (A Group, so with a company name) first: "REL" -> RELAXO, RELIANCE, RELIGARE before RELTD
        return rank, 0 if item["name"] else 1, len(sym), sym

    hits = sorted((i for i in seen.values() if score(i)[0] < 9), key=score)
    return hits[:limit]

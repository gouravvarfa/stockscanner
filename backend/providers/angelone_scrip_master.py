"""
Resolves NIFTY/BANKNIFTY/stock symbols to Angel One's exchange + instrument
token, via Angel One's own public instrument master file (no auth, no market
prices — just a symbol directory). Same real source URL as Angel One's
published SmartAPI docs.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from backend.core.cache import cache

SCRIP_MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
CACHE_KEY = "angelone:scrip_master:v2"  # v2: broadened to include NFO stock futures for Expiry Level 5
CACHE_TTL_SECONDS = 24 * 3600

# NSE: equities ("") + indices ("AMXIDX"). NFO: stock futures ("FUTSTK"), needed
# for Expiry Level 5's stock-future underlying — options/index futures not needed yet.
RELEVANT_NSE_TYPES = {"", "AMXIDX"}
RELEVANT_NFO_TYPES = {"FUTSTK"}


@dataclass
class ScripMatch:
    token: str
    trading_symbol: str
    exch_seg: str


async def _fetch_scrip_master() -> list[dict]:
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(SCRIP_MASTER_URL)
    response.raise_for_status()
    rows = response.json()

    filtered = [
        row
        for row in rows
        if (row.get("exch_seg") == "NSE" and row.get("instrumenttype") in RELEVANT_NSE_TYPES)
        or (row.get("exch_seg") == "NFO" and row.get("instrumenttype") in RELEVANT_NFO_TYPES)
    ]
    cache.set(CACHE_KEY, filtered, CACHE_TTL_SECONDS)
    return filtered


async def resolve_index(name: str) -> ScripMatch | None:
    """name e.g. 'NIFTY', 'BANKNIFTY' (Angel's index `name` field, not the tradingsymbol)."""
    rows = await _fetch_scrip_master()
    for row in rows:
        if row.get("instrumenttype") == "AMXIDX" and row.get("name") == name:
            return ScripMatch(token=row["token"], trading_symbol=row["symbol"], exch_seg="NSE")
    return None


# NSE cash-segment series, in preference order. "EQ" is the normal rolling
# segment; "BE"/"BZ" are the trade-to-trade/surveillance series — still real,
# fully tradable cash listings with the same historical-candle support, and
# the ONLY listing for stocks such as HEG, HFCL, STLTECH and INDIAGLYCO.
# Matching "-EQ" alone silently made ~240 NSE stocks unresolvable.
EQUITY_SERIES = ("EQ", "BE", "BZ")


async def resolve_equity(symbol: str) -> ScripMatch | None:
    """symbol e.g. 'RELIANCE' -> resolves its NSE cash listing (EQ, else BE/BZ)."""
    rows = await _fetch_scrip_master()
    by_series: dict[str, dict] = {}
    for row in rows:
        if row.get("instrumenttype") != "" or row.get("name") != symbol:
            continue
        series = str(row.get("symbol", "")).rpartition("-")[2]
        if series in EQUITY_SERIES:
            by_series.setdefault(series, row)

    for series in EQUITY_SERIES:
        row = by_series.get(series)
        if row is not None:
            return ScripMatch(token=row["token"], trading_symbol=row["symbol"], exch_seg="NSE")
    return None


async def resolve_stock_future(symbol: str) -> ScripMatch | None:
    """
    symbol e.g. 'RELIANCE' -> resolves the NEAREST-EXPIRY NFO stock future
    (FUTSTK) contract for that underlying. Returns None if the symbol has no
    listed futures contract (not every NIFTY 200 stock has one) — callers
    must treat that as "unavailable for this symbol", never fabricate one.
    """
    import datetime as dt

    rows = await _fetch_scrip_master()
    candidates = [
        row for row in rows
        if row.get("exch_seg") == "NFO" and row.get("instrumenttype") == "FUTSTK" and row.get("name") == symbol
    ]
    if not candidates:
        return None

    def _expiry_key(row: dict) -> dt.datetime:
        try:
            return dt.datetime.strptime(row.get("expiry", ""), "%d%b%Y")
        except ValueError:
            return dt.datetime.max  # unparsable expiry sorts last, never picked over a real one

    nearest = min(candidates, key=_expiry_key)
    return ScripMatch(token=nearest["token"], trading_symbol=nearest["symbol"], exch_seg="NFO")

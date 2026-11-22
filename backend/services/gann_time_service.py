"""
Gann Time module: future turn-date clusters (backend/strategies/gann_time.py)
for (a) every A Group stock in a STRONG sector and (b) any single NSE stock.

Strong sector: sector score = average of (sector median 1M return - NIFTY 1M
return) and (sector median 3M return - NIFTY 3M return). Every sector with a
score above 0 (i.e. beating NIFTY) is strong, and the top 3 always are. Sectors
with fewer than 3 stocks are not ranked. 1M = 21 bars, 3M = 63 bars.

The sector list is a background scan of ~600 stocks (same pattern and Angel One
rate-limit care as gfs_universe_service.py); the page polls its progress.
"""
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import difflib
import logging
import re
import statistics
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd

from backend.config.nse_holidays import ALL_NSE_HOLIDAYS
from backend.providers import angelone_scrip_master as scrip_master
from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.market_data_router import DataUnavailableError
from backend.services import universe_loader
from backend.services.gfs_universe_service import _yield_to_backtests
from backend.services.sectors import sector_for
from backend.strategies import gann_time

logger = logging.getLogger("scanner.gann_time")

HISTORY_DAYS = 800
MAX_CONCURRENT_FETCHES = 2
PER_STOCK_TIMEOUT_SECONDS = 75.0
CACHE_TTL = dt.timedelta(hours=12)
R1M, R3M = 21, 63
MIN_SECTOR_STOCKS = 3  # a sector needs at least this many stocks to be ranked
MIN_STRONG_SECTORS = 3  # the top N sectors are always treated as strong
_NSE_LIST = Path(__file__).resolve().parent.parent / "data" / "nse_equity_list.csv"


# MCX commodities (2026-11-22): front-month futures, stitched contract to contract.
COMMODITIES: dict[str, str] = {
    "GOLD": "Gold", "SILVER": "Silver", "CRUDEOIL": "Crude Oil", "NATURALGAS": "Natural Gas",
    "COPPER": "Copper", "ZINC": "Zinc", "ALUMINIUM": "Aluminium", "LEAD": "Lead",
}


def is_commodity(symbol: str) -> bool:
    return symbol.strip().upper() in COMMODITIES


# ---------------------------------------------------------------- NSE search
@lru_cache(maxsize=1)
def _nse_names() -> dict[str, str]:
    try:
        with open(_NSE_LIST, encoding="utf-8") as fh:
            rows = csv.reader(fh)
            next(rows, None)
            return {r[0].strip().upper(): r[1].strip() for r in rows if len(r) > 1 and r[0].strip()}
    except OSError:
        return {}


def company_name(symbol: str) -> str:
    if is_commodity(symbol):
        return f"{COMMODITIES[symbol.strip().upper()]} (MCX futures)"
    return _nse_names().get(symbol) or universe_loader.company_name_for(symbol) or symbol


def _norm(text: str) -> str:
    return re.sub(r"[^A-Z0-9 ]", "", text.upper())


def search_nse(query: str, limit: int = 20) -> list[dict]:
    """Any NSE equity (and the MCX commodities), by symbol or name, with typo tolerance."""
    names = {s: f"{n} (MCX futures)" for s, n in COMMODITIES.items()}
    names.update(_nse_names())
    for s in universe_loader.load_a_group_universe():
        names.setdefault(s, universe_loader.company_name_for(s) or s)
    nq = _norm(query.strip())
    squashed = nq.replace(" ", "")
    if not squashed:
        return []
    tokens = nq.split()
    starts = sorted((s for s in names if s.startswith(squashed)), key=len)
    seen = set(starts)
    contains = [s for s in names if squashed in s and s not in seen]
    seen.update(contains)
    by_name = [
        s for s, n in names.items()
        if s not in seen and all(any(w.startswith(t) for w in _norm(n).split()) for t in tokens)
    ]
    found = starts + contains + by_name
    if not found:
        found = difflib.get_close_matches(squashed, list(names), n=limit, cutoff=0.6)
    if not found:
        found = [
            s for s, n in names.items()
            if difflib.SequenceMatcher(None, squashed, _norm(n).replace(" ", "")[: len(squashed) + 4]).ratio() >= 0.7
        ]
    return [{"symbol": s, "company_name": names[s]} for s in found[:limit]]


# ---------------------------------------------------------------- data
async def _commodity_daily(provider: AngelOneProvider, name: str) -> pd.DataFrame:
    """One continuous daily series from MCX's live contracts: each day comes from the nearest contract that had
    not yet expired that day (the front month). Angel One serves only live contracts, so history is as long as
    the oldest live contract (about a year for most commodities)."""
    contracts = await scrip_master.mcx_commodity_contracts(name)
    if not contracts:
        raise DataUnavailableError(f"No live MCX {name} futures contract found.")
    frames = []
    for token, expiry in contracts[:4]:
        try:
            df = await provider.get_intraday_ohlc("MCX", token, "ONE_DAY", HISTORY_DAYS)
        except Exception:  # noqa: BLE001 - one contract without data must not stop the rest
            continue
        if df is not None and not df.empty:
            frames.append((expiry, df.sort_index()))
    if not frames:
        raise DataUnavailableError(f"Angel One returned no daily candles for MCX {name}.")
    # each day from the nearest contract that had not expired yet (frames are nearest-expiry first)
    rows: dict[pd.Timestamp, pd.Series] = {}
    for expiry, df in frames:
        live = df[df.index.normalize() <= pd.Timestamp(expiry).normalize()]
        for ts, row in live.iterrows():
            rows.setdefault(ts, row)
    return pd.DataFrame.from_dict(rows, orient="index").sort_index()


async def _daily(provider: AngelOneProvider, symbol: str) -> pd.DataFrame:
    if is_commodity(symbol):
        return await _commodity_daily(provider, symbol.strip().upper())
    match = await provider.resolve_equity(symbol)
    if match is None:
        raise DataUnavailableError(f"'{symbol}' has no NSE equity listing.")
    return await provider.get_intraday_ohlc(match.exch_seg, match.token, "ONE_DAY", HISTORY_DAYS)


async def _nifty(provider: AngelOneProvider) -> pd.DataFrame:
    match = await scrip_master.resolve_index("NIFTY")
    if match is None:
        raise DataUnavailableError("NIFTY index not found in the scrip master.")
    return await provider.get_intraday_ohlc(match.exch_seg, match.token, "ONE_DAY", 200)


def _ret(close: pd.Series, bars: int) -> float | None:
    if len(close) <= bars:
        return None
    return float(close.iloc[-1] / close.iloc[-1 - bars] - 1) * 100


def _cluster_out(c: gann_time.Cluster) -> dict:
    return {
        "date": c.date, "bars_away": c.bars_away, "strength": c.strength,
        "projections": [{"label": p.label, "source_date": p.source_date, "count": p.count} for p in c.projections],
    }


# ---------------------------------------------------------------- sector scan
@dataclass
class StockRow:
    symbol: str
    company_name: str
    sector: str
    close: float
    ret_1m: float | None
    ret_3m: float | None
    last_pivot_kind: str | None
    last_pivot_date: dt.date | None
    new_swing_forming: bool
    clusters: list[dict]


@dataclass
class ScanState:
    status: str = "idle"  # idle | running | done | error
    total: int = 0
    processed: int = 0
    failed: int = 0
    stocks: list[StockRow] = field(default_factory=list)
    nifty_1m: float | None = None
    nifty_3m: float | None = None
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    error: str | None = None


_state = ScanState()
_task: asyncio.Task | None = None


def evaluate(symbol: str, df: pd.DataFrame) -> StockRow | None:
    """Pure: one stock's returns + Gann clusters."""
    if df is None or df.empty:
        return None
    df = df.sort_index()
    res = gann_time.analyse(df, set(ALL_NSE_HOLIDAYS))
    close = df["close"]
    last = res.pivots[-1] if res else None
    return StockRow(
        symbol=symbol, company_name=company_name(symbol), sector=sector_for(symbol) or "Other",
        close=float(close.iloc[-1]), ret_1m=_ret(close, R1M), ret_3m=_ret(close, R3M),
        last_pivot_kind=last.kind if last else None, last_pivot_date=last.date if last else None,
        new_swing_forming=bool(res and res.new_swing_forming),
        clusters=[_cluster_out(c) for c in res.clusters] if res else [],
    )


async def _run(provider: AngelOneProvider, state: ScanState) -> None:
    sem = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
    try:
        nifty = await _nifty(provider)
        state.nifty_1m, state.nifty_3m = _ret(nifty["close"], R1M), _ret(nifty["close"], R3M)
    except Exception as exc:  # noqa: BLE001 - sectors then rank against 0 instead of NIFTY
        logger.warning("NIFTY fetch failed: %s", exc)

    async def one(symbol: str) -> None:
        try:
            async with sem:
                await _yield_to_backtests()
                df = await asyncio.wait_for(_daily(provider, symbol), timeout=PER_STOCK_TIMEOUT_SECONDS)
            row = await asyncio.to_thread(evaluate, symbol, df)
            if row is not None:
                state.stocks.append(row)
        except Exception as exc:  # noqa: BLE001 - one bad symbol must never stop the scan
            state.failed += 1
            logger.warning("%s: %s", symbol, exc)
        finally:
            state.processed += 1

    try:
        await asyncio.gather(*(one(s) for s in universe_loader.load_a_group_universe()))
        state.status = "done"
    except Exception as exc:  # noqa: BLE001
        state.status, state.error = "error", str(exc)
    finally:
        state.finished_at = dt.datetime.utcnow()


def start(provider: AngelOneProvider, fresh: bool = False) -> ScanState:
    global _state, _task
    if _state.status == "running":
        return _state
    if (not fresh and _state.status == "done" and _state.finished_at
            and dt.datetime.utcnow() - _state.finished_at < CACHE_TTL):
        return _state
    _state = ScanState(status="running", total=len(universe_loader.load_a_group_universe()),
                       started_at=dt.datetime.utcnow())
    _task = asyncio.create_task(_run(provider, _state))
    return _state


def get_state() -> ScanState:
    return _state


def sector_table(state: ScanState) -> list[dict]:
    groups: dict[str, list[StockRow]] = {}
    for s in state.stocks:
        groups.setdefault(s.sector, []).append(s)
    n1, n3 = state.nifty_1m or 0.0, state.nifty_3m or 0.0
    out = []
    for name, rows in groups.items():
        r1 = [r.ret_1m for r in rows if r.ret_1m is not None]
        r3 = [r.ret_3m for r in rows if r.ret_3m is not None]
        if len(r1) < MIN_SECTOR_STOCKS or len(r3) < MIN_SECTOR_STOCKS or name == "Other":
            continue
        m1, m3 = statistics.median(r1), statistics.median(r3)
        score = ((m1 - n1) + (m3 - n3)) / 2
        out.append({"sector": name, "stocks": len(rows), "ret_1m": m1, "ret_3m": m3,
                    "score": score, "strong": score > 0})
    out.sort(key=lambda r: r["score"], reverse=True)
    # Every sector beating NIFTY is strong, and the top MIN_STRONG_SECTORS always are
    # (when NIFTY itself rallies hard, "beats NIFTY" alone can leave almost nothing).
    for r in out[:MIN_STRONG_SECTORS]:
        r["strong"] = True
    return out


def snapshot(state: ScanState) -> dict:
    sectors = sector_table(state)
    strong = {s["sector"] for s in sectors if s["strong"]}
    rank = {s["sector"]: i for i, s in enumerate(sectors)}
    rows = [s for s in state.stocks if s.sector in strong and s.clusters]
    rows.sort(key=lambda r: (max(r.clusters[0]["bars_away"], 0), -r.clusters[0]["strength"], rank[r.sector]))
    return {
        "status": state.status, "total": state.total, "processed": state.processed, "failed": state.failed,
        "started_at": state.started_at, "finished_at": state.finished_at, "error": state.error,
        "nifty_1m": state.nifty_1m, "nifty_3m": state.nifty_3m,
        "sectors": sectors, "rows": [r.__dict__ for r in rows],
    }


# ---------------------------------------------------------------- single stock
async def analyse_symbol(provider: AngelOneProvider, symbol: str) -> dict:
    symbol = symbol.strip().upper()
    df = (await _daily(provider, symbol)).sort_index()
    res = gann_time.analyse(df, set(ALL_NSE_HOLIDAYS))
    if res is None:
        raise DataUnavailableError(f"Not enough daily history for '{symbol}' to find swings.")
    tail = df.iloc[-260:]
    offset = len(df) - len(tail)
    n = len(df)

    def date_of(bar: int) -> dt.date:
        return df.index[bar].date() if bar < n else res.future_dates[bar - n]

    horizon_end = n - 1 + gann_time.HORIZON_BARS
    return {
        "symbol": symbol, "company_name": company_name(symbol), "sector": "Commodity" if is_commodity(symbol) else sector_for(symbol),
        "last_date": res.last_date, "last_close": res.last_close, "new_swing_forming": res.new_swing_forming,
        "candles": [{"time": int(ts.timestamp()), "open": float(r.open), "high": float(r.high),
                     "low": float(r.low), "close": float(r.close)} for ts, r in tail.iterrows()],
        "pivots": [{"date": p.date, "kind": p.kind, "price": p.price} for p in res.pivots if p.index >= offset],
        "counts": res.counts,
        "projections": [
            {"date": date_of(p.bar), "label": p.label, "source_date": p.source_date, "count": p.count,
             "bars_away": p.bar - (n - 1)}
            for p in res.projections if n - 1 - gann_time.WINDOW_BARS <= p.bar <= horizon_end
        ],
        "clusters": [_cluster_out(c) for c in res.clusters],
    }

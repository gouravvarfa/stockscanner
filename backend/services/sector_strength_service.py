"""
Weekly Sectors (2026-11-21): fetches every sector index and every constituent from Angel One and builds the weekly
relative-strength report (backend/strategies/sector_strength.py).

Constituents come from NSE's own index files, refreshed once a day; if NSE cannot be reached (it often refuses
cloud servers) the bundled snapshot backend/data/sector_constituents.json is used. Capital Markets has no index on
Angel One, so its sector line is the equal-weight average of its stocks (and it has no RSI verdict).

A run fetches ~200 instruments (about 1-2 minutes, Angel One rate limits) as a background job the page polls; the
finished report is kept in memory for 30 minutes per as-of date, nothing is written on Render.
"""
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import io
import json
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from backend.providers import angelone_scrip_master as scrip_master
from backend.providers.angelone_provider import AngelOneProvider
from backend.strategies.sector_strength import build_report

logger = logging.getLogger("scanner.sector_strength")
IST = ZoneInfo("Asia/Kolkata")

NSE_ARCHIVES = "https://archives.nseindia.com/content/indices/"
NIFTY_INDICES = "https://www.niftyindices.com/IndexConstituent/"
SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "sector_constituents.json"

# key, label, Angel One index name (None = equal-weight line), NSE constituent file
SECTORS: list[dict[str, Any]] = [
    {"key": "psu_bank", "label": "PSU Bank", "index": "NIFTY PSU BANK", "file": NSE_ARCHIVES + "ind_niftypsubanklist.csv"},
    {"key": "bank", "label": "Banking", "index": "BANKNIFTY", "file": NSE_ARCHIVES + "ind_niftybanklist.csv"},
    {"key": "fin_service", "label": "Financial Services", "index": "FINNIFTY", "file": NSE_ARCHIVES + "ind_niftyfinancelist.csv"},
    {"key": "realty", "label": "Realty", "index": "NIFTY REALTY", "file": NSE_ARCHIVES + "ind_niftyrealtylist.csv"},
    {"key": "infra", "label": "Infrastructure", "index": "NIFTY INFRA", "file": NSE_ARCHIVES + "ind_niftyinfralist.csv"},
    {"key": "pharma", "label": "Pharma", "index": "NIFTY PHARMA", "file": NSE_ARCHIVES + "ind_niftypharmalist.csv"},
    {"key": "media", "label": "Media", "index": "NIFTY MEDIA", "file": NSE_ARCHIVES + "ind_niftymedialist.csv"},
    {"key": "capital_markets", "label": "Capital Market", "index": None, "file": NIFTY_INDICES + "ind_niftycapitalmarkets_list.csv"},
    {"key": "it", "label": "IT", "index": "NIFTY IT", "file": NSE_ARCHIVES + "ind_niftyitlist.csv"},
    {"key": "auto", "label": "Auto", "index": "NIFTY AUTO", "file": NSE_ARCHIVES + "ind_niftyautolist.csv"},
    {"key": "fmcg", "label": "FMCG", "index": "NIFTY FMCG", "file": NSE_ARCHIVES + "ind_niftyfmcglist.csv"},
    {"key": "metal", "label": "Metal", "index": "NIFTY METAL", "file": NSE_ARCHIVES + "ind_niftymetallist.csv"},
    {"key": "energy", "label": "Energy", "index": "NIFTY ENERGY", "file": NSE_ARCHIVES + "ind_niftyenergylist.csv"},
]
BENCHMARK_INDEX = "NIFTY"
INDEX_HISTORY_DAYS = 1900   # ~5 years: enough for a monthly RSI(14), one Angel One request
STOCK_HISTORY_DAYS = 60     # 1M return + holidays
CONCURRENCY = 2
REQUEST_PAUSE_S = 0.3
RETRIES = 4
RETRY_BASE_S = 2.0
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

_constituents_cache: dict[str, Any] = {}


def _parse_csv(text: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    out = [{"symbol": r["Symbol"].strip(), "name": (r.get("Company Name") or "").strip(), "industry": (r.get("Industry") or "").strip()}
           for r in rows if r.get("Symbol")]
    if not out:
        raise ValueError("no rows")
    return out


async def load_constituents() -> tuple[dict[str, list[dict[str, str]]], str]:
    """{sector key: [{symbol, name, industry}]} and where it came from ("NSE <date>" or "snapshot <date>")."""
    today = dt.date.today()
    if _constituents_cache.get("date") == today:
        return _constituents_cache["data"], _constituents_cache["source"]
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    data: dict[str, list[dict[str, str]]] = {}
    live = 0
    async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": _UA, "Accept": "text/csv,*/*"}) as client:
        for s in SECTORS:
            try:
                r = await client.get(s["file"])
                r.raise_for_status()
                data[s["key"]] = _parse_csv(r.text)
                live += 1
            except Exception as exc:  # noqa: BLE001 - NSE may refuse the server; use the bundled list
                logger.info("NSE constituents for %s not reachable (%s); using the snapshot", s["key"], exc)
                data[s["key"]] = snapshot["sectors"].get(s["key"], [])
    source = f"NSE {today.isoformat()}" if live == len(SECTORS) else (
        f"snapshot {snapshot['snapshot_date']}" if live == 0 else f"NSE {today.isoformat()} ({len(SECTORS) - live} from snapshot {snapshot['snapshot_date']})")
    _constituents_cache.update({"date": today, "data": data, "source": source})
    return data, source


def _drop_unfinished_today(df: pd.DataFrame) -> pd.DataFrame:
    """Today's daily candle counts only after the close (15:30 IST)."""
    now = dt.datetime.now(IST)
    if df.empty or now.time() >= dt.time(15, 35):
        return df
    return df[df.index.date < now.date()]


@dataclass
class SectorJob:
    job_id: str
    as_of: str
    status: str = "running"  # running | done | failed
    done: int = 0
    total: int = 0
    phase: str = "Loading NSE constituents"
    current: str = ""
    error: str | None = None
    result: dict | None = None
    started_at: str = field(default_factory=lambda: dt.datetime.now().isoformat(timespec="seconds"))

    def to_dict(self, with_result: bool = True) -> dict:
        d = {k: getattr(self, k) for k in ("job_id", "as_of", "status", "done", "total", "phase", "current", "error", "started_at")}
        if with_result and self.status == "done":
            d["result"] = self.result
        return d


_jobs: "OrderedDict[str, SectorJob]" = OrderedDict()
_results: dict[str, tuple[dt.datetime, dict]] = {}
RESULT_TTL = dt.timedelta(minutes=30)


async def _history(provider: AngelOneProvider, match: scrip_master.ScripMatch, start: dt.datetime, end: dt.datetime) -> pd.DataFrame:
    """Daily candles with patient retries: ~200 back-to-back requests trip Angel One's rate limit (HTTP 403) now and
    then; a first live run lost 34 stocks to it before these retries."""
    for attempt in range(RETRIES):
        try:
            df = await provider.get_daily_ohlc_range(match.exch_seg, match.token, start, end)
            await asyncio.sleep(REQUEST_PAUSE_S)
            return _drop_unfinished_today(df)
        except Exception:  # noqa: BLE001 - retried, then the caller records the stock as missing
            if attempt == RETRIES - 1:
                raise
            await asyncio.sleep(RETRY_BASE_S * (2 ** attempt))
    raise RuntimeError("unreachable")


async def _run(job: SectorJob, provider: AngelOneProvider, as_of: dt.date) -> None:
    constituents, source = await load_constituents()
    symbols = sorted({m["symbol"] for members in constituents.values() for m in members})
    indices = [(s["key"], s["index"]) for s in SECTORS if s["index"]] + [("__bench__", BENCHMARK_INDEX)]
    job.total = len(symbols) + len(indices)
    job.phase = "Fetching sector indices and stocks from Angel One"
    end = dt.datetime.combine(as_of, dt.time(23, 59))
    sem = asyncio.Semaphore(CONCURRENCY)
    index_data: dict[str, pd.DataFrame] = {}
    stock_data: dict[str, pd.DataFrame] = {}

    async def fetch_index(key: str, name: str) -> None:
        async with sem:
            job.current = name
            try:
                m = await scrip_master.resolve_index(name)
                if m is not None:
                    index_data[key] = await _history(provider, m, end - dt.timedelta(days=INDEX_HISTORY_DAYS), end)
            except Exception as exc:  # noqa: BLE001 - one bad instrument never stops the report
                logger.warning("sector index %s failed: %s", name, exc)
            job.done += 1

    async def fetch_stock(sym: str) -> None:
        async with sem:
            job.current = sym
            try:
                m = await scrip_master.resolve_equity(sym)
                if m is not None:
                    stock_data[sym] = await _history(provider, m, end - dt.timedelta(days=STOCK_HISTORY_DAYS), end)
            except Exception as exc:  # noqa: BLE001
                logger.warning("sector stock %s failed: %s", sym, exc)
            job.done += 1

    await asyncio.gather(*(fetch_index(k, n) for k, n in indices))
    await asyncio.gather(*(fetch_stock(s) for s in symbols))
    job.phase = "Building the report"
    sectors = [{"key": s["key"], "label": s["label"], "index_label": s["index"], "equal_weight": s["index"] is None} for s in SECTORS]
    report = build_report(pd.Timestamp(as_of), sectors, index_data, stock_data, constituents, index_data.get("__bench__"))
    report["constituents_source"] = source
    job.result = report
    _results[job.as_of] = (dt.datetime.now(), report)


def start_job(provider: AngelOneProvider, as_of: dt.date | None) -> SectorJob:
    as_of = as_of or dt.datetime.now(IST).date()
    key = as_of.isoformat()
    cached = _results.get(key)
    job = SectorJob(job_id=f"wk_{uuid.uuid4().hex[:10]}", as_of=key)
    if cached and dt.datetime.now() - cached[0] < RESULT_TTL:
        job.status, job.result, job.phase = "done", cached[1], "Done (computed a few minutes ago)"
    else:
        running = next((j for j in _jobs.values() if j.status == "running" and j.as_of == key), None)
        if running is not None:
            return running

        async def runner() -> None:
            try:
                await _run(job, provider, as_of)
                job.status, job.phase = "done", "Done"
            except Exception as exc:  # noqa: BLE001
                logger.exception("weekly sector report failed")
                job.status, job.error = "failed", str(exc)

        asyncio.get_running_loop().create_task(runner())
    _jobs[job.job_id] = job
    while len(_jobs) > 4:
        _jobs.popitem(last=False)
    return job


def get_job(job_id: str) -> SectorJob | None:
    return _jobs.get(job_id)

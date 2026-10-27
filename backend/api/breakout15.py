"""15-minute candle breakout (CALL) index-point backtest.

Standalone: its own router/engine, never imported by the strategy runner or
the scan pipeline, and it touches no other strategy's data. Historical
backtest only — nothing here can place an order. Results live in memory only
(bounded); no disk cache, so it is safe on Render's ephemeral disk.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import datetime as dt
import uuid
from collections import OrderedDict
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.providers import angelone_client
from backend.services import provider_factory
from backend.strategies.breakout15 import engine
from backend.strategies.breakout15.export import build_xlsx
from backend.strategies.breakout15.excel_import import ExcelImportError, parse_workbook

router = APIRouter(prefix="/api/breakout15", tags=["breakout15"])

IST = ZoneInfo("Asia/Kolkata")
INDEX_TOKENS = {"NIFTY": "99926000", "BANKNIFTY": "99926009"}  # NSE index tokens, Angel One scrip master
CHUNK_DAYS = 150  # 15-minute requests are capped near 200 days
CHUNK_DELAY_SECONDS = 3.0  # Angel One answers 403 to rapid back-to-back candle requests
MAX_RANGE_DAYS = 6 * 366
_jobs: "OrderedDict[str, dict]" = OrderedDict()
_results: dict[str, dict] = {}  # latest result per index


class RunRequest(BaseModel):
    symbol: str = "NIFTY"
    from_date: dt.date
    to_date: dt.date
    exit_mode: str = "CLOSE"  # CLOSE = 15:30 close (last candle) | SECOND_LAST = 15:15 (second-last candle close)


def parse_ts(raw: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    return t.astimezone(IST).replace(tzinfo=None) if t.tzinfo else t


def chunk_ranges(start: dt.date, end: dt.date) -> list[tuple[dt.datetime, dt.datetime]]:
    out, cur = [], start
    while cur <= end:
        last = min(cur + dt.timedelta(days=CHUNK_DAYS - 1), end)
        out.append((dt.datetime.combine(cur, dt.time(9, 15)), dt.datetime.combine(last, dt.time(15, 30))))
        cur = last + dt.timedelta(days=1)
    return out


def to_bars(rows: list[list], start: dt.date, end: dt.date) -> list[tuple]:
    """Raw Angel rows -> sorted unique (start_ts, o, h, l, c) inside [start, end]."""
    seen: dict[dt.datetime, tuple] = {}
    for r in rows:
        ts = parse_ts(r[0])
        if start <= ts.date() <= end:
            seen[ts] = (ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]))
    return [seen[k] for k in sorted(seen)]


async def fetch_bars(token: str, start: dt.date, end: dt.date, fetch_chunk, progress=None, delay: float = CHUNK_DELAY_SECONDS) -> list[tuple]:
    plan, rows = chunk_ranges(start, end), []
    for n, (a, b) in enumerate(plan, 1):
        if n > 1:
            await asyncio.sleep(delay)
        rows += await fetch_chunk(a, b)
        if progress:
            progress(n, len(plan))
    return to_bars(rows, start, end)


async def _run(job_id: str, req: RunRequest) -> None:
    job = _jobs[job_id]
    token = INDEX_TOKENS[req.symbol]
    try:
        provider = provider_factory.get_angelone_provider()

        async def fetch_candles(interval: str, a: dt.datetime, b: dt.datetime) -> list[list]:
            for attempt in range(3):
                try:
                    session = await provider.get_session()
                    return await angelone_client.get_candle_data(
                        session, "NSE", token, interval, a.strftime("%Y-%m-%d %H:%M"), b.strftime("%Y-%m-%d %H:%M"))
                except Exception:  # noqa: BLE001 - rate limit / transient; the last attempt re-raises
                    if attempt == 2:
                        raise
                    await asyncio.sleep(8 * (attempt + 1))
            return []

        async def fetch_chunk(a: dt.datetime, b: dt.datetime) -> list[list]:
            return await fetch_candles("FIFTEEN_MINUTE", a, b)

        bars = await fetch_bars(token, req.from_date, req.to_date, fetch_chunk,
                                progress=lambda d, t: job.update(done=d, total=t))
        if not bars:
            raise RuntimeError("Angel One returned no 15-minute candles for this range")
        # Days where one 15-minute candle broke both ends of the first candle: order the break from the real
        # 1-minute candles of just that candle, so the day gets a single CALL or PUT.
        minute_bars: dict[dt.date, list[tuple]] = {}
        todo = engine.ambiguous_candles(bars, req.exit_mode)
        job.update(phase="resolving", done=0, total=len(todo))
        for n, (day, start) in enumerate(sorted(todo.items()), 1):
            await asyncio.sleep(CHUNK_DELAY_SECONDS)
            try:
                raw = await fetch_candles("ONE_MINUTE", start, start + dt.timedelta(minutes=14))
                minute_bars[day] = to_bars(raw, day, day)
            except Exception:  # noqa: BLE001 - that day simply stays unresolved (flagged), the run continues
                minute_bars[day] = []
            job.update(done=n)
        rows, summary = engine.run_backtest(bars, req.exit_mode, minute_bars)
        _results[req.symbol] = {
            "symbol": req.symbol, "token": token, "exit_mode": req.exit_mode, "from": req.from_date.isoformat(), "to": req.to_date.isoformat(),
            "generated_at": dt.datetime.now(IST).isoformat(timespec="seconds"), "summary": summary,
            "rows": [r.as_dict() for r in rows],
        }
        job.update(state="done")
    except Exception as exc:  # noqa: BLE001 - shown in the UI
        job.update(state="error", error=str(exc))


@router.post("/runs")
async def start_run(req: RunRequest) -> dict:
    if req.symbol not in INDEX_TOKENS:
        raise HTTPException(400, f"symbol must be one of {list(INDEX_TOKENS)}")
    if req.exit_mode not in engine.EXIT_MODES:
        raise HTTPException(400, f"exit_mode must be one of {list(engine.EXIT_MODES)}")
    if req.from_date > req.to_date:
        raise HTTPException(400, "from must not be after to")
    if req.to_date >= dt.datetime.now(IST).date():
        raise HTTPException(400, "to must be before today (today's session is not complete)")
    if (req.to_date - req.from_date).days > MAX_RANGE_DAYS:
        raise HTTPException(400, "range too long (max 6 years)")
    if any(j["state"] == "running" for j in _jobs.values()):
        raise HTTPException(409, "A run is already in progress")
    jid = uuid.uuid4().hex[:8]
    _jobs[jid] = {"id": jid, "symbol": req.symbol, "state": "running", "done": 0, "total": 0, "error": None, "phase": "downloading"}
    while len(_jobs) > 10:
        _jobs.popitem(last=False)
    asyncio.create_task(_run(jid, req))
    return _jobs[jid]


@router.get("/runs/{job_id}")
async def get_run(job_id: str) -> dict:
    if job_id not in _jobs:
        raise HTTPException(404, "unknown run")
    return _jobs[job_id]


@router.get("/results/{symbol}")
async def get_result(symbol: str) -> dict:
    if symbol not in _results:
        raise HTTPException(404, "no result yet; run the backtest first")
    return _results[symbol]


class ExcelRequest(BaseModel):
    filename: str = ""
    content_base64: str


@router.post("/excel")
async def import_excel(req: ExcelRequest) -> dict:
    """Parse the user's manual trade sheet for comparison with the backtest (not stored)."""
    try:
        content = base64.b64decode(req.content_base64, validate=True)
        rows, skipped = parse_workbook(content)
    except (binascii.Error, ValueError) as exc:  # ExcelImportError is a ValueError
        raise HTTPException(400, str(exc) if isinstance(exc, ExcelImportError) else "Invalid file upload") from exc
    return {"filename": req.filename, "rows": rows, "skipped": skipped}


@router.get("/export/{symbol}")
async def export_result(symbol: str) -> Response:
    if symbol not in _results:
        raise HTTPException(404, "no result yet; run the backtest first")
    res = _results[symbol]
    name = f"breakout15_{symbol}_{res['from']}_{res['to']}.xlsx"
    return Response(
        build_xlsx(res),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )

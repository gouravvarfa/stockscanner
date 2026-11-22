"""
Background scan job API. Every scan the app can run (the Dashboard's strong-sector scan "a_group", Cup Breakout,
Value Buy) is submitted to the shared JobManager (scan_job_manager.py)
and executes via asyncio.create_task — independent of whichever frontend
page triggered it or is currently open. The frontend only starts jobs,
polls their progress, and reads results; it owns none of the execution.

Endpoints:
  POST /api/scan/start   {scan_type}         -- Normal Scan: serve a valid
                                                 24h cache if one exists,
                                                 else start a background job.
  POST /api/scan/fresh   {scan_type}         -- Fresh Scan: always starts a
                                                 new job, ignoring any cache;
                                                 replaces the cache only
                                                 after the job succeeds.
  GET  /api/scan/jobs                        -- every job this process knows
                                                 about (Part 2/6: lets a
                                                 returning page restore
                                                 running/completed jobs).
  GET  /api/scan/jobs/{job_id}               -- one job's live progress.
  GET  /api/scan/jobs/{job_id}/results       -- the job's finished result.
  POST /api/scan/jobs/{job_id}/cancel
  GET  /api/scan/cache/{scan_type}           -- the current 24h cache entry
                                                 for a scan type, if any
                                                 (lets a page show cached
                                                 results immediately on
                                                 mount without starting
                                                 anything).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config.cup_config import DEFAULT_CUP_CONFIG
from backend.services import config_store, sector_strength_service, serializers
from backend.services.cup_scan_service import run_cup_scan
from backend.services.provider_factory import get_angelone_provider
from backend.services.excel_sync.scan_sync import start_scan_sync
from backend.core.runtime import STATELESS_SERVER
from backend.services.scan_job_manager import (
    ScanAlreadyRunningError,
    TooManyConcurrentScansError,
    ScanJob,
    ScanType,
    clear_cached_result,
    get_cached_result,
    job_manager,
    set_cached_result,
)
from backend.services.scan_service import run_full_scan
from backend.services.universe_loader import load_a_group_universe

logger = logging.getLogger("scanner.scan_jobs")
router = APIRouter(prefix="/api/scan", tags=["scan-jobs"])


class StartScanRequest(BaseModel):
    scan_type: ScanType
    # Client-generated UUID (frontend: services/deviceId.ts), persisted in
    # that browser's localStorage. Purely scopes which device SEES/controls
    # this job afterwards — the scan itself still runs once, server-side,
    # regardless of who started it. Optional so older/other clients that
    # don't send it keep working exactly as before.
    device_id: str | None = None


def _estimate_total(scan_type: ScanType) -> int:
    """A cheap, no-network-call estimate of the job's total so the progress
    bar has a real denominator from the very first tick — the universe
    Excel is already cached in-process by universe_loader."""
    try:
        universe_size = len(load_a_group_universe())
    except Exception:  # noqa: BLE001
        return 0
    if scan_type == "cup_breakout":
        from backend.services.universe_loader import load_all_nse_universe

        return len(load_all_nse_universe())  # every NSE equity
    if scan_type == "a_group":
        return 0  # the stocks of today's STRONG sectors: known once the sector check is done (the job sets it)
    return universe_size  # Cup Breakout and Value Buy run over the whole A Group


async def _run_a_group_job(job: ScanJob) -> dict:
    """The Dashboard scan (2026-11-22): only the stocks of today's STRONG sectors (sector index daily, weekly and
    monthly RSI all above 60), every setup except Value Buy, which has its own page and scan over the whole A Group."""
    universe = await sector_strength_service.strong_sector_universe(get_angelone_provider())
    job.total = len(universe["symbols"])
    config = config_store.get_current_config()
    multi_strategy_config = config_store.get_current_multi_strategy_config()
    outcome = await run_full_scan(
        get_angelone_provider(), config, multi_strategy_config=multi_strategy_config,
        on_progress=lambda symbol, success, error: job.record_progress(symbol, success, error),
        on_result=job.record_result,
        symbols=universe["symbols"], value_buy_symbols=[],
    )
    # Serialization + SQLite persistence are synchronous/CPU+IO work: run
    # them off the event loop so the last stock's results and every API
    # poll stay responsive while the final aggregate is written.
    return await asyncio.to_thread(_finalize_a_group, outcome, universe)


async def _run_value_buy_job(job: ScanJob) -> dict:
    """The Value Buy page: Value Buy alone over the whole A Group universe (each stock fetched once)."""
    symbols = load_a_group_universe()
    job.total = len(symbols)
    outcome = await run_full_scan(
        get_angelone_provider(), config_store.get_current_config(),
        multi_strategy_config=config_store.get_current_multi_strategy_config(),
        on_progress=lambda symbol, success, error: job.record_progress(symbol, success, error),
        on_result=job.record_result,
        symbols=[], value_buy_symbols=symbols,
    )

    def finalize() -> dict:
        payload = serializers.scan_outcome_out(outcome).model_dump(mode="json")
        set_cached_result("value_buy", payload)
        return payload

    return await asyncio.to_thread(finalize)


async def _run_cup_breakout_job(job: ScanJob) -> dict:
    outcome = await run_cup_scan(
        get_angelone_provider(), DEFAULT_CUP_CONFIG,
        on_progress=lambda symbol, success, error: job.record_progress(symbol, success, error),
        on_result=job.record_result,
    )
    payload = {
        "started_at": outcome.started_at.isoformat(),
        "finished_at": outcome.finished_at.isoformat(),
        "execution_seconds": outcome.execution_seconds,
        "stocks_scanned": outcome.stocks_scanned,
        "stocks_failed": outcome.stocks_failed,
        "failed_symbols": outcome.failed_symbols,
        "results": outcome.results,
    }
    if STATELESS_SERVER:
        # Render keeps nothing (2026-11-17): the device saves this result in its own storage when the job
        # completes; the server forgets the previous Cup result instead of holding a copy in memory and on disk.
        clear_cached_result("cup_breakout")
    else:
        set_cached_result("cup_breakout", payload)
    return payload


def _finalize_a_group(outcome, universe: dict | None = None) -> dict:
    # 2026-09-25: no longer persisted to the server database. Every A Group
    # run used to insert a ScanRun + its result rows (full signal detail
    # JSON) into scanner.db on Render and nothing ever deleted them, so
    # server storage grew with every scan — while the UI never read them
    # (Scan History is device-local IndexedDB since the 2026-09-22
    # architecture decision; api.listHistory has no callers). Per explicit
    # user direction ("render par kuch store nahi karna, sab local device
    # par"), scan results now live only on the device. scan_id stays None;
    # every reader already treats it as optional.
    result = serializers.scan_outcome_out(outcome)
    payload = result.model_dump(mode="json")
    if universe is not None:
        # which sectors the scanned stocks came from (the Dashboard shows them; a result without this key is from
        # the old whole-A-Group scan and is never served from the cache again)
        payload["strong_sectors"] = [{k: sec[k] for k in ("key", "label", "index", "rsi")} | {"stocks": len(sec["members"])}
                                     for sec in universe["sectors"]]
        payload["strong_as_of"] = universe["as_of"]
    set_cached_result("a_group", payload)
    return payload


async def _start_job(scan_type: ScanType, device_id: str | None = None) -> ScanJob:
    if scan_type == "a_group":
        runner = _run_a_group_job
    elif scan_type == "cup_breakout":
        runner = _run_cup_breakout_job
    elif scan_type == "value_buy":
        runner = _run_value_buy_job
    else:
        raise HTTPException(status_code=400, detail=f"Unknown scan_type '{scan_type}'.")

    inner = runner

    async def runner(job: ScanJob):  # noqa: F811 — wraps the scan with the OneDrive worksheet sync
        sync = None
        try:
            sync = start_scan_sync(job.job_id, job.scan_type, job.start_time)
            job._sync = sync
        except Exception:  # noqa: BLE001 — Excel trouble must never stop a scan
            logger.exception("Excel sync setup failed; scan continues without it")
        try:
            return await inner(job)
        finally:
            if sync is not None:  # final flush in the background: the job completes without waiting for Excel
                asyncio.get_running_loop().create_task(sync.finish())

    try:
        job = job_manager.start_job(scan_type, runner, device_id=device_id)
    except ScanAlreadyRunningError as exc:
        # Structured detail — lets the frontend adopt/poll the existing job
        # directly (its job_id) instead of a separate, racy list-and-guess.
        raise HTTPException(status_code=409, detail={"message": str(exc), "job_id": exc.job_id}) from exc
    except TooManyConcurrentScansError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    job.total = _estimate_total(scan_type)
    return job


def _usable_cache(scan_type: ScanType) -> dict | None:
    """The cached result, unless it is an old whole-A-Group Dashboard result (from before 2026-11-22, no
    "strong_sectors"): the Dashboard now scans only the stocks of the STRONG sectors, so that one is never served."""
    cached = get_cached_result(scan_type)
    if cached is not None and scan_type == "a_group" and "strong_sectors" not in (cached.get("result") or {}):
        return None
    return cached


@router.post("/start")
async def start_scan(request: StartScanRequest) -> dict:
    """Normal Scan (Part 9): a valid 24h cache is served immediately with no
    new Angel One work at all; otherwise a background job starts."""
    cached = _usable_cache(request.scan_type)
    if cached is not None:
        return {"status": "cached", "cache": cached}

    job = await _start_job(request.scan_type, request.device_id)
    return {"status": "started", "job": job.to_dict()}


@router.post("/fresh")
async def fresh_scan(request: StartScanRequest) -> dict:
    """Fresh Scan (Part 9): ignores any existing cache and always starts a
    new job; that scan type's cache is replaced only once the job actually
    succeeds (see the runner functions above) — a failed/cancelled fresh
    scan never destroys a still-valid previous cache."""
    job = await _start_job(request.scan_type, request.device_id)
    return {"status": "started", "job": job.to_dict()}


@router.get("/jobs")
async def list_jobs(device_id: str | None = None) -> list[dict]:
    """With `device_id`, only that browser's own jobs are returned — this is
    what makes the Active Scans panel/dashboard device-specific instead of
    every device seeing every job the server knows about."""
    return [j.to_dict() for j in job_manager.list_jobs(device_id=device_id)]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, device_id: str | None = None) -> dict:
    job = job_manager.get(job_id, device_id=device_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No such job '{job_id}'.")
    return job.to_dict()


@router.get("/jobs/{job_id}/partial")
async def get_job_partial(job_id: str, after: int = 0) -> dict:
    """Incremental QUALIFYING results (full signal detail), newer than `after`."""
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No such job '{job_id}'.")
    return job.partial_after(max(after, 0))


@router.get("/jobs/{job_id}/progress")
async def get_job_progress(job_id: str, after: int = 0) -> dict:
    """Incremental log of EVERY processed stock (success or fail) — lets the
    browser persist a complete, gap-free local history entry per stock as
    the scan runs, independent of whether it qualified for any strategy."""
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No such job '{job_id}'.")
    return job.progress_after(max(after, 0))


@router.get("/jobs/{job_id}/results")
async def get_job_results(job_id: str) -> dict:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No such job '{job_id}'.")
    if job.status == "running":
        raise HTTPException(status_code=202, detail="Scan still running.")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"Job ended with status '{job.status}': {job.error or ''}")
    return job.result


@router.post("/jobs/{job_id}/forget")
async def forget_job(job_id: str) -> dict:
    """The device has saved this finished job's result on its own disk: drop the server's copy from memory."""
    return {"forgotten": job_manager.forget(job_id)}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, device_id: str | None = None) -> dict:
    """A device can only cancel a job it owns — cancelling with a mismatched
    (or missing, for a device-owned job) device_id fails exactly like the
    job not existing, same as GET /jobs/{job_id}."""
    if not job_manager.cancel(job_id, device_id=device_id):
        raise HTTPException(status_code=404, detail=f"No running job '{job_id}' to cancel.")
    return {"status": "cancelling"}


@router.get("/cache/{scan_type}")
async def get_cache(scan_type: ScanType) -> dict:
    cached = _usable_cache(scan_type)
    if cached is None:
        raise HTTPException(status_code=404, detail=f"No cached result for '{scan_type}'.")
    return cached


@router.delete("/cache/{scan_type}")
async def delete_cache(scan_type: ScanType) -> dict:
    clear_cached_result(scan_type)
    return {"status": "cleared"}

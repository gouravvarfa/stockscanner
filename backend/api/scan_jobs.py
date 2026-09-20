"""
Background scan job API. Every scan the app can run (A Group, Expiry Level
1, Expiry Level 5) is submitted to the shared JobManager (scan_job_manager.py)
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

# Reuse the existing per-endpoint OUT-schema serializers rather than
# duplicating them — these are the exact functions backend/api/expiry.py and
# backend/api/expiry_level_5.py already use to shape their responses.
from backend.api.expiry import _signal_out as _expiry_l1_signal_out
from backend.api.expiry_level_5 import _signal_out as _expiry_l5_signal_out
from backend.core.database import SessionLocal
from backend.schemas.expiry import ExpiryLevel1ResultOut
from backend.schemas.expiry_level_5 import ExpiryLevel5ResultOut
from backend.services import config_store, history_service, serializers
from backend.services.expiry_level_5_scan_service import run_expiry_level_5_scan
from backend.services.expiry_scan_service import run_expiry_level_1_scan
from backend.services.provider_factory import get_angelone_provider, get_market_data_router
from backend.services.excel_sync.scan_sync import start_scan_sync
from backend.services.scan_job_manager import (
    ScanAlreadyRunningError,
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


def _estimate_total(scan_type: ScanType) -> int:
    """A cheap, no-network-call estimate of the job's total so the progress
    bar has a real denominator from the very first tick — the universe
    Excel is already cached in-process by universe_loader."""
    try:
        universe_size = len(load_a_group_universe())
    except Exception:  # noqa: BLE001
        return 0
    if scan_type == "a_group":
        return universe_size
    # Expiry Level 1/5 both cap at max_stocks=40 by default, plus (for
    # Level 1) the 2 index symbols.
    return min(universe_size, 40) + (2 if scan_type == "expiry_level_1" else 0)


async def _run_a_group_job(job: ScanJob) -> dict:
    config = config_store.get_current_config()
    multi_strategy_config = config_store.get_current_multi_strategy_config()
    outcome = await run_full_scan(
        get_angelone_provider(), config, multi_strategy_config=multi_strategy_config,
        on_progress=lambda symbol, success, error: job.record_progress(symbol, success, error),
        on_result=job.record_result,
    )
    # Serialization + SQLite persistence are synchronous/CPU+IO work: run
    # them off the event loop so the last stock's results and every API
    # poll stay responsive while the final aggregate is written.
    return await asyncio.to_thread(_finalize_a_group, outcome)


def _finalize_a_group(outcome) -> dict:
    result = serializers.scan_outcome_out(outcome)

    # A dedicated session opened/closed entirely within this background
    # task — a session obtained from the POST /start request's dependency
    # would already be closed by the time this runs (the HTTP response
    # returns immediately; it does not wait for the scan to finish).
    db = SessionLocal()
    try:
        run = history_service.persist_scan(db, "manual", result)
        result.scan_id = run.id
    finally:
        db.close()

    payload = result.model_dump(mode="json")
    set_cached_result("a_group", payload)
    return payload


async def _run_expiry_level_1_job(job: ScanJob, max_stocks: int) -> dict:
    market_data_router = get_market_data_router()
    config = config_store.get_current_expiry_level_1_config()
    outcome = await run_expiry_level_1_scan(
        market_data_router, config, max_stocks=max_stocks,
        on_progress=lambda symbol, success, error: job.record_progress(symbol, success, error),
    )
    result = ExpiryLevel1ResultOut(
        started_at=outcome.started_at,
        finished_at=outcome.finished_at,
        execution_seconds=outcome.execution_seconds,
        angelone_configured=outcome.angelone_configured,
        symbols_scanned=outcome.symbols_scanned,
        symbols_failed=outcome.symbols_failed,
        failed_symbols=outcome.failed_symbols,
        index_signals=[_expiry_l1_signal_out(s) for s in outcome.index_signals],
        stock_signals=[_expiry_l1_signal_out(s) for s in outcome.stock_signals],
        data_source_summary=outcome.data_source_summary,
        errors=outcome.errors,
    )
    payload = result.model_dump(mode="json")
    set_cached_result("expiry_level_1", payload)
    return payload


async def _run_expiry_level_5_job(job: ScanJob, max_stocks: int) -> dict:
    market_data_router = get_market_data_router()
    config = config_store.get_current_expiry_level_5_config()
    outcome = await run_expiry_level_5_scan(
        market_data_router, config, max_stocks=max_stocks,
        on_progress=lambda symbol, success, error: job.record_progress(symbol, success, error),
    )
    result = ExpiryLevel5ResultOut(
        started_at=outcome.started_at,
        finished_at=outcome.finished_at,
        execution_seconds=outcome.execution_seconds,
        angelone_configured=outcome.angelone_configured,
        symbols_scanned=outcome.symbols_scanned,
        symbols_failed=outcome.symbols_failed,
        failed_symbols=outcome.failed_symbols,
        signals=[_expiry_l5_signal_out(s) for s in outcome.signals],
        data_source_summary=outcome.data_source_summary,
        errors=outcome.errors,
    )
    payload = result.model_dump(mode="json")
    set_cached_result("expiry_level_5", payload)
    return payload


def _add_signal_rows(sync, job: ScanJob, payload) -> None:
    """Expiry Level 1/5 report their signals only at the end (no per-stock
    callback carries them), so their signal rows are added from the final
    payload. A Group rows were already streamed per stock."""
    if job.scan_type == "a_group" or not isinstance(payload, dict):
        return
    from backend.services.excel_sync.rows import status_row

    signals = list(payload.get("signals", [])) + list(payload.get("stock_signals", [])) + list(payload.get("index_signals", []))
    rows = []
    for s in signals:
        key, row = status_row(sync.ctx, s.get("symbol", ""), "QUALIFIED", str(s.get("explanation") or s.get("signal") or ""))
        row[6], row[11] = job.scan_type, s.get("signal", "QUALIFIED")
        rows.append(((s.get("symbol", ""), job.scan_type, "", "QUALIFIED", str(s.get("signal_date", ""))), row))
    sync.add_rows(rows)


async def _start_job(scan_type: ScanType) -> ScanJob:
    if scan_type == "a_group":
        runner = _run_a_group_job
    elif scan_type == "expiry_level_1":
        runner = lambda job: _run_expiry_level_1_job(job, max_stocks=40)  # noqa: E731
    elif scan_type == "expiry_level_5":
        runner = lambda job: _run_expiry_level_5_job(job, max_stocks=40)  # noqa: E731
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
            result = await inner(job)
            if sync is not None:
                _add_signal_rows(sync, job, result)
            return result
        finally:
            if sync is not None:  # final flush in the background: the job completes without waiting for Excel
                asyncio.get_running_loop().create_task(sync.finish())

    try:
        job = job_manager.start_job(scan_type, runner)
    except ScanAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    job.total = _estimate_total(scan_type)
    return job


@router.post("/start")
async def start_scan(request: StartScanRequest) -> dict:
    """Normal Scan (Part 9): a valid 24h cache is served immediately with no
    new Angel One work at all; otherwise a background job starts."""
    cached = get_cached_result(request.scan_type)
    if cached is not None:
        return {"status": "cached", "cache": cached}

    job = await _start_job(request.scan_type)
    return {"status": "started", "job": job.to_dict()}


@router.post("/fresh")
async def fresh_scan(request: StartScanRequest) -> dict:
    """Fresh Scan (Part 9): ignores any existing cache and always starts a
    new job; that scan type's cache is replaced only once the job actually
    succeeds (see the runner functions above) — a failed/cancelled fresh
    scan never destroys a still-valid previous cache."""
    job = await _start_job(request.scan_type)
    return {"status": "started", "job": job.to_dict()}


@router.get("/jobs")
async def list_jobs() -> list[dict]:
    return [j.to_dict() for j in job_manager.list_jobs()]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No such job '{job_id}'.")
    return job.to_dict()


@router.get("/jobs/{job_id}/partial")
async def get_job_partial(job_id: str, after: int = 0) -> dict:
    """Incremental results: only entries newer than the `after` cursor."""
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No such job '{job_id}'.")
    return job.partial_after(max(after, 0))


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


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    if not job_manager.cancel(job_id):
        raise HTTPException(status_code=404, detail=f"No running job '{job_id}' to cancel.")
    return {"status": "cancelling"}


@router.get("/cache/{scan_type}")
async def get_cache(scan_type: ScanType) -> dict:
    cached = get_cached_result(scan_type)
    if cached is None:
        raise HTTPException(status_code=404, detail=f"No cached result for '{scan_type}'.")
    return cached


@router.delete("/cache/{scan_type}")
async def delete_cache(scan_type: ScanType) -> dict:
    clear_cached_result(scan_type)
    return {"status": "cleared"}

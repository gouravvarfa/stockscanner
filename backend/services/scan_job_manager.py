"""
Centralized background scan job manager. Every scan the app can run (A
Group, Expiry Level 1, Expiry Level 5) is submitted here as a job that
executes on the server via `asyncio.create_task` — independent of whichever
frontend page is open, and independent of each other (three jobs can run
concurrently without cancelling one another).

Deliberately minimal infrastructure: an in-process dict + the app's existing
disk/memory cache abstraction (backend/core/cache.py). No Redis, no Docker,
no new database tables — this single-process FastAPI app already owns the
one event loop every scan runs on, so a plain in-memory registry is enough,
and it's simple to reason about. Jobs (and their attached results, for the
in-flight "still running" case) live only as long as the process does; the
24-hour CACHE (separate from this registry — see get_cached_result/
set_cached_result below) is what survives a backend restart and is what a
returning page actually reads by preference.

Progress: each scan service accepts an optional `on_progress(symbol,
processed, total)` callback (backward compatible — defaults to None, so
every existing direct caller/test keeps working unchanged). This module
supplies that callback, updates the job's counters, and computes ETA from a
rolling average of per-symbol duration so a single slow/fast outlier can't
swing the estimate wildly.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from backend.core.cache import cache

logger = logging.getLogger("scanner.scan_job_manager")

ScanType = Literal["a_group", "expiry_level_1", "expiry_level_5"]
JobStatus = Literal["running", "completed", "failed", "cancelled"]

# One 24-hour cached result per scan type — Part 8/9: a "Normal Scan" reads
# this before ever starting a job; a "Fresh Scan" bypasses it and only
# overwrites it after the job succeeds. Independent keys per type, so a
# Fresh Scan of one type can never touch another type's cache.
RESULT_CACHE_TTL_SECONDS = 24 * 3600
_CACHE_KEY_PREFIX = "scan_job_result:"

# How many of the most recent per-symbol durations feed the ETA's rolling
# average — enough to smooth out one slow symbol without lagging behind a
# genuine speed change for too long.
_ETA_WINDOW = 20
_MIN_SAMPLES_FOR_ETA = 3


@dataclass
class FailedSymbol:
    symbol: str
    error: str
    timestamp: dt.datetime


@dataclass
class ScanJob:
    job_id: str
    scan_type: ScanType
    # Which browser/device started this job (a client-generated UUID the
    # frontend keeps in localStorage — see frontend/src/services/deviceId.ts).
    # Purely a VISIBILITY/ownership scope: the scan itself still runs once,
    # server-side, on Render, regardless of device_id. None means an older
    # client that didn't send one (or a legacy job from before this field
    # existed) — such jobs are never returned by device-scoped listing/
    # lookup, so they can't leak across devices either.
    device_id: str | None = None
    status: JobStatus = "running"
    start_time: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    completion_time: dt.datetime | None = None
    processed: int = 0
    total: int = 0
    successful: int = 0
    failed: int = 0
    current_symbol: str | None = None
    failed_symbols: list[FailedSymbol] = field(default_factory=list)
    error: str | None = None
    signals_found: int = 0
    partial_results: list[dict] = field(default_factory=list)  # incremental, cursor = seq — QUALIFYING stocks only, full signal detail
    progress_log: list[dict] = field(default_factory=list)  # incremental, cursor = seq — EVERY processed stock (success or fail)
    _sync: Any = field(default=None, repr=False)  # optional OneDrive worksheet sync (never affects the scan)
    result: Any = None  # the scan's own Outcome/Result object, once completed
    _durations: deque[float] = field(default_factory=lambda: deque(maxlen=_ETA_WINDOW), repr=False)
    _last_tick: float = field(default_factory=time.monotonic, repr=False)
    _task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def percentage(self) -> float:
        return round((self.processed / self.total) * 100.0, 1) if self.total else 0.0

    @property
    def elapsed_seconds(self) -> float:
        end = self.completion_time or dt.datetime.now(dt.timezone.utc)
        return (end - self.start_time).total_seconds()

    @property
    def eta_seconds(self) -> float | None:
        """None (never a fabricated number) until enough real samples exist."""
        if self.status != "running" or len(self._durations) < _MIN_SAMPLES_FOR_ETA:
            return None
        remaining = self.total - self.processed
        if remaining <= 0:
            return 0.0
        avg = sum(self._durations) / len(self._durations)
        return round(avg * remaining, 1)

    def record_progress(self, symbol: str, success: bool, error: str | None = None) -> None:
        now = time.monotonic()
        self._durations.append(now - self._last_tick)
        self._last_tick = now
        self.processed += 1
        self.current_symbol = symbol
        if self._sync is not None:
            self._sync.on_progress(symbol, success, error)  # queues in memory only; never raises
        # EVERY processed stock (success or fail), not just qualifying ones —
        # lets the browser's local history persist a complete, gap-free
        # record as each stock finishes (see frontend's useLocalHistoryWriter),
        # independent of whether it produced any strategy signal.
        from backend.services.instrument_classifier import get_instrument_type

        self.progress_log.append({
            "seq": len(self.progress_log) + 1,
            "symbol": symbol,
            "instrument_type": get_instrument_type(symbol),
            "success": success,
            "error": error,
        })
        if success:
            self.successful += 1
        else:
            self.failed += 1
            if error:
                self.failed_symbols.append(FailedSymbol(symbol, error, dt.datetime.now(dt.timezone.utc)))

    def record_result(self, symbol: str, qualifying: list[tuple[str, Any]]) -> None:
        """A stock finished and qualified for >=1 strategy: make it visible
        immediately (polled via the cursor-based /partial endpoint) instead
        of only once the whole scan completes.

        Includes each signal's FULL detail (daily/weekly/monthly RSI,
        explanation, and `extra` — which is where PRD/PRD Forming's A/B
        date/price/RSI live) — a straight reformat of data the strategy
        already computed, not a recalculation — so the browser's local
        history (see frontend/src/services/historyRowMapping.ts, which
        already knows how to parse this exact shape from the final result)
        can persist a fully-detailed row for a stock immediately, instead of
        only a bare symbol+strategy name that would need enriching later. If
        the process dies before the scan completes, whatever was already
        streamed here is what the browser already has — nothing waits for
        job completion.
        """
        if self._sync is not None:
            self._sync.on_result(symbol, qualifying)
        if not qualifying:
            return
        from backend.services.instrument_classifier import get_instrument_type
        from backend.services.serializers import _json_safe

        self.signals_found += len(qualifying)
        self.partial_results.append({
            "seq": len(self.partial_results) + 1,
            "symbol": symbol,
            "instrument_type": get_instrument_type(symbol),
            "strategies": [name for name, _ in qualifying],
            "signals": [
                {
                    "strategy": name,
                    "symbol": signal.symbol,
                    "instrument_type": getattr(signal, "instrument_type", None) or get_instrument_type(symbol),
                    "qualifies": signal.qualifies,
                    "daily_rsi": signal.daily_rsi,
                    "weekly_rsi": signal.weekly_rsi,
                    "monthly_rsi": signal.monthly_rsi,
                    "explanation": signal.explanation,
                    "extra": _json_safe(signal.extra),
                }
                for name, signal in qualifying
            ],
        })

    def partial_after(self, after: int) -> dict:
        items = self.partial_results[after:]
        return {"items": items, "next": after + len(items), "status": self.status}

    def progress_after(self, after: int) -> dict:
        items = self.progress_log[after:]
        return {"items": items, "next": after + len(items), "status": self.status}

    def to_dict(self) -> dict:
        return {
            "signals_found": self.signals_found,
            "job_id": self.job_id,
            "device_id": self.device_id,
            "scan_type": self.scan_type,
            "status": self.status,
            "start_time": self.start_time.isoformat(),
            "completion_time": self.completion_time.isoformat() if self.completion_time else None,
            "processed": self.processed,
            "total": self.total,
            "percentage": self.percentage,
            "successful": self.successful,
            "failed": self.failed,
            "current_symbol": self.current_symbol,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "eta_seconds": self.eta_seconds,
            "result_count": _result_count(self.result),
            "error": self.error,
            "failed_symbols": [
                {"symbol": f.symbol, "error": f.error, "timestamp": f.timestamp.isoformat()}
                for f in self.failed_symbols
            ],
        }


def _result_count(result: Any) -> int | None:
    """Best-effort 'how many signals/results' summary for the job list view
    — each scan type's Outcome shape differs, so this only reports what it
    can safely introspect rather than assuming a common shape."""
    if result is None:
        return None
    strategy_signals = getattr(result, "strategy_signals", None)
    if isinstance(strategy_signals, dict):
        return sum(len(v) for v in strategy_signals.values())
    stock_signals = getattr(result, "stock_signals", None)
    if isinstance(stock_signals, list):
        return len(stock_signals)
    return None


class ScanAlreadyRunningError(RuntimeError):
    def __init__(self, message: str, job_id: str):
        super().__init__(message)
        # The already-running job's id — lets the caller adopt/poll it
        # directly instead of racing a separate list-and-guess lookup.
        self.job_id = job_id


class TooManyConcurrentScansError(RuntimeError):
    pass


# Safety valve, not a business rule: each running a_group job keeps its own
# `all_results` list (every StockAnalysisResult for the whole universe) in
# memory until it finishes — genuinely unbounded concurrent devices would
# multiply that without limit and reproduce the OOM crashes this project
# already fixed once. The Angel One fetch/CPU work itself is already capped
# by a single SHARED pool (see scan_service.py's _get_shared_fetch_semaphore
# / _get_shared_cpu_pool) regardless of how many jobs are running, so this
# cap exists only to bound that per-job memory, not to protect Angel One.
MAX_CONCURRENT_JOBS_PER_SCAN_TYPE = 3


class JobManager:
    """One instance lives for the app's lifetime (module-level singleton
    below) — the in-process job registry every API route reads/writes."""

    def __init__(self) -> None:
        self._jobs: dict[str, ScanJob] = {}

    def start_job(
        self,
        scan_type: ScanType,
        runner: Callable[[ScanJob], Awaitable[Any]],
        *,
        allow_concurrent_same_type: bool = False,
        device_id: str | None = None,
    ) -> ScanJob:
        """
        `runner` is an async function that performs the actual scan and
        returns its Outcome object; it receives the ScanJob so it can call
        job.record_progress(...) as an on_progress callback and set
        job.total up front.

        Concurrency is DEVICE-scoped, not global (2026-09-22 architecture:
        multiple devices must be able to run the same scan type at the same
        time, independently — see the device-scoping work earlier). The
        same device starting the same type twice while one is already
        running is still rejected by default, since that would just be a
        redundant duplicate job for that one device, not a different
        device's scan (`allow_concurrent_same_type=True` is available for a
        caller that explicitly wants to bypass even that, same as before).
        A process-wide MAX_CONCURRENT_JOBS_PER_SCAN_TYPE cap still applies
        regardless of device, purely to bound this project's own per-job
        memory footprint (see the class comment above) — real Angel One
        request concurrency is protected separately and is unaffected by
        how many jobs are running.

        `device_id` also tags who may SEE/cancel this job afterwards (see
        list_jobs/get/cancel below).
        """
        running_same_type = [j for j in self._jobs.values() if j.scan_type == scan_type and j.status == "running"]
        if not allow_concurrent_same_type:
            same_device = next((j for j in running_same_type if j.device_id == device_id), None)
            if same_device is not None:
                raise ScanAlreadyRunningError(
                    f"A {scan_type} scan is already running for this device (job {same_device.job_id}).",
                    job_id=same_device.job_id,
                )
        if len(running_same_type) >= MAX_CONCURRENT_JOBS_PER_SCAN_TYPE:
            raise TooManyConcurrentScansError(
                f"Too many {scan_type} scans are already running right now "
                f"({len(running_same_type)}/{MAX_CONCURRENT_JOBS_PER_SCAN_TYPE}). Please try again shortly."
            )

        job = ScanJob(job_id=f"scan_{uuid.uuid4().hex[:10]}", scan_type=scan_type, device_id=device_id)
        self._jobs[job.job_id] = job

        async def _execute() -> None:
            try:
                result = await runner(job)
                job.result = result
                job.status = "completed"
            except asyncio.CancelledError:
                job.status = "cancelled"
                raise
            except Exception as exc:  # noqa: BLE001 — one job's failure must never crash the app
                logger.exception("Scan job %s (%s) failed", job.job_id, scan_type)
                job.status = "failed"
                job.error = str(exc)
            finally:
                job.completion_time = dt.datetime.now(dt.timezone.utc)

        job._task = asyncio.create_task(_execute())
        return job

    def get(self, job_id: str, *, device_id: str | None = None) -> ScanJob | None:
        """With `device_id`, only returns the job if it belongs to that
        device — a mismatch (or a legacy job with no device_id at all) is
        treated exactly like "doesn't exist", so one device can never probe
        for another device's live job by guessing/reusing a job id."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if device_id is not None and job.device_id != device_id:
            return None
        return job

    def list_jobs(self, *, device_id: str | None = None) -> list[ScanJob]:
        """With `device_id`, only that device's own jobs are returned —
        legacy jobs started before this field existed (device_id is None)
        are excluded from a device-scoped listing rather than shown to
        everyone, per explicit backward-compatibility requirement."""
        jobs = self._jobs.values()
        if device_id is not None:
            jobs = [j for j in jobs if j.device_id == device_id]
        return sorted(jobs, key=lambda j: j.start_time, reverse=True)

    def cancel(self, job_id: str, *, device_id: str | None = None) -> bool:
        job = self.get(job_id, device_id=device_id)
        if job is None or job.status != "running" or job._task is None:
            return False
        job._task.cancel()
        return True


job_manager = JobManager()


# ---- 24-hour result cache (Part 8/9/12) -----------------------------------

def _cache_key(scan_type: ScanType) -> str:
    return f"{_CACHE_KEY_PREFIX}{scan_type}"


_DISK_CACHE_DIR = Path("data/scan_cache")


def _disk_path(scan_type: ScanType) -> Path:
    return _DISK_CACHE_DIR / f"{scan_type}.json"


def get_cached_result(scan_type: ScanType) -> dict | None:
    """Returns the cached envelope {result, data_timestamp, completed_at,
    provider, scan_type} or None if there is no valid (unexpired) cache.
    Read-through: the in-process cache is backed by a JSON file so a backend
    restart no longer throws away a still-valid 24h result."""
    hit = cache.get(_cache_key(scan_type))
    if hit is not None:
        return hit
    try:
        envelope = json.loads(_disk_path(scan_type).read_text(encoding="utf-8"))
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(envelope["completed_at"])).total_seconds()
        if age >= RESULT_CACHE_TTL_SECONDS:
            return None
        cache.set(_cache_key(scan_type), envelope, int(RESULT_CACHE_TTL_SECONDS - age))
        return envelope
    except (OSError, ValueError, KeyError):
        return None


def set_cached_result(scan_type: ScanType, result: Any, provider: str = "ANGEL_ONE") -> None:
    now = dt.datetime.now(dt.timezone.utc)
    envelope = {
        "scan_type": scan_type,
        "result": result,
        "data_timestamp": now.isoformat(),
        "completed_at": now.isoformat(),
        "provider": provider,
    }
    cache.set(_cache_key(scan_type), envelope, RESULT_CACHE_TTL_SECONDS)
    try:
        _DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _disk_path(scan_type).write_text(json.dumps(envelope), encoding="utf-8")
    except (OSError, TypeError) as exc:  # disk persistence is best-effort
        logger.warning("Could not persist %s scan cache to disk: %s", scan_type, exc)


def clear_cached_result(scan_type: ScanType) -> None:
    cache.delete(_cache_key(scan_type))
    try:
        _disk_path(scan_type).unlink()
    except OSError:
        pass

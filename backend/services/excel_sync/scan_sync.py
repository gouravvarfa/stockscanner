"""
Per-scan worksheet sync. NEVER blocks or fails the scanner: the scanner-facing
methods are synchronous and non-raising (rows are only queued in memory); a
background task creates the worksheet at scan start and flushes queued rows
in BATCHES (one Graph request per contiguous batch, not one per stock).
Rows get their sheet row number when first queued and keep it across
retries, so a retry rewrites the same cells — it can never duplicate a row.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any

from backend.services.excel_sync.graph_backend import WorkbookBackend, get_default_backend
from backend.services.excel_sync.naming import worksheet_name
from backend.services.excel_sync.rows import RowContext, signal_rows, status_row

logger = logging.getLogger("scanner.excel_sync")

FLUSH_INTERVAL_SECONDS = 2.0
MAX_ROWS_PER_REQUEST = 200
MAX_NAME_ATTEMPTS = 50

# scan_id -> sheet name (the same scan never creates a second worksheet)
_sheet_by_scan: dict[str, str] = {}


class ScanSheetSync:
    def __init__(self, backend: WorkbookBackend, scan_id: str, scan_type: str, started_at: dt.datetime,
                 flush_interval: float = FLUSH_INTERVAL_SECONDS):
        self.backend = backend
        self.scan_id = scan_id
        self.started_at = started_at
        self.ctx = RowContext(scan_id, scan_type, started_at)
        self.flush_interval = flush_interval
        self.sheet_name: str | None = _sheet_by_scan.get(scan_id)
        self._row_by_key: dict[tuple, int] = {}
        self._values: dict[int, list[Any]] = {}  # row number -> latest values
        self._dirty: set[int] = set()
        self._next_row = 2  # row 1 = headers
        self._pending_qualifying: dict[str, list[tuple[str, Any]]] = {}
        self._wake = asyncio.Event()
        self._closing = False
        self._task: asyncio.Task | None = None
        self.failures = 0

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        """Called at scan start: schedules worksheet creation + the flusher; returns immediately."""
        try:
            self._task = asyncio.get_running_loop().create_task(self._run())
        except RuntimeError:  # no running loop — sync stays off, scanner unaffected
            logger.warning("Excel sync could not start (no running event loop)")

    async def finish(self, timeout: float = 60.0) -> None:
        """Flush everything still queued, then stop. Meant to run as a background task; never raises."""
        self._closing = True
        self._wake.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Excel sync final flush did not complete: %s", exc)

    # ---- scanner-facing hooks (sync, cheap, non-raising) ------------------
    def on_result(self, symbol: str, qualifying: list[tuple[str, Any]]) -> None:
        try:
            if qualifying:
                self._pending_qualifying[symbol] = qualifying
        except Exception:  # noqa: BLE001
            logger.exception("excel sync on_result failed")

    def on_progress(self, symbol: str, success: bool, error: str | None) -> None:
        try:
            if not success:
                self._enqueue([status_row(self.ctx, symbol, "DATA_UNAVAILABLE", error or "")])
                return
            rows: list[tuple[tuple, list[Any]]] = []
            for name, signal in self._pending_qualifying.pop(symbol, []):
                rows.extend(signal_rows(self.ctx, symbol, name, signal))
            self._enqueue(rows or [status_row(self.ctx, symbol, "SCANNED_NO_SIGNAL")])
        except Exception:  # noqa: BLE001
            logger.exception("excel sync on_progress failed")

    def add_rows(self, rows: list[tuple[tuple, list[Any]]]) -> None:
        try:
            self._enqueue(rows)
        except Exception:  # noqa: BLE001
            logger.exception("excel sync add_rows failed")

    def _enqueue(self, rows: list[tuple[tuple, list[Any]]]) -> None:
        for key, values in rows:
            row = self._row_by_key.get(key)
            if row is None:
                row = self._next_row
                self._next_row += 1
                self._row_by_key[key] = row
            self._values[row] = values  # same key again = same row, never a duplicate
            self._dirty.add(row)
        self._wake.set()

    # ---- background ------------------------------------------------------
    async def _create_sheet(self) -> bool:
        if self.sheet_name:  # this scan already owns a sheet: reuse it
            return True
        for attempt in range(MAX_NAME_ATTEMPTS):
            name = worksheet_name(self.started_at, attempt)
            if await self.backend.create_sheet(name):
                self.sheet_name = name
                _sheet_by_scan[self.scan_id] = name
                return True
        return False

    async def _run(self) -> None:
        delay = 1.0
        while not self.sheet_name:
            try:
                if await self._create_sheet():
                    break
            except Exception as exc:  # noqa: BLE001
                self.failures += 1
                logger.warning("Excel sync: worksheet creation failed (%s); retrying", exc)
            if self._closing and self.failures > 8:
                return
            await asyncio.sleep(min(delay, 15.0))
            delay *= 2
        delay = 1.0
        while True:
            if not self._dirty:
                if self._closing:
                    return
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=self.flush_interval)
                except asyncio.TimeoutError:
                    pass
                if not self._dirty:
                    continue
                if not self._closing:
                    await asyncio.sleep(self.flush_interval)  # let several stocks batch into one request
            try:
                await self._flush()
                delay = 1.0
            except Exception as exc:  # noqa: BLE001 — sync trouble must never touch the scan
                self.failures += 1
                logger.warning("Excel sync flush failed (%s); will retry the same rows", exc)
                if self._closing and self.failures > 8:
                    return
                await asyncio.sleep(min(delay, 15.0))
                delay *= 2

    async def _flush(self) -> None:
        runs: list[list[int]] = []
        for r in sorted(self._dirty):
            if runs and r == runs[-1][-1] + 1 and len(runs[-1]) < MAX_ROWS_PER_REQUEST:
                runs[-1].append(r)
            else:
                runs.append([r])
        for run in runs:
            await self.backend.write_rows(self.sheet_name, run[0], [self._values[r] for r in run])
            self._dirty.difference_update(run)  # cleared only after a successful write


def start_scan_sync(scan_id: str, scan_type: str, started_at: dt.datetime,
                    backend: WorkbookBackend | None = None) -> ScanSheetSync | None:
    """Returns a started sync, or None when OneDrive sync isn't configured."""
    backend = backend or get_default_backend()
    if backend is None:
        return None
    sync = ScanSheetSync(backend, scan_id, scan_type, started_at)
    sync.start()
    return sync

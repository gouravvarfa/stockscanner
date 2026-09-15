"""
In-memory ring buffer of recent log records, so the frontend can show a
live logs panel via simple polling — no new infra (WebSocket/SSE broker)
needed for a single-user local app. Bounded so a long-running scan can
never grow this unboundedly.
"""
from __future__ import annotations

import datetime as dt
import itertools
import logging
from collections import deque
from dataclasses import dataclass

_MAX_ENTRIES = 1000

_counter = itertools.count(1)


@dataclass
class LogEntry:
    id: int
    timestamp: str
    level: str
    logger: str
    message: str


_buffer: deque[LogEntry] = deque(maxlen=_MAX_ENTRIES)


class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001 — a bad log call must never crash the app
            message = record.getMessage()
        _buffer.append(
            LogEntry(
                id=next(_counter),
                timestamp=dt.datetime.utcnow().isoformat(),
                level=record.levelname,
                logger=record.name,
                message=message,
            )
        )


def install() -> None:
    """Call once at app startup (backend/main.py)."""
    handler = _BufferHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)


def get_entries_since(since_id: int) -> list[LogEntry]:
    return [e for e in _buffer if e.id > since_id]


def get_recent(limit: int = 200) -> list[LogEntry]:
    return list(_buffer)[-limit:]

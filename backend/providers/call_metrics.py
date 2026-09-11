"""
Counts REAL provider calls so quota usage is observable instead of estimated.

Tapetide's free tier allows 50 MCP tool calls per day, resetting at 00:00 IST
(that's what its own rate-limit message states), so the counter rolls over on
the IST calendar day rather than UTC. Counts are persisted to a small JSON
file so a backend restart doesn't silently reset today's usage — the quota it
tracks is enforced server-side and does not restart with us.

Nothing here ever issues a call of its own; every number is recorded by the
code paths already making the calls.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
METRICS_PATH = Path(".provider_call_metrics.json")

TAPETIDE_DAILY_QUOTA = 50


def _today_ist() -> str:
    return dt.datetime.now(IST).date().isoformat()


@dataclass
class CallMetrics:
    day: str
    tapetide_calls: int = 0
    tapetide_cache_hits: int = 0
    tapetide_cache_misses: int = 0
    angelone_calls: int = 0
    fallbacks: int = 0

    @property
    def tapetide_quota_remaining(self) -> int:
        return max(0, TAPETIDE_DAILY_QUOTA - self.tapetide_calls)

    @property
    def cache_hit_rate_pct(self) -> float:
        total = self.tapetide_cache_hits + self.tapetide_cache_misses
        return round(self.tapetide_cache_hits / total * 100, 1) if total else 0.0


_lock = Lock()
_metrics: CallMetrics | None = None


def _load() -> CallMetrics:
    today = _today_ist()
    if METRICS_PATH.exists():
        try:
            data = json.loads(METRICS_PATH.read_text())
            if data.get("day") == today:
                return CallMetrics(**data)
        except (json.JSONDecodeError, TypeError):
            pass  # a corrupt counter file must never break a scan — start fresh
    return CallMetrics(day=today)


def _save(metrics: CallMetrics) -> None:
    try:
        METRICS_PATH.write_text(json.dumps(asdict(metrics), indent=2))
    except OSError:
        pass  # metrics are diagnostics; failing to persist them must not break a scan


def _bump(field: str, amount: int = 1) -> None:
    global _metrics
    with _lock:
        if _metrics is None or _metrics.day != _today_ist():
            _metrics = _load()
        setattr(_metrics, field, getattr(_metrics, field) + amount)
        _save(_metrics)


def record_tapetide_call() -> None:
    """One real MCP tool call actually sent to Tapetide (counts against the 50/day quota)."""
    _bump("tapetide_calls")


def record_tapetide_cache_hit() -> None:
    _bump("tapetide_cache_hits")


def record_tapetide_cache_miss() -> None:
    _bump("tapetide_cache_misses")


def record_angelone_call() -> None:
    """One real HTTP call to Angel One (no daily cap, but rate-limited per second)."""
    _bump("angelone_calls")


def record_fallback() -> None:
    """One provider fallback actually taken (preferred provider failed, the other served it)."""
    _bump("fallbacks")


def snapshot() -> CallMetrics:
    global _metrics
    with _lock:
        if _metrics is None or _metrics.day != _today_ist():
            _metrics = _load()
        return CallMetrics(**asdict(_metrics))


def reset_for_tests() -> None:
    global _metrics
    with _lock:
        _metrics = CallMetrics(day=_today_ist())

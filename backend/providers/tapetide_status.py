"""
Tracks Tapetide's last-observed real status from actual calls already being
made elsewhere — never spends an extra call just to check status (that would
waste the daily quota it's trying to report on).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

_QUOTA_MARKER = "reached the Tapetide free tier limit"


@dataclass
class TapetideStatus:
    state: str  # "UNKNOWN" | "OK" | "RATE_LIMITED" | "DISCONNECTED" | "RECONNECTED"
    last_updated: dt.datetime | None
    detail: str | None


_status = TapetideStatus(state="UNKNOWN", last_updated=None, detail=None)


def record_success() -> None:
    global _status
    _status = TapetideStatus(state="OK", last_updated=dt.datetime.utcnow(), detail=None)


def record_error(message: str) -> None:
    global _status
    if _QUOTA_MARKER in message:
        _status = TapetideStatus(state="RATE_LIMITED", last_updated=dt.datetime.utcnow(), detail=message[:200])
    else:
        # A non-quota error doesn't necessarily mean the provider is down —
        # leave state as-is unless we have no prior signal at all (RECONNECTED
        # counts as "no confirmed signal yet" here too).
        if _status.state in ("UNKNOWN", "RECONNECTED"):
            _status = TapetideStatus(state="UNKNOWN", last_updated=dt.datetime.utcnow(), detail=message[:200])


def record_reconnected() -> None:
    """
    Session was just rebuilt. Distinct from plain "UNKNOWN" (no signal yet)
    so the UI can show a clear positive confirmation right after a manual
    reconnect, instead of an ambiguous state that looks unchanged and invites
    repeated clicking — the next real tool call still confirms it actually
    works and will move this to OK/RATE_LIMITED as usual.
    """
    global _status
    _status = TapetideStatus(state="RECONNECTED", last_updated=dt.datetime.utcnow(), detail="Session reconnected — awaiting next call")


def record_disconnected(message: str) -> None:
    """
    The underlying MCP session itself failed (transport-level — a dropped
    connection, not a tool returning an error). This is distinct from
    RATE_LIMITED/UNKNOWN: the session needs to be rebuilt (see
    provider_factory.reconnect_tapetide), not just retried.
    """
    global _status
    _status = TapetideStatus(state="DISCONNECTED", last_updated=dt.datetime.utcnow(), detail=message[:200])


def get_status() -> TapetideStatus:
    return _status

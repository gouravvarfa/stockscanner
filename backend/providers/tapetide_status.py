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
    state: str  # "UNKNOWN" | "OK" | "RATE_LIMITED"
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
        # leave state as-is unless we have no prior signal at all.
        if _status.state == "UNKNOWN":
            _status = TapetideStatus(state="UNKNOWN", last_updated=dt.datetime.utcnow(), detail=message[:200])


def get_status() -> TapetideStatus:
    return _status

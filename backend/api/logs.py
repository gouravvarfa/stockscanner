from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core import log_buffer

router = APIRouter(prefix="/api/logs", tags=["logs"])


class LogEntryOut(BaseModel):
    id: int
    timestamp: str
    level: str
    logger: str
    message: str


@router.get("", response_model=list[LogEntryOut])
def get_logs(since_id: int = 0, limit: int = 200) -> list[log_buffer.LogEntry]:
    if since_id > 0:
        return log_buffer.get_entries_since(since_id)
    return log_buffer.get_recent(limit)

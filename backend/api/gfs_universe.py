"""Shared "All Stocks" endpoints for the GFS, Advanced GFS and 50 GFS routers."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services import gfs_universe_service as service
from backend.services.provider_factory import get_angelone_provider


class UniverseRowOut(BaseModel):
    symbol: str
    company_name: str
    data_from: dt.date
    data_to: dt.date
    close: float
    daily_rsi: float | None
    weekly_rsi: float | None
    monthly_rsi: float | None
    in_setup_since: dt.date


class UniverseOut(BaseModel):
    status: str
    total: int
    processed: int
    failed: int
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    error: str | None
    rows: list[UniverseRowOut]


class UniverseStartRequest(BaseModel):
    fresh: bool = False


def _out(state: service.UniverseState) -> UniverseOut:
    return UniverseOut(
        status=state.status, total=state.total, processed=state.processed, failed=state.failed,
        started_at=state.started_at, finished_at=state.finished_at, error=state.error,
        rows=[UniverseRowOut(**r.__dict__) for r in state.rows],
    )


def add_universe_routes(router: APIRouter, variant: str) -> None:
    @router.post("/universe/start", response_model=UniverseOut)
    async def start_universe(request: UniverseStartRequest | None = None) -> UniverseOut:
        fresh = request.fresh if request else False
        return _out(service.start(variant, get_angelone_provider(), fresh=fresh))

    @router.get("/universe", response_model=UniverseOut)
    async def universe_status() -> UniverseOut:
        return _out(service.get_state(variant))

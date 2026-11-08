from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.gfs_universe import add_universe_routes
from backend.api.system_one_backtest import serialize_backtest
from backend.schemas.gfs_backtest import GFSBacktestRequest
from backend.schemas.system_one_backtest import SystemOneBacktestOut
from backend.services import gfs_backtest_service as service
from backend.services.provider_factory import get_angelone_provider
from backend.services.top_bottom_backtest_service import InsufficientDataError, TopBottomValidationError

router = APIRouter(prefix="/api/gfs", tags=["gfs"])
add_universe_routes(router, "gfs")


@router.post("/backtest", response_model=SystemOneBacktestOut)
async def run_backtest(request: GFSBacktestRequest) -> SystemOneBacktestOut:
    try:
        stored = await service.run_for_symbol(get_angelone_provider(), request.symbol, request.from_date, request.to_date)
    except TopBottomValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InsufficientDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — one bad symbol/response must never crash the app
        raise HTTPException(status_code=502, detail=f"Angel One error: {exc}") from exc
    out = serialize_backtest(stored)
    out.note = service.PNL_NOTE
    return out


@router.get("/backtest/{backtest_id}/export")
async def export_backtest(backtest_id: str):
    return service.export_response(backtest_id, "GFS", "gfs")

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.system_one_backtest import serialize_backtest
from backend.config.strategy_config import DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG
from backend.schemas.gfs_backtest import GFSBacktestRequest
from backend.schemas.system_one_backtest import SystemOneBacktestOut
from backend.services import gfs_backtest_service as service
from backend.services.provider_factory import get_angelone_provider
from backend.services.top_bottom_backtest_service import InsufficientDataError, TopBottomValidationError
from backend.strategies.gfs_backtest import run_advanced_gfs_backtest

router = APIRouter(prefix="/api/advanced-gfs", tags=["advanced-gfs"])


@router.post("/backtest", response_model=SystemOneBacktestOut)
async def run_backtest(request: GFSBacktestRequest) -> SystemOneBacktestOut:
    try:
        stored = await service.run_for_symbol(
            get_angelone_provider(), request.symbol, request.from_date, request.to_date,
            config=DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG, runner=run_advanced_gfs_backtest,
        )
    except TopBottomValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InsufficientDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - one bad symbol/response must never crash the app
        raise HTTPException(status_code=502, detail=f"Angel One error: {exc}") from exc
    out = serialize_backtest(stored)
    out.note = service.PNL_NOTE
    return out

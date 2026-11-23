from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.providers.market_data_router import DataUnavailableError
from backend.services import thrust_service as svc
from backend.services.provider_factory import get_angelone_provider

router = APIRouter(prefix="/api/thrust", tags=["thrust"])


@router.get("/stock/{symbol}")
async def stock(symbol: str) -> dict:
    try:
        return await svc.analyse_symbol(get_angelone_provider(), symbol)
    except (DataUnavailableError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Angel One error: {exc}") from exc

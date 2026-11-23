from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.providers.market_data_router import DataUnavailableError
from backend.services import outlook_service
from backend.services.provider_factory import get_angelone_provider

router = APIRouter(prefix="/api/outlook", tags=["outlook"])


@router.get("")
async def outlook() -> dict:
    """Nifty's VIX range and market weather, plus Gold/Silver ranges - live from Angel One."""
    try:
        return await outlook_service.snapshot(get_angelone_provider())
    except DataUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Angel One error: {exc}") from exc

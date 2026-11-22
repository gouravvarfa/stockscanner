from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.providers.market_data_router import DataUnavailableError
from backend.services import gann_time_service as svc
from backend.services.provider_factory import get_angelone_provider

router = APIRouter(prefix="/api/gann-time", tags=["gann-time"])


@router.get("/search")
def search(q: str) -> list[dict]:
    return svc.search_nse(q)


@router.post("/sectors/start")
async def start(fresh: bool = False) -> dict:
    return svc.snapshot(svc.start(get_angelone_provider(), fresh))


@router.get("/sectors")
def sectors() -> dict:
    return svc.snapshot(svc.get_state())


@router.get("/stock/{symbol}")
async def stock(symbol: str) -> dict:
    try:
        return await svc.analyse_symbol(get_angelone_provider(), symbol)
    except DataUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Angel One error: {exc}") from exc

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.schemas.scan import ScanResultOut
from backend.services import config_store, history_service, serializers
from backend.services.provider_factory import get_angelone_provider, get_market_data_router, get_provider
from backend.services.scan_service import run_full_scan

router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.post("/run", response_model=ScanResultOut)
async def run_scan(scan_type: str = "manual", db: Session = Depends(get_db)) -> ScanResultOut:
    provider = get_provider()
    config = config_store.get_current_config()
    multi_strategy_config = config_store.get_current_multi_strategy_config()
    data_source_mode = config_store.get_current_data_source_config().mode
    try:
        outcome = await run_full_scan(
            provider, config, multi_strategy_config=multi_strategy_config,
            market_data_router=get_market_data_router(), data_source_mode=data_source_mode,
            angelone_provider=get_angelone_provider(),
        )
    except RuntimeError as exc:
        # Surfaces Tapetide-side failures (e.g. daily MCP call quota exhausted)
        # as a clean 502 instead of an unhandled 500 that browsers report as
        # a bare "Failed to fetch".
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result = serializers.scan_outcome_out(outcome)
    run = history_service.persist_scan(db, scan_type, result)
    result.scan_id = run.id
    return result

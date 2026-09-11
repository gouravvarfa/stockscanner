from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config.expiry_level_1_config import ExpiryLevel1Config
from backend.schemas.expiry import ExpiryLevel1ResultOut, ExpiryLevel1SignalOut
from backend.services import config_store
from backend.services.expiry_scan_service import ExpiryLevel1Signal, run_expiry_level_1_scan
from backend.services.provider_factory import get_market_data_router, get_provider

router = APIRouter(prefix="/api/expiry", tags=["expiry-level-1"])


def _signal_out(signal: ExpiryLevel1Signal) -> ExpiryLevel1SignalOut:
    return ExpiryLevel1SignalOut(
        symbol=signal.symbol,
        instrument_type=signal.instrument_type,
        name=signal.name,
        sector=signal.sector,
        signal_date=signal.signal_date.to_pydatetime(),
        rsi_15m=signal.rsi_15m,
        rsi_15m_prev=signal.rsi_15m_prev,
        rsi_1h=signal.rsi_1h,
        status=signal.status,
        explanation=signal.explanation,
    )


@router.post("/scan", response_model=ExpiryLevel1ResultOut)
async def run_scan(max_stocks: int = 40) -> ExpiryLevel1ResultOut:
    tapetide = get_provider()
    market_data_router = get_market_data_router()
    config = config_store.get_current_expiry_level_1_config()
    data_source_mode = config_store.get_current_data_source_config().mode

    try:
        outcome = await run_expiry_level_1_scan(
            tapetide, market_data_router, config, max_stocks=max_stocks, data_source_mode=data_source_mode
        )
    except RuntimeError as exc:
        # Belt-and-braces: run_expiry_level_1_scan already isolates known
        # failure points (Tapetide universe, Angel One not configured,
        # per-symbol errors), but any other unexpected failure should still
        # come back as a clean 502, not a bare "Failed to fetch".
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ExpiryLevel1ResultOut(
        started_at=outcome.started_at,
        finished_at=outcome.finished_at,
        execution_seconds=outcome.execution_seconds,
        angelone_configured=outcome.angelone_configured,
        symbols_scanned=outcome.symbols_scanned,
        symbols_failed=outcome.symbols_failed,
        failed_symbols=outcome.failed_symbols,
        index_signals=[_signal_out(s) for s in outcome.index_signals],
        stock_signals=[_signal_out(s) for s in outcome.stock_signals],
        data_source_mode=outcome.data_source_mode.upper(),
        data_source_summary=outcome.data_source_summary,
        errors=outcome.errors,
    )


@router.get("/config", response_model=ExpiryLevel1Config)
def get_config() -> ExpiryLevel1Config:
    return config_store.get_current_expiry_level_1_config()


@router.put("/config", response_model=ExpiryLevel1Config)
def update_config(new_config: ExpiryLevel1Config) -> ExpiryLevel1Config:
    return config_store.update_expiry_level_1_config(new_config)


@router.post("/config/reset", response_model=ExpiryLevel1Config)
def reset_config() -> ExpiryLevel1Config:
    return config_store.reset_expiry_level_1_config()

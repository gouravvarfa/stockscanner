from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config.expiry_level_5_config import ExpiryLevel5Config
from backend.schemas.expiry_level_5 import CandleOut, ExpiryLevel5ResultOut, ExpiryLevel5SignalOut
from backend.services import config_store
from backend.services.expiry_level_5_scan_service import ExpiryLevel5Signal, run_expiry_level_5_scan
from backend.services.provider_factory import get_market_data_router, get_provider

router = APIRouter(prefix="/api/expiry-level-5", tags=["expiry-level-5"])


def _signal_out(signal: ExpiryLevel5Signal) -> ExpiryLevel5SignalOut:
    return ExpiryLevel5SignalOut(
        strategy=signal.strategy,
        signal=signal.signal,
        symbol=signal.symbol,
        instrument_type=signal.instrument_type,
        signal_date=signal.signal_date.to_pydatetime(),
        swing_high=signal.swing_high,
        swing_low=signal.swing_low,
        fib_38_2=signal.fib_38_2,
        fib_50=signal.fib_50,
        fib_61_8=signal.fib_61_8,
        support_price=signal.support_price,
        support_confirmed=signal.support_confirmed,
        confirmation_candle=CandleOut(**signal.confirmation_candle),
        previous_candle_high=signal.previous_candle_high,
        confirmation_close_above_previous_high=signal.confirmation_close_above_previous_high,
        reason=signal.reason,
    )


@router.post("/scan", response_model=ExpiryLevel5ResultOut)
async def run_scan(max_stocks: int = 40) -> ExpiryLevel5ResultOut:
    tapetide = get_provider()
    market_data_router = get_market_data_router()
    config = config_store.get_current_expiry_level_5_config()
    data_source_mode = config_store.get_current_data_source_config().mode

    try:
        outcome = await run_expiry_level_5_scan(
            tapetide, market_data_router, config, max_stocks=max_stocks, data_source_mode=data_source_mode
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ExpiryLevel5ResultOut(
        started_at=outcome.started_at,
        finished_at=outcome.finished_at,
        execution_seconds=outcome.execution_seconds,
        angelone_configured=outcome.angelone_configured,
        symbols_scanned=outcome.symbols_scanned,
        symbols_failed=outcome.symbols_failed,
        failed_symbols=outcome.failed_symbols,
        signals=[_signal_out(s) for s in outcome.signals],
        data_source_mode=outcome.data_source_mode.upper(),
        data_source_summary=outcome.data_source_summary,
        errors=outcome.errors,
    )


@router.get("/config", response_model=ExpiryLevel5Config)
def get_config() -> ExpiryLevel5Config:
    return config_store.get_current_expiry_level_5_config()


@router.put("/config", response_model=ExpiryLevel5Config)
def update_config(new_config: ExpiryLevel5Config) -> ExpiryLevel5Config:
    return config_store.update_expiry_level_5_config(new_config)


@router.post("/config/reset", response_model=ExpiryLevel5Config)
def reset_config() -> ExpiryLevel5Config:
    return config_store.reset_expiry_level_5_config()

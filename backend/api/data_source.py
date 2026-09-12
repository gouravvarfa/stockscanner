from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config.data_source_config import DataSourceConfig
from backend.providers import call_metrics, tapetide_status
from backend.services import angelone_credential_store, config_store, provider_factory

router = APIRouter(prefix="/api/data-source", tags=["data-source"])


@router.get("", response_model=DataSourceConfig)
def get_data_source() -> DataSourceConfig:
    return config_store.get_current_data_source_config()


@router.put("", response_model=DataSourceConfig)
def update_data_source(new_config: DataSourceConfig) -> DataSourceConfig:
    return config_store.update_data_source_config(new_config)


class ProviderStatusOut(BaseModel):
    name: str
    status: str  # "OK" | "RATE_LIMITED" | "CONNECTED" | "NOT_CONFIGURED" | "UNKNOWN"
    detail: str | None


@router.get("/providers", response_model=list[ProviderStatusOut])
def get_provider_status() -> list[ProviderStatusOut]:
    """
    Real, observed status — never a fabricated indicator. Tapetide's state
    reflects the outcome of calls already made elsewhere in this session (no
    extra call is spent just to check), Angel One's reflects whether a
    verified connection is currently saved.
    """
    tp = tapetide_status.get_status()
    creds = angelone_credential_store.get_credentials()

    return [
        ProviderStatusOut(name="TAPETIDE", status=tp.state, detail=tp.detail),
        ProviderStatusOut(
            name="ANGEL_ONE",
            status="CONNECTED" if creds else "NOT_CONFIGURED",
            detail=f"Connected as {creds.client_code}" if creds else None,
        ),
    ]


@router.post("/tapetide/reconnect", response_model=ProviderStatusOut)
async def reconnect_tapetide() -> ProviderStatusOut:
    """
    Rebuilds the Tapetide MCP session in place — no server restart needed.
    Use this when the Providers panel shows Tapetide as DISCONNECTED (its
    long-lived session dropped and stopped recovering on its own).
    """
    try:
        await provider_factory.reconnect_tapetide()
    except Exception as exc:  # noqa: BLE001 — surfaced to the UI as a clear failure, not a 500 crash
        raise HTTPException(status_code=502, detail=f"Tapetide reconnect failed: {exc}") from exc

    tp = tapetide_status.get_status()
    return ProviderStatusOut(name="TAPETIDE", status=tp.state, detail=tp.detail)


class CallMetricsOut(BaseModel):
    day: str
    tapetide_calls: int
    tapetide_quota: int
    tapetide_quota_remaining: int
    tapetide_cache_hits: int
    tapetide_cache_misses: int
    cache_hit_rate_pct: float
    angelone_calls: int
    fallbacks: int


@router.get("/call-metrics", response_model=CallMetricsOut)
def get_call_metrics() -> CallMetricsOut:
    """
    Real counts of calls actually issued today (IST day, matching Tapetide's
    own quota reset). Recorded by the code paths already making the calls —
    checking this never costs a call of its own.
    """
    m = call_metrics.snapshot()
    return CallMetricsOut(
        day=m.day,
        tapetide_calls=m.tapetide_calls,
        tapetide_quota=call_metrics.TAPETIDE_DAILY_QUOTA,
        tapetide_quota_remaining=m.tapetide_quota_remaining,
        tapetide_cache_hits=m.tapetide_cache_hits,
        tapetide_cache_misses=m.tapetide_cache_misses,
        cache_hit_rate_pct=m.cache_hit_rate_pct,
        angelone_calls=m.angelone_calls,
        fallbacks=m.fallbacks,
    )

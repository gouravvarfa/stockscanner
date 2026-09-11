from __future__ import annotations

from fastapi import APIRouter

from backend.config.multi_strategy_config import MultiStrategyConfig
from backend.config.strategy_config import StrategyConfig
from backend.services import config_store

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=StrategyConfig)
def get_config() -> StrategyConfig:
    return config_store.get_current_config()


@router.put("", response_model=StrategyConfig)
def update_config(new_config: StrategyConfig) -> StrategyConfig:
    return config_store.update_config(new_config)


@router.post("/reset", response_model=StrategyConfig)
def reset_config() -> StrategyConfig:
    return config_store.reset_config()


# Additive: configuration for GFS/Advanced GFS/PRD/NRD/Value Buy, kept fully
# separate from Strategy One's config above so tuning these never affects it.
@router.get("/multi-strategy", response_model=MultiStrategyConfig)
def get_multi_strategy_config() -> MultiStrategyConfig:
    return config_store.get_current_multi_strategy_config()


@router.put("/multi-strategy", response_model=MultiStrategyConfig)
def update_multi_strategy_config(new_config: MultiStrategyConfig) -> MultiStrategyConfig:
    return config_store.update_multi_strategy_config(new_config)


@router.post("/multi-strategy/reset", response_model=MultiStrategyConfig)
def reset_multi_strategy_config() -> MultiStrategyConfig:
    return config_store.reset_multi_strategy_config()

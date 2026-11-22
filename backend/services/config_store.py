from __future__ import annotations

import json
from pathlib import Path

from backend.config.multi_strategy_config import DEFAULT_MULTI_STRATEGY_CONFIG, MultiStrategyConfig
from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG, StrategyConfig

_OVERRIDE_PATH = Path("strategy_config_overrides.json")
_current: StrategyConfig | None = None

_MULTI_OVERRIDE_PATH = Path("multi_strategy_config_overrides.json")
_current_multi: MultiStrategyConfig | None = None



def get_current_config() -> StrategyConfig:
    global _current
    if _current is None:
        if _OVERRIDE_PATH.exists():
            _current = StrategyConfig.model_validate(json.loads(_OVERRIDE_PATH.read_text()))
        else:
            _current = DEFAULT_STRATEGY_CONFIG.model_copy(deep=True)
    return _current


def update_config(new_config: StrategyConfig) -> StrategyConfig:
    global _current
    _current = new_config
    _OVERRIDE_PATH.write_text(json.dumps(new_config.model_dump(), indent=2))
    return _current


def reset_config() -> StrategyConfig:
    global _current
    _current = DEFAULT_STRATEGY_CONFIG.model_copy(deep=True)
    if _OVERRIDE_PATH.exists():
        _OVERRIDE_PATH.unlink()
    return _current


def get_current_multi_strategy_config() -> MultiStrategyConfig:
    global _current_multi
    if _current_multi is None:
        if _MULTI_OVERRIDE_PATH.exists():
            _current_multi = MultiStrategyConfig.model_validate(json.loads(_MULTI_OVERRIDE_PATH.read_text()))
        else:
            _current_multi = DEFAULT_MULTI_STRATEGY_CONFIG.model_copy(deep=True)
    return _current_multi


def update_multi_strategy_config(new_config: MultiStrategyConfig) -> MultiStrategyConfig:
    global _current_multi
    _current_multi = new_config
    _MULTI_OVERRIDE_PATH.write_text(json.dumps(new_config.model_dump(), indent=2))
    return _current_multi


def reset_multi_strategy_config() -> MultiStrategyConfig:
    global _current_multi
    _current_multi = DEFAULT_MULTI_STRATEGY_CONFIG.model_copy(deep=True)
    if _MULTI_OVERRIDE_PATH.exists():
        _MULTI_OVERRIDE_PATH.unlink()
    return _current_multi


from __future__ import annotations

import json
from pathlib import Path

from backend.config.data_source_config import DEFAULT_DATA_SOURCE_CONFIG, DataSourceConfig
from backend.config.expiry_level_1_config import DEFAULT_EXPIRY_LEVEL_1_CONFIG, ExpiryLevel1Config
from backend.config.expiry_level_5_config import DEFAULT_EXPIRY_LEVEL_5_CONFIG, ExpiryLevel5Config
from backend.config.multi_strategy_config import DEFAULT_MULTI_STRATEGY_CONFIG, MultiStrategyConfig
from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG, StrategyConfig

_OVERRIDE_PATH = Path("strategy_config_overrides.json")
_current: StrategyConfig | None = None

_MULTI_OVERRIDE_PATH = Path("multi_strategy_config_overrides.json")
_current_multi: MultiStrategyConfig | None = None

_EXPIRY_OVERRIDE_PATH = Path("expiry_level_1_config_overrides.json")
_current_expiry: ExpiryLevel1Config | None = None

_EXPIRY5_OVERRIDE_PATH = Path("expiry_level_5_config_overrides.json")
_current_expiry5: ExpiryLevel5Config | None = None

_DATA_SOURCE_OVERRIDE_PATH = Path("data_source_config_overrides.json")
_current_data_source: DataSourceConfig | None = None


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


def get_current_expiry_level_1_config() -> ExpiryLevel1Config:
    global _current_expiry
    if _current_expiry is None:
        if _EXPIRY_OVERRIDE_PATH.exists():
            _current_expiry = ExpiryLevel1Config.model_validate(json.loads(_EXPIRY_OVERRIDE_PATH.read_text()))
        else:
            _current_expiry = DEFAULT_EXPIRY_LEVEL_1_CONFIG.model_copy(deep=True)
    return _current_expiry


def update_expiry_level_1_config(new_config: ExpiryLevel1Config) -> ExpiryLevel1Config:
    global _current_expiry
    _current_expiry = new_config
    _EXPIRY_OVERRIDE_PATH.write_text(json.dumps(new_config.model_dump(), indent=2))
    return _current_expiry


def reset_expiry_level_1_config() -> ExpiryLevel1Config:
    global _current_expiry
    _current_expiry = DEFAULT_EXPIRY_LEVEL_1_CONFIG.model_copy(deep=True)
    if _EXPIRY_OVERRIDE_PATH.exists():
        _EXPIRY_OVERRIDE_PATH.unlink()
    return _current_expiry


def get_current_expiry_level_5_config() -> ExpiryLevel5Config:
    global _current_expiry5
    if _current_expiry5 is None:
        if _EXPIRY5_OVERRIDE_PATH.exists():
            _current_expiry5 = ExpiryLevel5Config.model_validate(json.loads(_EXPIRY5_OVERRIDE_PATH.read_text()))
        else:
            _current_expiry5 = DEFAULT_EXPIRY_LEVEL_5_CONFIG.model_copy(deep=True)
    return _current_expiry5


def update_expiry_level_5_config(new_config: ExpiryLevel5Config) -> ExpiryLevel5Config:
    global _current_expiry5
    _current_expiry5 = new_config
    _EXPIRY5_OVERRIDE_PATH.write_text(json.dumps(new_config.model_dump(), indent=2))
    return _current_expiry5


def reset_expiry_level_5_config() -> ExpiryLevel5Config:
    global _current_expiry5
    _current_expiry5 = DEFAULT_EXPIRY_LEVEL_5_CONFIG.model_copy(deep=True)
    if _EXPIRY5_OVERRIDE_PATH.exists():
        _EXPIRY5_OVERRIDE_PATH.unlink()
    return _current_expiry5


def get_current_data_source_config() -> DataSourceConfig:
    global _current_data_source
    if _current_data_source is None:
        if _DATA_SOURCE_OVERRIDE_PATH.exists():
            _current_data_source = DataSourceConfig.model_validate(json.loads(_DATA_SOURCE_OVERRIDE_PATH.read_text()))
        else:
            _current_data_source = DEFAULT_DATA_SOURCE_CONFIG.model_copy(deep=True)
    return _current_data_source


def update_data_source_config(new_config: DataSourceConfig) -> DataSourceConfig:
    global _current_data_source
    _current_data_source = new_config
    _DATA_SOURCE_OVERRIDE_PATH.write_text(json.dumps(new_config.model_dump(), indent=2))
    return _current_data_source

from __future__ import annotations

import pandas as pd

from backend.config.multi_strategy_config import MultiStrategyConfig
from backend.screeners.stock_analysis import StockAnalysisResult
from backend.strategies.advanced_gfs import evaluate_advanced_gfs
from backend.strategies.gfs import evaluate_gfs
from backend.strategies.nrd import evaluate_nrd
from backend.strategies.prd import evaluate_prd
from backend.strategies.strategy_one import evaluate_strategy_one
from backend.strategies.types import StrategySignal
from backend.strategies.value_buy import evaluate_value_buy

ALL_STRATEGY_NAMES = ["Strategy One", "GFS", "Advanced GFS", "PRD", "NRD", "Value Buy"]


def evaluate_all_strategies(
    result: StockAnalysisResult, daily_ohlcv: pd.DataFrame, config: MultiStrategyConfig
) -> dict[str, StrategySignal]:
    """
    Runs all six strategies against ONE already-fetched/analyzed stock. No
    additional Angel One calls are made here — everything derives from
    `result` (Strategy One's already-computed indicators/divergences) and
    `daily_ohlcv` (already fetched by the caller). A stock can qualify for
    several of these at once; callers must keep them as separate entries,
    never deduplicated.
    """
    return {
        "Strategy One": evaluate_strategy_one(result),
        "GFS": evaluate_gfs(result, config.gfs),
        "Advanced GFS": evaluate_advanced_gfs(result, config.advanced_gfs),
        "PRD": evaluate_prd(result, daily_ohlcv, config.prd),
        "NRD": evaluate_nrd(result, config.nrd),
        "Value Buy": evaluate_value_buy(result, daily_ohlcv, config.value_buy),
    }

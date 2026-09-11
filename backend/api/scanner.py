from __future__ import annotations

from fastapi import APIRouter

from backend.strategies.runner import ALL_STRATEGY_NAMES

router = APIRouter(prefix="/api/scanner", tags=["scanner"])

_DESCRIPTIONS = {
    "Strategy One": "The original sector-first NIFTY 200 scoring strategy.",
    "GFS": "Daily RSI 38-45, Weekly RSI > 60, Monthly RSI > 60.",
    "Advanced GFS": "Daily RSI 59-65, Weekly RSI > 65, Monthly RSI > 68.",
    "PRD": "Positive Reverse Divergence: real bullish RSI/price divergence, gated by D/W/M RSI > 60.",
    "NRD": "Negative Reverse Divergence: real bearish RSI/price divergence, gated by D/W/M RSI > 60.",
    "Value Buy": "Monthly RSI in the support zone, latest confirmed weekly candle green, plus a daily key reversal or trendline breakout.",
}


@router.get("/strategies")
def list_strategies() -> list[dict[str, str]]:
    return [{"name": name, "description": _DESCRIPTIONS[name]} for name in ALL_STRATEGY_NAMES]

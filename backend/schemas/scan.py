from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class TimeframeReadingOut(BaseModel):
    rsi: float | None
    has_bearish_divergence: bool
    divergence_count: int


class FibonacciOut(BaseModel):
    swing_high: float
    swing_low: float
    direction: str
    nearest_ratio: float
    nearest_price: float
    distance_pct: float
    in_preferred_zone: bool


class TradeSetupOut(BaseModel):
    available: bool
    reason: str | None
    entry_low: float | None
    entry_high: float | None
    stop_loss: float | None
    target1: float | None
    target2: float | None
    risk_reward_t1: float | None
    risk_reward_t2: float | None
    methodology: str


class StockResultOut(BaseModel):
    rank: int
    symbol: str
    sector: str
    current_price: float
    data_as_of: dt.datetime
    score: float
    classification: str
    bias: str
    components: dict[str, float]
    daily: TimeframeReadingOut
    weekly: TimeframeReadingOut
    monthly: TimeframeReadingOut
    fibonacci: FibonacciOut | None
    ema20: float | None
    ema50: float | None
    ema200: float | None
    macd_histogram: float | None
    adx: float | None
    volume_ratio: float | None
    distance_from_52w_high_pct: float | None
    meets_weekly_rsi_band: bool
    meets_monthly_rsi_min: bool
    disqualified_by_divergence: bool
    explanation: list[str]
    data_warnings: list[str]
    trade_setup: TradeSetupOut | None = None


class SectorResultOut(BaseModel):
    sector: str
    nse_index: str | None
    available: bool
    unavailable_reason: str | None
    daily_rsi: float | None
    weekly_rsi: float | None
    monthly_rsi: float | None
    daily_return_pct: float | None
    weekly_return_pct: float | None
    monthly_return_pct: float | None
    daily_vs_nifty: float | None
    weekly_vs_nifty: float | None
    monthly_vs_nifty: float | None
    meets_rsi_thresholds: bool
    outperforms_nifty: bool
    sector_score: float
    weekly_data_source: str = "UNAVAILABLE"  # "ANGEL_ONE" | "TAPETIDE" | "UNAVAILABLE"
    monthly_data_source: str = "UNAVAILABLE"  # "ANGEL_ONE" | "TAPETIDE" | "UNAVAILABLE"


class StrategySignalOut(BaseModel):
    strategy: str
    symbol: str
    sector: str
    qualifies: bool
    signal_date: dt.datetime | None
    daily_rsi: float | None
    weekly_rsi: float | None
    monthly_rsi: float | None
    conditions: dict[str, bool]
    explanation: str
    extra: dict = {}


class ScanResultOut(BaseModel):
    scan_id: int | None
    started_at: dt.datetime
    finished_at: dt.datetime
    execution_seconds: float
    data_source: str = "tapetide"  # kept for compatibility; now the SELECTED mode (auto/tapetide/angel_one)
    data_source_summary: dict[str, int] = {}  # actual provider used per stock, e.g. {"TAPETIDE": 45, "ANGEL_ONE": 3}
    universe_requested: int
    universe_returned: int
    universe_complete: bool
    universe_note: str | None
    stocks_scanned: int
    stocks_failed: int
    failed_symbols: list[str]
    qualifying_sectors: list[str]
    sectors: list[SectorResultOut]
    top10: list[StockResultOut]
    top3: list[StockResultOut]
    best: StockResultOut | None
    # Additive: all six strategies' qualifying stocks from this same scan run,
    # keyed by strategy name. A stock may appear under multiple strategies.
    strategies: dict[str, list[StrategySignalOut]] = {}
    errors: list[str]

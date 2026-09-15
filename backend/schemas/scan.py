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
    data_source: str | None = None  # always "ANGEL_ONE" — the only provider in this project


class NiftyUniverseStockOut(BaseModel):
    """
    One row of the NIFTY 200 master universe (from NIFTY_200_Sector_List.xlsx)
    — one entry per symbol in that file, present regardless of whether that
    stock's own price/RSI analysis succeeded. Never removed on failure;
    unavailable fields are None with `status`/`status_reason` explaining why.
    """
    symbol: str
    current_price: float | None = None
    daily_rsi: float | None = None
    weekly_rsi: float | None = None
    monthly_rsi: float | None = None
    data_source: str | None = None
    status: str  # "OK" | "DATA_UNAVAILABLE"
    status_reason: str | None = None


class StrategySignalOut(BaseModel):
    strategy: str
    symbol: str
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
    data_source: str = "ANGEL_ONE"  # the only market-data provider in this project
    data_source_summary: dict[str, int] = {}
    # NIFTY 200 universe (Strategy One/GFS/Advanced GFS/PRD/NRD).
    universe_requested: int
    universe_returned: int
    universe_complete: bool
    # NIFTY 500 universe (Value Buy only) — a separate, larger list.
    value_buy_universe_requested: int
    value_buy_universe_returned: int
    stocks_scanned: int
    stocks_failed: int
    failed_symbols: list[str]
    top10: list[StockResultOut]
    top3: list[StockResultOut]
    best: StockResultOut | None
    # The NIFTY 200 master universe (every symbol in the Excel file,
    # regardless of analysis success) — for the NIFTY 200 Scanner page's
    # full-universe table + local strategy/search filtering.
    nifty200_universe: list[NiftyUniverseStockOut] = []
    # All six strategies' qualifying stocks from this same scan run, keyed by
    # strategy name. A stock may appear under multiple strategies.
    strategies: dict[str, list[StrategySignalOut]] = {}
    errors: list[str]

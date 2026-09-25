from __future__ import annotations

from backend.schemas.scan import (
    FibonacciOut,
    NiftyUniverseStockOut,
    ScanResultOut,
    StockResultOut,
    StrategySignalOut,
    TimeframeReadingOut,
    TradeSetupOut,
)
from backend.screeners.stock_analysis import StockAnalysisResult, TimeframeReading
from backend.services.scan_service import ScanOutcome, UniverseStockEntry
from backend.strategies.trade_setup import TradeSetup, calculate_trade_setup
from backend.strategies.types import StrategySignal
from backend.services.sectors import sector_for


def _timeframe_out(reading: TimeframeReading) -> TimeframeReadingOut:
    return TimeframeReadingOut(
        rsi=reading.rsi,
        has_bearish_divergence=reading.has_bearish_divergence,
        divergence_count=len(reading.divergences),
    )


def _trade_setup_out(setup: TradeSetup) -> TradeSetupOut:
    return TradeSetupOut(
        available=setup.available,
        reason=setup.reason,
        entry_low=setup.entry_low,
        entry_high=setup.entry_high,
        stop_loss=setup.stop_loss,
        target1=setup.target1,
        target2=setup.target2,
        risk_reward_t1=setup.risk_reward_t1,
        risk_reward_t2=setup.risk_reward_t2,
        methodology=setup.methodology,
    )


def stock_result_out(
    result: StockAnalysisResult, rank: int, include_trade_setup: bool = False, data_source: str | None = "ANGEL_ONE"
) -> StockResultOut:
    fib = result.fibonacci
    fib_out = (
        FibonacciOut(
            swing_high=fib.swing_high,
            swing_low=fib.swing_low,
            direction=fib.direction,
            nearest_ratio=fib.nearest_level.ratio,
            nearest_price=fib.nearest_level.price,
            distance_pct=fib.nearest_level.distance_pct,
            in_preferred_zone=fib.in_preferred_zone,
        )
        if fib is not None
        else None
    )
    return StockResultOut(
        rank=rank,
        symbol=result.symbol,
        current_price=result.current_price,
        data_as_of=result.data_as_of.to_pydatetime(),
        score=result.score.total_score,
        classification=result.score.classification,
        bias=result.score.bias,
        components=result.score.components,
        daily=_timeframe_out(result.daily),
        weekly=_timeframe_out(result.weekly),
        monthly=_timeframe_out(result.monthly),
        fibonacci=fib_out,
        ema20=result.ema20,
        ema50=result.ema50,
        ema200=result.ema200,
        macd_histogram=result.macd_histogram,
        adx=result.adx_value,
        volume_ratio=result.volume_ratio_value,
        distance_from_52w_high_pct=result.distance_from_52w_high_pct,
        meets_weekly_rsi_band=result.meets_weekly_rsi_band,
        meets_monthly_rsi_min=result.meets_monthly_rsi_min,
        disqualified_by_divergence=result.disqualified_by_divergence,
        explanation=result.score.explanation,
        data_warnings=result.data_warnings,
        trade_setup=_trade_setup_out(calculate_trade_setup(result)) if include_trade_setup else None,
        data_source=data_source,
    )


def universe_stock_out(entry: UniverseStockEntry) -> NiftyUniverseStockOut:
    return NiftyUniverseStockOut(
        symbol=entry.symbol,
        current_price=entry.current_price,
        daily_rsi=entry.daily_rsi,
        weekly_rsi=entry.weekly_rsi,
        monthly_rsi=entry.monthly_rsi,
        data_source=entry.data_source,
        status=entry.status,
        status_reason=entry.status_reason,
    )


def _json_safe(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def strategy_signal_out(signal: StrategySignal) -> StrategySignalOut:
    return StrategySignalOut(
        strategy=signal.strategy,
        symbol=signal.symbol,
        qualifies=signal.qualifies,
        signal_date=signal.signal_date.to_pydatetime() if signal.signal_date is not None else None,
        daily_rsi=signal.daily_rsi,
        weekly_rsi=signal.weekly_rsi,
        monthly_rsi=signal.monthly_rsi,
        conditions=signal.conditions,
        explanation=signal.explanation,
        extra={**_json_safe(signal.extra), "sector": sector_for(signal.symbol)},
    )


def scan_outcome_out(outcome: ScanOutcome, scan_id: int | None = None) -> ScanResultOut:
    top10_out = [stock_result_out(r, i + 1) for i, r in enumerate(outcome.top10)]
    top3_out = [stock_result_out(r, i + 1, include_trade_setup=True) for i, r in enumerate(outcome.top3)]
    best_out = stock_result_out(outcome.best, 1, include_trade_setup=True) if outcome.best else None
    nifty200_universe_out = [universe_stock_out(entry) for entry in outcome.nifty200_universe]

    return ScanResultOut(
        scan_id=scan_id,
        started_at=outcome.started_at,
        finished_at=outcome.finished_at,
        execution_seconds=outcome.execution_seconds,
        data_source_summary=outcome.data_source_summary,
        universe_requested=outcome.universe_requested,
        universe_returned=outcome.universe_returned,
        universe_complete=outcome.universe_complete,
        value_buy_universe_requested=outcome.value_buy_universe_requested,
        value_buy_universe_returned=outcome.value_buy_universe_returned,
        stocks_scanned=outcome.stocks_scanned,
        stocks_failed=outcome.stocks_failed,
        failed_symbols=outcome.failed_symbols,
        top10=top10_out,
        top3=top3_out,
        best=best_out,
        nifty200_universe=nifty200_universe_out,
        strategies={
            name: [strategy_signal_out(s) for s in signals]
            for name, signals in outcome.strategy_signals.items()
        },
        errors=outcome.errors,
    )

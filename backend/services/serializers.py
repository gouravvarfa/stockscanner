from __future__ import annotations

from backend.schemas.scan import (
    FibonacciOut,
    ScanResultOut,
    SectorResultOut,
    StockResultOut,
    StrategySignalOut,
    TimeframeReadingOut,
    TradeSetupOut,
)
from backend.screeners.stock_analysis import StockAnalysisResult, TimeframeReading
from backend.sector_analysis.engine import SectorAnalysis
from backend.services.scan_service import ScanOutcome
from backend.strategies.trade_setup import TradeSetup, calculate_trade_setup
from backend.strategies.types import StrategySignal


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


def stock_result_out(result: StockAnalysisResult, rank: int, include_trade_setup: bool = False) -> StockResultOut:
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
        sector=result.sector,
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
    )


def sector_result_out(sector: str, analysis: SectorAnalysis) -> SectorResultOut:
    return SectorResultOut(
        sector=sector,
        nse_index=analysis.nse_index,
        available=analysis.available,
        unavailable_reason=analysis.unavailable_reason,
        daily_rsi=analysis.daily.rsi if analysis.daily else None,
        weekly_rsi=analysis.weekly.rsi if analysis.weekly else None,
        monthly_rsi=analysis.monthly.rsi if analysis.monthly else None,
        daily_return_pct=analysis.daily.return_pct if analysis.daily else None,
        weekly_return_pct=analysis.weekly.return_pct if analysis.weekly else None,
        monthly_return_pct=analysis.monthly.return_pct if analysis.monthly else None,
        daily_vs_nifty=analysis.daily_vs_nifty,
        weekly_vs_nifty=analysis.weekly_vs_nifty,
        monthly_vs_nifty=analysis.monthly_vs_nifty,
        meets_rsi_thresholds=analysis.meets_rsi_thresholds,
        outperforms_nifty=analysis.outperforms_nifty,
        sector_score=analysis.sector_score,
        weekly_data_source=analysis.weekly_data_source,
        monthly_data_source=analysis.monthly_data_source,
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
        sector=signal.sector,
        qualifies=signal.qualifies,
        signal_date=signal.signal_date.to_pydatetime() if signal.signal_date is not None else None,
        daily_rsi=signal.daily_rsi,
        weekly_rsi=signal.weekly_rsi,
        monthly_rsi=signal.monthly_rsi,
        conditions=signal.conditions,
        explanation=signal.explanation,
        extra=_json_safe(signal.extra),
    )


def scan_outcome_out(outcome: ScanOutcome, scan_id: int | None = None) -> ScanResultOut:
    top10_out = [stock_result_out(r, i + 1) for i, r in enumerate(outcome.top10)]
    top3_out = [stock_result_out(r, i + 1, include_trade_setup=True) for i, r in enumerate(outcome.top3)]
    best_out = stock_result_out(outcome.best, 1, include_trade_setup=True) if outcome.best else None

    return ScanResultOut(
        scan_id=scan_id,
        started_at=outcome.started_at,
        finished_at=outcome.finished_at,
        execution_seconds=outcome.execution_seconds,
        data_source=outcome.data_source_mode.upper(),
        data_source_summary=outcome.data_source_summary,
        universe_requested=outcome.universe_requested,
        universe_returned=outcome.universe_returned,
        universe_complete=outcome.universe_complete,
        universe_note=outcome.universe_note,
        stocks_scanned=outcome.stocks_scanned,
        stocks_failed=outcome.stocks_failed,
        failed_symbols=outcome.failed_symbols,
        qualifying_sectors=outcome.qualifying_sectors,
        sectors=[sector_result_out(s, a) for s, a in sorted(outcome.sector_analyses.items(), key=lambda kv: -kv[1].sector_score)],
        top10=top10_out,
        top3=top3_out,
        best=best_out,
        strategies={
            name: [strategy_signal_out(s) for s in signals]
            for name, signals in outcome.strategy_signals.items()
        },
        errors=outcome.errors,
    )

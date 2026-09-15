"""BacktestResult (dataclasses) -> API response schemas. Kept separate from
the engine so the engine has zero pydantic/FastAPI dependency."""
from __future__ import annotations

from backend.schemas.top_bottom import (
    BacktestResultOut,
    DataCoverageOut,
    EquityPointOut,
    FutureContractOut,
    LevelPointOut,
    PricePointOut,
    SignalOut,
    StatisticsOut,
    TradeOut,
)
from backend.strategies.top_bottom.models import BacktestResult


def serialize_result(result: BacktestResult) -> BacktestResultOut:
    return BacktestResultOut(
        backtest_id=result.backtest_id,
        symbol=result.symbol,
        trading_symbol=result.trading_symbol,
        expiry=result.expiry,
        instrument_class=result.instrument_class,
        exch_seg=result.exch_seg,
        timeframe=result.timeframe,
        starting_capital=result.starting_capital,
        coverage=DataCoverageOut(
            requested_from=result.coverage.requested_from,
            requested_to=result.coverage.requested_to,
            available_from=result.coverage.available_from,
            available_to=result.coverage.available_to,
            is_complete=result.coverage.is_complete,
        ),
        statistics=StatisticsOut(**vars(result.statistics)),
        price_series=[PricePointOut(date=p.date, close=p.close) for p in result.price_series],
        system_point_line=[LevelPointOut(date=p.date, value=p.value) for p in result.system_point_line],
        stop_loss_line=[LevelPointOut(date=p.date, value=p.value) for p in result.stop_loss_line],
        trades=[
            TradeOut(
                trade_number=n,
                direction=t.direction,
                symbol=t.symbol,
                trading_symbol=t.trading_symbol,
                expiry=t.expiry,
                signal_date=t.signal_date,
                entry_date=t.entry_date,
                entry_price=t.entry_price,
                system_point=t.system_point,
                initial_sl=t.initial_sl,
                active_stop=t.active_stop,
                reversal_event_id=t.reversal_event_id,
                lot_size=t.lot_size,
                exit_date=t.exit_date,
                exit_price=t.exit_price,
                exit_reason=t.exit_reason,
                pnl_points=t.pnl_points,
                pnl_amount=t.pnl_amount,
                pnl_pct=t.pnl_pct,
                holding_days=t.holding_days,
                status=t.status,
            )
            for n, t in enumerate(result.trades, start=1)
        ],
        signals=[
            SignalOut(
                direction=s.direction,
                signal_date=s.signal_date,
                system_point=s.system_point,
                entry_price=s.entry_price,
                reversal_event_id=s.reversal_event_id,
            )
            for s in result.signals
        ],
        equity_curve=[
            EquityPointOut(
                date=e.date,
                trade_number=e.trade_number,
                equity=e.equity,
                cumulative_pnl_pct=e.cumulative_pnl_pct,
                drawdown_pct=e.drawdown_pct,
            )
            for e in result.equity_curve
        ],
        created_at=result.created_at,
    )


def serialize_contract(c) -> FutureContractOut:  # c: FutureContract
    return FutureContractOut(
        underlying=c.underlying, trading_symbol=c.trading_symbol, token=c.token,
        exch_seg=c.exch_seg, expiry=c.expiry, is_index=c.is_index, lot_size=c.lot_size,
    )

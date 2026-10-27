from __future__ import annotations

import dataclasses

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.schemas.system_one_backtest import (
    SystemOneBacktestOut,
    SystemOneBacktestRequest,
    SystemOneCandleOut,
    SystemOneEquityPointOut,
    SystemOneSkippedOut,
    SystemOneSummaryOut,
    SystemOneTradeOut,
    SystemOneYearOut,
)
from backend.services import system_one_backtest_service as service
from backend.services import system_one_excel_export as excel_export
from backend.services.provider_factory import get_angelone_provider
from backend.services.top_bottom_backtest_service import InsufficientDataError, TopBottomValidationError

router = APIRouter(prefix="/api/system-one", tags=["system-one"])


def _serialize(stored: service.StoredSystemOneBacktest) -> SystemOneBacktestOut:
    result = stored.result
    summary = result.summary()
    return SystemOneBacktestOut(
        backtest_id=stored.backtest_id,
        symbol=stored.symbol,
        trading_symbol=stored.trading_symbol,
        timeframe=stored.timeframe,
        from_date=stored.from_date,
        to_date=stored.to_date,
        data_available_from=stored.data_available_from,
        data_available_to=stored.data_available_to,
        reference_capital=stored.config.reference_capital,
        risk_per_trade=stored.config.risk_per_trade,
        summary=SystemOneSummaryOut(
            total_trades=summary.total_trades,
            closed_trades=summary.closed_trades,
            open_trades=summary.open_trades,
            winning_trades=summary.winning_trades,
            losing_trades=summary.losing_trades,
            net_realized_pnl=summary.net_realized_pnl,
            win_rate=summary.win_rate,
            average_win=summary.average_win,
            average_loss=summary.average_loss,
            profit_factor=summary.profit_factor,
            best_trade=summary.best_trade,
            worst_trade=summary.worst_trade,
            max_drawdown=summary.max_drawdown,
            longest_losing_streak=summary.longest_losing_streak,
            unrealized_pnl=summary.unrealized_pnl,
        ),
        candles=[
            SystemOneCandleOut(
                date=c.date.to_pydatetime(), open=c.open, high=c.high, low=c.low, close=c.close, rsi=c.rsi, ma=c.ma,
            )
            for c in result.series
        ],
        trades=[
            SystemOneTradeOut(
                trade_number=t.trade_number,
                signal_date=t.signal_date.to_pydatetime(),
                entry_date=t.entry_date.to_pydatetime(),
                entry_price=t.entry_price,
                stop_loss=t.stop_loss,
                risk_per_share=t.risk_per_share,
                risk_per_trade=t.risk_per_trade,
                quantity=t.quantity,
                exit_price=t.exit_price,
                exit_date=t.exit_date.to_pydatetime() if t.exit_date is not None else None,
                pnl_amount=t.pnl_amount,
                status=t.status,
                exit_reason=t.exit_reason,
                holding_periods=t.holding_periods,
                pnl_pct=t.pnl_pct,
                r_multiple=t.r_multiple,
                unrealized_pnl=t.unrealized_pnl,
                data_flag=t.data_flag,
            )
            for t in result.trades
        ],
        skipped_signals=[
            SystemOneSkippedOut(signal_date=sk.signal_date.to_pydatetime(), reason=sk.reason) for sk in result.skipped
        ],
        yearly=[SystemOneYearOut(**dataclasses.asdict(y)) for y in result.yearly()],
        equity_curve=[
            SystemOneEquityPointOut(date=p.date.to_pydatetime(), trade_number=p.trade_number, cumulative_pnl=p.cumulative_pnl)
            for p in result.equity_curve()
        ],
        warnings=result.warnings,
        note=service.PNL_NOTE,
        created_at=stored.created_at,
    )


@router.post("/backtest", response_model=SystemOneBacktestOut)
async def run_backtest(request: SystemOneBacktestRequest) -> SystemOneBacktestOut:
    try:
        stored = await service.run_for_symbol(
            get_angelone_provider(), request.symbol, request.from_date, request.to_date, timeframe=request.timeframe
        )
    except TopBottomValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InsufficientDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — one bad symbol/response must never crash the app
        raise HTTPException(status_code=502, detail=f"Angel One error: {exc}") from exc
    return _serialize(stored)


@router.get("/backtest/{backtest_id}/export")
async def export_backtest(backtest_id: str) -> Response:
    stored = service.get_result(backtest_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Backtest not found (it may have been cleared by a backend restart).")
    return Response(
        content=excel_export.build_excel(stored),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{excel_export.file_name(stored)}"'},
    )

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.schemas.top_bottom import BacktestRequest, BacktestResultOut, FutureContractOut
from backend.services import equity_instrument_service as equity_service
from backend.services import futures_instrument_service as futures_service
from backend.services import top_bottom_backtest_service as backtest_service
from backend.services import top_bottom_excel_export as excel_export
from backend.services.provider_factory import get_angelone_provider
from backend.services.top_bottom_backtest_service import InsufficientDataError, TopBottomValidationError
from backend.services.top_bottom_serializers import serialize_contract, serialize_result

router = APIRouter(prefix="/api/top-bottom", tags=["top-bottom"])


@router.get("/equity/search", response_model=list[str])
def search_equities(q: str) -> list[str]:
    """A Group stock symbols matching `q` — the Top-Bottom equity universe."""
    return equity_service.search_equities(q)


@router.get("/futures/search", response_model=list[FutureContractOut])
async def search_futures(q: str) -> list[FutureContractOut]:
    q = q.strip()
    if not q:
        return []
    contracts = await futures_service.search_futures(q)
    return [serialize_contract(c) for c in contracts]


@router.get("/futures/contracts/{symbol}", response_model=list[FutureContractOut])
async def list_contracts(symbol: str) -> list[FutureContractOut]:
    contracts = await futures_service.list_contracts(symbol.strip().upper())
    if not contracts:
        raise HTTPException(status_code=404, detail="Top-Bottom strategy is available only for Futures.")
    return [serialize_contract(c) for c in contracts]


@router.post("/backtest", response_model=BacktestResultOut)
async def run_backtest(request: BacktestRequest) -> BacktestResultOut:
    try:
        result = await backtest_service.run_futures_backtest(
            get_angelone_provider(),
            symbol=request.symbol.strip().upper(),
            instrument_type=request.instrument_type,
            timeframe=request.timeframe,
            from_date=request.from_date,
            to_date=request.to_date,
            expiry=request.expiry,
            starting_capital=request.starting_capital,
        )
    except TopBottomValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InsufficientDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — one bad symbol/response must never crash the app
        raise HTTPException(status_code=502, detail=f"Angel One error: {exc}") from exc

    return serialize_result(result)


@router.get("/backtest/{backtest_id}", response_model=BacktestResultOut)
async def get_backtest(backtest_id: str) -> BacktestResultOut:
    result = backtest_service.get_result(backtest_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest not found (it may have been cleared by a backend restart).")
    return serialize_result(result)


@router.get("/backtest/{backtest_id}/trades", response_model=BacktestResultOut)
async def get_backtest_trades(backtest_id: str) -> BacktestResultOut:
    return await get_backtest(backtest_id)


@router.get("/backtest/{backtest_id}/equity", response_model=BacktestResultOut)
async def get_backtest_equity(backtest_id: str) -> BacktestResultOut:
    return await get_backtest(backtest_id)


@router.get("/backtest/{backtest_id}/export")
async def export_backtest(backtest_id: str) -> Response:
    result = backtest_service.get_result(backtest_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest not found (it may have been cleared by a backend restart).")

    content = excel_export.build_excel(result)
    filename = f"top_bottom_{result.trading_symbol}_{result.timeframe}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

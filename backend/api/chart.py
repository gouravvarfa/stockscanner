from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException

from backend.providers.market_data_router import DataUnavailableError
from backend.schemas.chart import ChartCandleOut, ChartCandlesResponse
from backend.services import chart_service
from backend.services.provider_factory import get_angelone_provider

router = APIRouter(prefix="/api/chart", tags=["chart"])


@router.get("/candles", response_model=ChartCandlesResponse)
async def get_candles(symbol: str, timeframe: str = "1D") -> ChartCandlesResponse:
    symbol = symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    try:
        df = await chart_service.get_candles(get_angelone_provider(), symbol, timeframe)
    except chart_service.ChartUnsupportedTimeframeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DataUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surfaced as a clean error, never a bare 500
        raise HTTPException(status_code=502, detail=f"Angel One error: {exc}") from exc

    candles = [
        ChartCandleOut(
            time=int(idx.timestamp()),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume) if not pd.isna(row.volume) else 0.0,
        )
        for idx, row in df.iterrows()
    ]
    return ChartCandlesResponse(symbol=symbol, timeframe=timeframe, candles=candles)

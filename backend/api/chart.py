from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException, Response

from backend.providers.market_data_router import DataUnavailableError
from backend.schemas.chart import ChartCandleOut, ChartCandlesResponse
from backend.services import chart_service
from backend.services.provider_factory import get_angelone_provider

router = APIRouter(prefix="/api/chart", tags=["chart"])


@router.get("/candles", response_model=ChartCandlesResponse)
async def get_candles(
    response: Response, symbol: str, timeframe: str = "1D", long_history: bool = False,
) -> ChartCandlesResponse:
    # 2026-09-28 (ACC/ABFRL chart-frozen bug): this response had no
    # Cache-Control header at all, which left it eligible for the calling
    # browser/webview's OWN heuristic HTTP disk cache — a layer BELOW the
    # frontend's in-memory chart cache (chartDatafeed.ts), invisible to it,
    # and NOT cleared by a normal page refresh or even a full app restart.
    # 1D/1W/1M now carry a live, continuously-changing current candle, so
    # this endpoint must never be served from any HTTP-level cache.
    response.headers["Cache-Control"] = "no-store"
    symbol = symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    try:
        df = await chart_service.get_candles(get_angelone_provider(), symbol, timeframe, long_history=long_history)
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

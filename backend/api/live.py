"""
Live market-data API — SSE stream for one symbol at a time, matching the
"chart open subscribes, chart close unsubscribes" flow from the
2026-09-25 WebSocket master prompt. No project-wide SSE/WebSocket infra
existed before this (the rest of the app polls — see scan_job_manager.py's
/partial endpoints), so this is a small, additive, isolated exception:
frontend/src/chart/useLiveChart.ts is the ONLY consumer.

Never exposes Angel One credentials — the frontend only ever sees symbol/
candle/status JSON, never a token/session.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from backend.services.provider_factory import get_live_market_data_service

router = APIRouter(prefix="/api/live", tags=["live"])


@router.get("/status")
async def get_status() -> dict:
    service = get_live_market_data_service()
    return {
        "connection_state": service.connection_state,
        "market_state": service.market_state(),
        "last_tick_at": service.last_tick_at.isoformat() if service.last_tick_at else None,
        "subscribed_symbols": service.subscriptions.subscribed_symbols(),
    }


@router.get("/stream/{symbol}")
async def stream_symbol(symbol: str) -> StreamingResponse:
    """One SSE connection = one reference in the SubscriptionManager for
    the lifetime of the HTTP connection — acquired on connect, released
    the moment the client disconnects (chart closed/navigated away/tab
    closed), so a symbol nobody is watching gets unsubscribed automatically
    without any explicit "chart close" call needed from the frontend.

    Hand-rolled SSE (no sse_starlette dependency — the project has no
    prior SSE infra to reuse, and a plain "data: ...\\n\\n" stream over
    FastAPI's own StreamingResponse needs nothing extra in requirements.txt)."""
    symbol = symbol.strip().upper()
    service = get_live_market_data_service()
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=50)  # bounded — a slow consumer drops old ticks, never accumulates unbounded (2026-09-25 memory-safety requirement)

    async def on_tick(tick_symbol: str, candles: dict) -> None:
        if tick_symbol != symbol:
            return
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await queue.put(candles)

    async def event_generator():
        await service.subscriptions.acquire(symbol)
        service.add_listener(on_tick)
        try:
            while True:
                candles = await queue.get()
                yield f"event: candle\ndata: {json.dumps(candles)}\n\n"
        finally:
            service.remove_listener(on_tick)
            await service.subscriptions.release(symbol)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

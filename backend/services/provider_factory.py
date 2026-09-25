from __future__ import annotations

from backend.live.market_data_service import MarketDataService
from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.market_data_router import MarketDataRouter

_angelone_provider: AngelOneProvider | None = None
_router: MarketDataRouter | None = None
_live_market_data_service: MarketDataService | None = None


async def startup() -> None:
    global _angelone_provider, _router, _live_market_data_service
    _angelone_provider = AngelOneProvider()
    _router = MarketDataRouter(_angelone_provider)
    # Lazy connection (see MarketDataService._ensure_running): no WebSocket
    # is actually opened until the first chart subscribes a symbol — "Do
    # NOT automatically subscribe the entire universe just because the
    # scanner is open" (2026-09-25 spec).
    _live_market_data_service = MarketDataService(_angelone_provider)


async def shutdown() -> None:
    global _angelone_provider, _router, _live_market_data_service
    if _live_market_data_service is not None:
        await _live_market_data_service.stop()
    _angelone_provider = None
    _router = None
    _live_market_data_service = None


def get_angelone_provider() -> AngelOneProvider:
    if _angelone_provider is None:
        raise RuntimeError("Angel One provider not initialized — app startup has not run yet.")
    return _angelone_provider


def get_market_data_router() -> MarketDataRouter:
    if _router is None:
        raise RuntimeError("Market data router not initialized — app startup has not run yet.")
    return _router


def get_live_market_data_service() -> MarketDataService:
    if _live_market_data_service is None:
        raise RuntimeError("Live market data service not initialized — app startup has not run yet.")
    return _live_market_data_service

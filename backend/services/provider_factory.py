from __future__ import annotations

from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.market_data_router import MarketDataRouter

_angelone_provider: AngelOneProvider | None = None
_router: MarketDataRouter | None = None


async def startup() -> None:
    global _angelone_provider, _router
    _angelone_provider = AngelOneProvider()
    _router = MarketDataRouter(_angelone_provider)


async def shutdown() -> None:
    global _angelone_provider, _router
    _angelone_provider = None
    _router = None


def get_angelone_provider() -> AngelOneProvider:
    if _angelone_provider is None:
        raise RuntimeError("Angel One provider not initialized — app startup has not run yet.")
    return _angelone_provider


def get_market_data_router() -> MarketDataRouter:
    if _router is None:
        raise RuntimeError("Market data router not initialized — app startup has not run yet.")
    return _router

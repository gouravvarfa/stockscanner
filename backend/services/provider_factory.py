from __future__ import annotations

from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.market_data_router import MarketDataRouter
from backend.providers.tapetide_client import TapetideMCPClient
from backend.providers.tapetide_provider import TapetideProvider

_client: TapetideMCPClient | None = None
_provider: TapetideProvider | None = None
_angelone_provider: AngelOneProvider | None = None
_router: MarketDataRouter | None = None


async def startup() -> None:
    global _client, _provider, _angelone_provider, _router
    _client = TapetideMCPClient()
    await _client.__aenter__()
    _provider = TapetideProvider(_client)
    # Angel One authenticates lazily on first intraday request (TOTP-based
    # login on every app start would be wasteful when Expiry Level 1 is
    # never used in a given run).
    _angelone_provider = AngelOneProvider()
    _router = MarketDataRouter(_provider, _angelone_provider)


async def shutdown() -> None:
    global _client, _provider, _angelone_provider, _router
    if _client is not None:
        await _client.__aexit__(None, None, None)
    _client = None
    _provider = None
    _angelone_provider = None
    _router = None


def get_provider() -> TapetideProvider:
    if _provider is None:
        raise RuntimeError("Tapetide provider not initialized — app startup has not run yet.")
    return _provider


def get_angelone_provider() -> AngelOneProvider:
    if _angelone_provider is None:
        raise RuntimeError("Angel One provider not initialized — app startup has not run yet.")
    return _angelone_provider


def get_market_data_router() -> MarketDataRouter:
    if _router is None:
        raise RuntimeError("Market data router not initialized — app startup has not run yet.")
    return _router

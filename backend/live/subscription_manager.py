"""
Reference-counted symbol subscription tracking for the live market-data
engine — the "central subscription manager" the WebSocket master prompt
asks for (2026-09-25). Purely in-memory bookkeeping: it decides WHEN to
call the injected subscribe/unsubscribe callbacks, never talks to Angel
One itself (that's market_data_service.py's job), so it's trivially
testable and reusable regardless of transport.

Multiple independent "reasons" a symbol might be needed (a chart open on
one device, a live scanner row, etc.) each acquire/release their own
reference; the symbol is only actually subscribed while at least one
reference is held, and unsubscribed the moment the last one is released —
this is what prevents duplicate subscriptions when e.g. two chart tabs
both have BHEL open.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger("scanner.live.subscription_manager")

OnFirstSubscribe = Callable[[str], Awaitable[None]]
OnLastUnsubscribe = Callable[[str], Awaitable[None]]


class SubscriptionManager:
    def __init__(self, on_first_subscribe: OnFirstSubscribe, on_last_unsubscribe: OnLastUnsubscribe) -> None:
        self._refcounts: dict[str, int] = {}
        self._on_first_subscribe = on_first_subscribe
        self._on_last_unsubscribe = on_last_unsubscribe
        self._lock = asyncio.Lock()

    async def acquire(self, symbol: str) -> None:
        """One more reference wants live data for `symbol`. Only triggers
        an actual Angel One subscription on the FIRST reference — every
        subsequent acquire() for the same symbol just bumps the count and
        reuses the existing stream (no duplicate subscription)."""
        async with self._lock:
            count = self._refcounts.get(symbol, 0)
            self._refcounts[symbol] = count + 1
            if count == 0:
                logger.info("Live subscribe: %s (first reference)", symbol)
                await self._on_first_subscribe(symbol)

    async def release(self, symbol: str) -> None:
        """One reference no longer needs `symbol` (e.g. its chart closed).
        Only triggers an actual Angel One unsubscription once EVERY
        reference has released it — another chart/component still holding
        it keeps the stream alive."""
        async with self._lock:
            if symbol not in self._refcounts:
                return
            self._refcounts[symbol] -= 1
            if self._refcounts[symbol] <= 0:
                del self._refcounts[symbol]
                logger.info("Live unsubscribe: %s (last reference released)", symbol)
                await self._on_last_unsubscribe(symbol)

    def is_subscribed(self, symbol: str) -> bool:
        return symbol in self._refcounts

    def refcount(self, symbol: str) -> int:
        return self._refcounts.get(symbol, 0)

    def subscribed_symbols(self) -> list[str]:
        return list(self._refcounts.keys())

"""
Live market-data orchestrator — the one place that owns the Angel One
WebSocket connection, routes ticks into per-symbol candle builders, and
exposes connection/market status. Everything else in the live engine
(candle_builder.py, subscription_manager.py, angelone_ws_transport.py) is
a pure, independently-testable building block this module wires together.

    Angel One WebSocket (angelone_ws_transport.py)
            -> Live Tick Stream
            -> THIS MODULE (routes by token -> symbol)
            -> SymbolCandleSet (candle_builder.py, per symbol)
            -> 15m / 1H / 1D / 1W / 1M live candles
            -> subscribers (backend/api/live.py's SSE stream)

Reused, never duplicated: the existing AngelOneProvider's session
(backend/providers/angelone_provider.py — same login/credentials), the
existing symbol resolver (angelone_scrip_master.resolve_equity), the
existing FUTURE/EQUITY instrument classifier is untouched (this module
never calls it — live data is symbol/token based, independent of that
classification).

Memory safety (2026-09-25, after this project's real Render OOM
incidents): only ONE MarketDataService instance exists per process (see
provider_factory.py), it stores at most a SymbolCandleSet per currently
SUBSCRIBED symbol (bounded by subscription_manager's refcounts — a symbol
with zero references is dropped from `_candle_sets` entirely), and each
SymbolCandleSet itself is bounded (candle_builder.py's history_maxlen).
Raw ticks are never retained past the single on_tick() call.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

from backend.live import market_hours
from backend.live.angelone_ws_transport import (
    EXCHANGE_TYPE_BY_EXCH_SEG,
    AngelOneWebSocketTransport,
    Tick,
    WebSocketTransport,
)
from backend.live.candle_builder import ALL_TIMEFRAMES, SymbolCandleSet, Timeframe
from backend.live.subscription_manager import SubscriptionManager
from backend.providers.angelone_provider import AngelOneProvider

logger = logging.getLogger("scanner.live.market_data_service")

ConnectionState = Literal["CONNECTED", "RECONNECTING", "DISCONNECTED", "STOPPED"]

_HEARTBEAT_INTERVAL_SECONDS = 20.0
_RECONNECT_BASE_DELAY_SECONDS = 1.0
_RECONNECT_MAX_DELAY_SECONDS = 30.0

TickListener = Callable[[str, dict], Awaitable[None]]  # (symbol, {timeframe: LiveCandle.as_dict()})


@dataclass
class _SymbolInfo:
    symbol: str
    token: str
    exch_seg: str
    candles: SymbolCandleSet = field(init=False)

    def __post_init__(self) -> None:
        self.candles = SymbolCandleSet(symbol=self.symbol)


class MarketDataService:
    """One instance lives for the app's lifetime (module-level singleton —
    see provider_factory.py), same pattern as JobManager
    (backend/services/scan_job_manager.py)."""

    def __init__(self, angelone: AngelOneProvider, transport: WebSocketTransport | None = None) -> None:
        self._angelone = angelone
        self._transport: WebSocketTransport = transport or AngelOneWebSocketTransport()
        self._state: ConnectionState = "DISCONNECTED"
        self._last_tick_at: dt.datetime | None = None
        self._symbols_by_token: dict[str, _SymbolInfo] = {}
        self._listeners: list[TickListener] = []
        self._run_task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

        self.subscriptions = SubscriptionManager(
            on_first_subscribe=self._subscribe_symbol, on_last_unsubscribe=self._unsubscribe_symbol,
        )

    # ---- status -------------------------------------------------------

    @property
    def connection_state(self) -> ConnectionState:
        return self._state

    @property
    def last_tick_at(self) -> dt.datetime | None:
        return self._last_tick_at

    def market_state(self) -> market_hours.MarketState:
        return market_hours.market_state()

    def add_listener(self, listener: TickListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: TickListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def get_candles(self, symbol: str) -> dict[Timeframe, dict] | None:
        info = next((s for s in self._symbols_by_token.values() if s.symbol == symbol), None)
        if info is None:
            return None
        return {
            tf: builder.current.as_dict()
            for tf, builder in info.candles.builders.items() if builder.current is not None
        }

    # ---- subscription callbacks (invoked by SubscriptionManager) ------

    async def _subscribe_symbol(self, symbol: str) -> None:
        match = await self._angelone.resolve_equity(symbol)
        if match is None:
            logger.warning("Live subscribe: %s has no Angel One equity listing — skipped, not fatal.", symbol)
            return
        exchange_type = EXCHANGE_TYPE_BY_EXCH_SEG.get(match.exch_seg)
        if exchange_type is None:
            logger.warning("Live subscribe: %s has unsupported exch_seg %r — skipped.", symbol, match.exch_seg)
            return
        self._symbols_by_token[match.token] = _SymbolInfo(symbol=symbol, token=match.token, exch_seg=match.exch_seg)
        await self._ensure_running()
        if self._state == "CONNECTED":
            try:
                await self._transport.subscribe(exchange_type, [match.token])
            except Exception:
                logger.exception("Live subscribe: %s failed to send subscription — will retry on next reconnect.", symbol)

    async def _unsubscribe_symbol(self, symbol: str) -> None:
        entry = next(((t, s) for t, s in self._symbols_by_token.items() if s.symbol == symbol), None)
        if entry is None:
            return
        token, info = entry
        del self._symbols_by_token[token]
        exchange_type = EXCHANGE_TYPE_BY_EXCH_SEG.get(info.exch_seg)
        if self._state == "CONNECTED" and exchange_type is not None:
            try:
                await self._transport.unsubscribe(exchange_type, [token])
            except Exception:
                logger.exception("Live unsubscribe: %s failed to send — harmless, connection will restore only active refs on reconnect.", symbol)
        if not self._symbols_by_token:
            await self.stop()

    # ---- connection lifecycle ------------------------------------------

    async def _ensure_running(self) -> None:
        if self._run_task is None or self._run_task.done():
            self._stopped.clear()
            self._run_task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stops the connection when no symbol needs it any more (last
        subscriber released) — per spec: "Do not continuously poll Angel
        One unnecessarily" when nothing is watching."""
        self._stopped.set()
        if self._run_task is not None:
            self._run_task.cancel()
            self._run_task = None
        await self._transport.close()
        self._state = "STOPPED"

    async def _run(self) -> None:
        delay = _RECONNECT_BASE_DELAY_SECONDS
        while not self._stopped.is_set():
            try:
                session = await self._angelone.get_session()  # same session the REST calls already use
                await self._transport.connect(session)
                self._state = "CONNECTED"
                delay = _RECONNECT_BASE_DELAY_SECONDS
                await self._restore_subscriptions()
                heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                try:
                    async for tick in self._transport.ticks():
                        await self._handle_tick(tick)
                finally:
                    heartbeat_task.cancel()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Live market data connection lost — reconnecting.")
            if self._stopped.is_set():
                break
            self._state = "RECONNECTING"
            await asyncio.sleep(delay)
            delay = min(delay * 2, _RECONNECT_MAX_DELAY_SECONDS)
        if not self._stopped.is_set():
            self._state = "DISCONNECTED"

    async def _restore_subscriptions(self) -> None:
        by_exchange: dict[int, list[str]] = {}
        for info in self._symbols_by_token.values():
            exchange_type = EXCHANGE_TYPE_BY_EXCH_SEG.get(info.exch_seg)
            if exchange_type is not None:
                by_exchange.setdefault(exchange_type, []).append(info.token)
        for exchange_type, tokens in by_exchange.items():
            try:
                await self._transport.subscribe(exchange_type, tokens)
            except Exception:
                logger.exception("Failed to restore live subscriptions for exchange_type=%s — will retry on next reconnect.", exchange_type)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
            heartbeat = getattr(self._transport, "heartbeat", None)
            if heartbeat is not None:
                try:
                    await heartbeat()
                except Exception:
                    logger.warning("Live heartbeat send failed — the receive loop's own reconnect will handle a truly dead connection.")

    async def _handle_tick(self, tick: Tick) -> None:
        """Per-symbol error isolation (spec 2026-09-25 item 22): one bad
        tick/symbol must never take down the stream for every other
        subscribed symbol."""
        info = self._symbols_by_token.get(tick.token)
        if info is None:
            return  # a tick for a token we've since unsubscribed — harmless, drop it
        try:
            self._last_tick_at = tick.exchange_timestamp
            candles = info.candles.on_tick(tick.exchange_timestamp, tick.ltp, tick.day_volume)
            payload = {tf: c.as_dict() for tf, c in candles.items()}
            for listener in list(self._listeners):
                await listener(info.symbol, payload)
        except Exception:
            logger.exception("Live tick handling failed for %s — other symbols unaffected.", info.symbol)

    async def finalize_market_close(self, now: dt.datetime | None = None) -> None:
        """Called once at 15:30 IST (see backend/live/scheduler.py) — marks
        every currently-forming candle complete using the latest data
        already received, WITHOUT waiting for a tick that will never come
        before tomorrow's session. Never fabricates a closing tick."""
        now_ts = now or dt.datetime.now(market_hours.IST)
        for info in self._symbols_by_token.values():
            finalized = info.candles.finalize_at(now_ts, timeframes=("15m", "1H", "1D"))
            if finalized:
                payload = {tf: c.as_dict() for tf, c in finalized.items()}
                for listener in list(self._listeners):
                    await listener(info.symbol, payload)

import asyncio
from dataclasses import dataclass, field

import pytest

from backend.live.angelone_ws_transport import Tick
from backend.live.market_data_service import MarketDataService
from backend.providers.angelone_client import AngelOneSession


@dataclass
class FakeMatch:
    token: str
    trading_symbol: str
    exch_seg: str = "NSE"


class FakeAngelOneProvider:
    def __init__(self, symbols: dict[str, str]):
        self._symbols = symbols  # symbol -> token

    async def resolve_equity(self, symbol: str):
        token = self._symbols.get(symbol)
        return FakeMatch(token=token, trading_symbol=symbol) if token else None

    async def get_session(self) -> AngelOneSession:
        return AngelOneSession(api_key="k", jwt_token="j", feed_token="f", refresh_token="r", client_code="c")


class FakeTransport:
    """Deterministic stand-in for AngelOneWebSocketTransport — feeds ticks
    under test control, records subscribe/unsubscribe calls, and can
    simulate a connection drop to exercise reconnect."""

    def __init__(self):
        self.connected = False
        self.subscribe_calls: list[tuple[int, list[str]]] = []
        self.unsubscribe_calls: list[tuple[int, list[str]]] = []
        self.connect_count = 0
        self._tick_queue: asyncio.Queue = asyncio.Queue()
        self._closed = asyncio.Event()

    async def connect(self, session) -> None:
        self.connected = True
        self.connect_count += 1
        self._closed = asyncio.Event()

    async def subscribe(self, exchange_type, tokens) -> None:
        self.subscribe_calls.append((exchange_type, tokens))

    async def unsubscribe(self, exchange_type, tokens) -> None:
        self.unsubscribe_calls.append((exchange_type, tokens))

    async def push_tick(self, tick: Tick) -> None:
        await self._tick_queue.put(tick)

    async def drop_connection(self) -> None:
        self._closed.set()

    async def ticks(self):
        while True:
            get_task = asyncio.create_task(self._tick_queue.get())
            closed_task = asyncio.create_task(self._closed.wait())
            done, pending = await asyncio.wait({get_task, closed_task}, return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()
            if closed_task in done:
                raise ConnectionError("simulated drop")
            yield get_task.result()

    async def close(self) -> None:
        self.connected = False


async def test_acquiring_a_symbol_starts_the_connection_and_subscribes():
    provider = FakeAngelOneProvider({"BHEL": "1001"})
    transport = FakeTransport()
    service = MarketDataService(provider, transport=transport)

    await service.subscriptions.acquire("BHEL")
    await asyncio.sleep(0.05)  # let the background _run() task connect

    assert transport.connected
    assert (1, ["1001"]) in transport.subscribe_calls
    assert service.connection_state == "CONNECTED"
    await service.stop()


async def test_unknown_symbol_is_skipped_without_crashing():
    provider = FakeAngelOneProvider({})  # BHEL not resolvable
    transport = FakeTransport()
    service = MarketDataService(provider, transport=transport)

    await service.subscriptions.acquire("NOTASYMBOL")
    await asyncio.sleep(0.02)
    # No crash, and nothing was subscribed for it.
    assert transport.subscribe_calls == []
    await service.stop()


async def test_tick_updates_are_delivered_to_listeners():
    provider = FakeAngelOneProvider({"BHEL": "1001"})
    transport = FakeTransport()
    service = MarketDataService(provider, transport=transport)
    received = []

    async def listener(symbol, candles):
        received.append((symbol, candles))

    service.add_listener(listener)
    await service.subscriptions.acquire("BHEL")
    await asyncio.sleep(0.05)

    import datetime as dt

    from backend.live.market_hours import IST

    await transport.push_tick(Tick(
        token="1001", exchange_type=1, ltp=250.5,
        exchange_timestamp=dt.datetime(2026, 9, 25, 10, 0, tzinfo=IST), day_volume=1000.0,
    ))
    await asyncio.sleep(0.05)

    assert len(received) == 1
    symbol, candles = received[0]
    assert symbol == "BHEL"
    assert candles["1D"]["close"] == 250.5
    await service.stop()


async def test_a_tick_for_an_unsubscribed_token_is_dropped_not_crashed():
    provider = FakeAngelOneProvider({"BHEL": "1001"})
    transport = FakeTransport()
    service = MarketDataService(provider, transport=transport)
    received = []
    service.add_listener(lambda symbol, candles: received.append(symbol) or asyncio.sleep(0))

    await service.subscriptions.acquire("BHEL")
    await asyncio.sleep(0.05)

    import datetime as dt

    from backend.live.market_hours import IST

    await transport.push_tick(Tick(
        token="9999-UNKNOWN", exchange_type=1, ltp=99.0,
        exchange_timestamp=dt.datetime(2026, 9, 25, 10, 0, tzinfo=IST), day_volume=1.0,
    ))
    await asyncio.sleep(0.05)
    assert received == []  # dropped silently, no crash
    await service.stop()


async def test_releasing_the_last_symbol_unsubscribes_and_stops():
    provider = FakeAngelOneProvider({"BHEL": "1001"})
    transport = FakeTransport()
    service = MarketDataService(provider, transport=transport)

    await service.subscriptions.acquire("BHEL")
    await asyncio.sleep(0.05)
    await service.subscriptions.release("BHEL")
    await asyncio.sleep(0.05)

    assert (1, ["1001"]) in transport.unsubscribe_calls
    assert service.connection_state == "STOPPED"


async def test_reconnect_restores_subscriptions(monkeypatch):
    import backend.live.market_data_service as mds

    # Reconnect delay starts at 1s in production; patch it down for the
    # test BEFORE the service's _run() loop reads it.
    monkeypatch.setattr(mds, "_RECONNECT_BASE_DELAY_SECONDS", 0.01)

    provider = FakeAngelOneProvider({"BHEL": "1001"})
    transport = FakeTransport()
    service = MarketDataService(provider, transport=transport)

    await service.subscriptions.acquire("BHEL")
    await asyncio.sleep(0.05)
    assert transport.connect_count == 1

    await transport.drop_connection()
    await asyncio.sleep(0.2)

    assert transport.connect_count >= 2
    assert service.connection_state == "CONNECTED"
    # Subscriptions restored on the new connection.
    assert transport.subscribe_calls.count((1, ["1001"])) >= 2
    await service.stop()


async def test_get_candles_returns_none_for_a_symbol_never_subscribed():
    provider = FakeAngelOneProvider({"BHEL": "1001"})
    service = MarketDataService(provider, transport=FakeTransport())
    assert service.get_candles("NOPE") is None


async def test_multiple_symbols_are_isolated_from_each_other():
    provider = FakeAngelOneProvider({"BHEL": "1001", "RELIANCE": "2002"})
    transport = FakeTransport()
    service = MarketDataService(provider, transport=transport)

    await service.subscriptions.acquire("BHEL")
    await service.subscriptions.acquire("RELIANCE")
    await asyncio.sleep(0.05)

    import datetime as dt

    from backend.live.market_hours import IST

    await transport.push_tick(Tick(
        token="1001", exchange_type=1, ltp=250.0,
        exchange_timestamp=dt.datetime(2026, 9, 25, 10, 0, tzinfo=IST), day_volume=1.0,
    ))
    await asyncio.sleep(0.05)

    bhel_candles = service.get_candles("BHEL")
    reliance_candles = service.get_candles("RELIANCE")
    assert bhel_candles is not None and bhel_candles["1D"]["close"] == 250.0
    assert reliance_candles == {}  # subscribed, but no tick received for it yet
    await service.stop()

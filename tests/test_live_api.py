import asyncio
import json

import pytest

import backend.api.live as live_api


class _FakeSubscriptions:
    def __init__(self):
        self.acquired = []
        self.released = []

    async def acquire(self, symbol):
        self.acquired.append(symbol)

    async def release(self, symbol):
        self.released.append(symbol)

    def subscribed_symbols(self):
        return list(self.acquired)


class _FakeService:
    def __init__(self):
        self.connection_state = "CONNECTED"
        self.last_tick_at = None
        self.subscriptions = _FakeSubscriptions()
        self._listeners = []

    def market_state(self):
        return "MARKET_OPEN"

    def add_listener(self, listener):
        self._listeners.append(listener)

    def remove_listener(self, listener):
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def emit(self, symbol, candles):
        for listener in list(self._listeners):
            await listener(symbol, candles)


async def test_status_endpoint_reports_connection_and_market_state(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(live_api, "get_live_market_data_service", lambda: fake)

    result = await live_api.get_status()
    assert result["connection_state"] == "CONNECTED"
    assert result["market_state"] == "MARKET_OPEN"
    assert result["subscribed_symbols"] == []


async def test_stream_endpoint_acquires_symbol_on_connect(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(live_api, "get_live_market_data_service", lambda: fake)

    response = await live_api.stream_symbol("bhel")  # lowercase - must normalize
    generator = response.body_iterator

    # Kick the generator to its first `yield` point (it awaits queue.get()
    # after acquiring) — give the event loop a turn so acquire() completes.
    task = asyncio.ensure_future(generator.__anext__())
    await asyncio.sleep(0.02)
    assert fake.subscriptions.acquired == ["BHEL"]

    await fake.emit("BHEL", {"1D": {"close": 100.0}})
    chunk = await task
    assert "BHEL" not in chunk  # payload is just the candles dict, symbol is implicit in the URL
    assert "close" in chunk

    await generator.aclose()
    await asyncio.sleep(0.02)
    assert fake.subscriptions.released == ["BHEL"]


async def test_stream_endpoint_ignores_ticks_for_other_symbols(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(live_api, "get_live_market_data_service", lambda: fake)

    response = await live_api.stream_symbol("BHEL")
    generator = response.body_iterator
    task = asyncio.ensure_future(generator.__anext__())
    await asyncio.sleep(0.02)

    await fake.emit("RELIANCE", {"1D": {"close": 999.0}})  # different symbol - must not surface
    await asyncio.sleep(0.02)
    assert not task.done()

    await fake.emit("BHEL", {"1D": {"close": 250.0}})
    chunk = await task
    assert "250.0" in chunk

    await generator.aclose()

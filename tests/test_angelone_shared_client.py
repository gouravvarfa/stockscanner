"""Angel One calls reuse one HTTPS client and one TLS context (a new one per request ran Render out of memory)."""
from __future__ import annotations

import asyncio
import ssl
import time

import httpx

from backend.providers import angelone_client as ac


def _patch(monkeypatch, seen_cookies: list):
    made, tls = [], []
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        seen_cookies.append(request.headers.get("cookie"))
        body = {"status": True, "data": [["2026-11-20T00:00:00+05:30", 1, 2, 0.5, 1.5, 10]]}
        return httpx.Response(200, json=body, headers={"set-cookie": "lb=abc; Path=/"})

    def client_factory(**kwargs):
        made.append(dict(kwargs))
        kwargs.pop("verify", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    def tls_factory():
        tls.append(1)
        return ssl.create_default_context()

    monkeypatch.setattr(ac.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(ac.httpx, "create_ssl_context", tls_factory)
    monkeypatch.setattr(ac, "_ssl_context", None)
    monkeypatch.setattr(ac, "CANDLE_GAP_S", 0.0)
    monkeypatch.setattr(ac, "_next_slot", 0.0)
    ac._clients.clear()
    return made, tls


SESSION = ac.AngelOneSession(api_key="k", jwt_token="t", feed_token="", refresh_token="", client_code="C1")


async def test_candle_calls_share_one_client_and_one_tls_context(monkeypatch):
    cookies: list = []
    made, tls = _patch(monkeypatch, cookies)

    for _ in range(5):
        rows = await ac.get_candle_data(SESSION, "NSE", "1", "ONE_DAY", "2026-11-01 00:00", "2026-11-20 23:59")
        assert rows[0][4] == 1.5
    await asyncio.gather(*(ac.get_candle_data(SESSION, "NSE", "1", "ONE_DAY", "a", "b") for _ in range(4)))

    assert len(made) == 1 and len(tls) == 1
    assert made[0]["verify"] is ac._ssl_context
    assert cookies == [None] * 9  # a Set-Cookie from Angel One is never sent back on later requests

    await ac.aclose_http()
    assert asyncio.get_running_loop() not in ac._clients


async def test_a_closed_client_is_replaced_but_the_tls_context_is_kept(monkeypatch):
    made, tls = _patch(monkeypatch, [])
    await ac.get_candle_data(SESSION, "NSE", "1", "ONE_DAY", "a", "b")
    await ac._clients[asyncio.get_running_loop()].aclose()
    await ac.get_candle_data(SESSION, "NSE", "1", "ONE_DAY", "a", "b")
    assert len(made) == 2 and len(tls) == 1
    await ac.aclose_http()


async def test_candle_requests_are_paced_and_a_403_backs_everyone_off(monkeypatch):
    _patch(monkeypatch, [])
    monkeypatch.setattr(ac, "CANDLE_GAP_S", 0.05)
    t0 = time.monotonic()
    await asyncio.gather(*(ac.get_candle_data(SESSION, "NSE", "1", "ONE_DAY", "a", "b") for _ in range(5)))
    assert time.monotonic() - t0 >= 0.19  # 5 requests start at least 4 gaps apart, even when fired together

    monkeypatch.setattr(ac, "RATE_LIMIT_BACKOFF_S", 0.3)
    before = time.monotonic()
    ac._back_off()
    assert ac._next_slot >= before + 0.3
    t1 = time.monotonic()
    await ac.get_candle_data(SESSION, "NSE", "1", "ONE_DAY", "a", "b")
    assert time.monotonic() - t1 >= 0.25
    await ac.aclose_http()

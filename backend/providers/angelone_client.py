"""
Thin REST client over Angel One's SmartAPI — the only market-data provider
in this project (daily, intraday 15m/1h, and stock-future OHLCV).

Endpoints/payload shapes are taken from Angel One's own SmartAPI reference
(https://smartapi.angelone.in/docs), the same source the project's other
Angel One integration (a separate, unrelated project on this machine) was
built from — nothing was copied from that project; this is an independent
implementation.
"""
from __future__ import annotations

import asyncio
import http.cookiejar
import logging
import ssl
import time
import weakref
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, TypeVar

import httpx
import pyotp

from backend.providers import call_metrics

logger = logging.getLogger("scanner.angelone_client")

T = TypeVar("T")

BASE_URL = "https://apiconnect.angelone.in"

ROUTES = {
    "login": "/rest/auth/angelbroking/user/v1/loginByPassword",
    "candle_data": "/rest/secure/angelbroking/historical/v1/getCandleData",
    "logout": "/rest/secure/angelbroking/user/v1/logout",
}

AngelOneInterval = Literal[
    "ONE_MINUTE", "THREE_MINUTE", "FIVE_MINUTE", "TEN_MINUTE",
    "FIFTEEN_MINUTE", "THIRTY_MINUTE", "ONE_HOUR", "ONE_DAY",
]


class AngelOneApiError(Exception):
    def __init__(self, message: str, kind: Literal["auth", "network", "data"], retryable: bool = False):
        super().__init__(message)
        self.kind = kind
        # True for transient-looking failures (network errors, non-JSON
        # responses — often a rate-limit page or a momentary proxy hiccup,
        # observed in practice on the historical-candle endpoint). False for
        # a real JSON error body Angel One returned deliberately (bad
        # symbol, invalid auth, etc.) — retrying those would just waste
        # calls against a strict daily/per-second quota for no benefit.
        self.retryable = retryable


@dataclass
class AngelOneSession:
    api_key: str
    jwt_token: str
    feed_token: str
    refresh_token: str
    client_code: str


def _base_headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-PrivateKey": api_key,
        # Angel's API expects these to be present; server-side we have no
        # meaningful local/public IP or MAC to report, so — like every
        # community integration — we send harmless placeholders.
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": "127.0.0.1",
        "X-MACAddress": "00:00:00:00:00:00",
    }


# ---- One HTTPS client for every call (2026-11-21) ---------------------------------------------------------------
# Every request used to open its own httpx.AsyncClient, i.e. a new TLS context that loads the whole CA bundle
# (OpenSSL 3) plus a fresh TLS handshake. On Render (Linux) that memory was never handed back: RSS climbed ~1.5 MB
# per instrument (167 -> 527 MB over a 200-stock Weekly Sectors run) until the 512 MB limit killed the instance -
# the same climb as the A Group scan's OOMs. Now one TLS context is built once, and each event loop keeps one
# client whose keep-alive connections are reused. Cookies are never stored, so nothing from one request (or one
# Angel One account) rides along on the next - exactly like the old one-client-per-request behaviour.
_ssl_context: ssl.SSLContext | None = None
_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = weakref.WeakKeyDictionary()
_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=8, keepalive_expiry=20.0)


def _tls() -> ssl.SSLContext:
    global _ssl_context
    if _ssl_context is None:  # built on first use, after main.py's truststore.inject_into_ssl()
        _ssl_context = httpx.create_ssl_context()
    return _ssl_context


def _no_cookies() -> http.cookiejar.CookieJar:
    # A bare CookieJar (httpx keeps it as is; an httpx.Cookies would be copied into a default jar, losing the policy).
    return http.cookiejar.CookieJar(policy=http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))


def _http() -> httpx.AsyncClient:
    """The shared client of the running event loop (a client's connections belong to one loop)."""
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(verify=_tls(), timeout=20.0, limits=_LIMITS, cookies=_no_cookies())
        _clients[loop] = client
    return client


# Candle requests are paced process-wide. A new client per request used to slow every call down by a full TLS
# handshake (~1.5 requests/s in total at the scans' concurrency of 2), which happened to keep them under Angel One's
# candle rate limit. With reused connections the same concurrency fires much faster and draws HTTP 403s (a live
# Weekly Sectors run: 291 retries, 5 stocks lost; a probe at ~2.5/s: 19 of 30 refused, and a refused burst keeps
# being refused for a while). Measured after a 60 s rest: ~1.5/s gets no 403s. So requests start at least
# CANDLE_GAP_S apart (~1.7 per second in total, whatever runs at the same time - the old speed), and a 403 pushes
# every caller back a little so the burst can clear.
CANDLE_GAP_S = 0.6
RATE_LIMIT_BACKOFF_S = 1.0
_next_slot = 0.0


async def _pace() -> None:
    global _next_slot
    now = time.monotonic()
    slot = max(now, _next_slot)
    _next_slot = slot + CANDLE_GAP_S  # reserved before awaiting, so concurrent callers queue up behind it
    if slot > now:
        await asyncio.sleep(slot - now)


def _back_off() -> None:
    global _next_slot
    _next_slot = max(_next_slot, time.monotonic() + RATE_LIMIT_BACKOFF_S)


async def aclose_http() -> None:
    """Close the running loop's shared client (app shutdown)."""
    client = _clients.pop(asyncio.get_running_loop(), None)
    if client is not None:
        await client.aclose()


def generate_totp(base32_secret: str) -> str:
    return pyotp.TOTP(base32_secret).now()


async def _retry_async(
    fn: Callable[[], Awaitable[T]], max_attempts: int = 3, base_delay_seconds: float = 0.75
) -> T:
    """Retries only AngelOneApiError(retryable=True) with exponential backoff.
    A non-retryable error (a real API-reported failure) or the final attempt
    propagates immediately."""
    last_exc: AngelOneApiError | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except AngelOneApiError as exc:
            if not exc.retryable or attempt == max_attempts - 1:
                raise
            last_exc = exc
            delay = base_delay_seconds * (2**attempt)
            logger.warning(
                "Angel One call failed (attempt %d/%d, retryable): %s — retrying in %.1fs",
                attempt + 1, max_attempts, exc, delay,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None  # unreachable: loop always returns or raises above
    raise last_exc


async def login(api_key: str, client_code: str, pin: str, totp_secret: str) -> AngelOneSession:
    async def _attempt() -> AngelOneSession:
        totp = generate_totp(totp_secret)  # regenerated each attempt: a stale 30s-window code would just fail again
        try:
            response = await _http().post(
                BASE_URL + ROUTES["login"],
                headers=_base_headers(api_key),
                json={"clientcode": client_code, "password": pin, "totp": totp},
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise AngelOneApiError(f"Could not reach Angel One: {exc}", "network", retryable=True) from exc

        body = _parse_json_or_raise(response, "auth")
        if response.status_code != 200 or body.get("status") is not True or not body.get("data", {}).get("jwtToken"):
            # Wrong credentials/PIN/TOTP secret won't fix itself on retry.
            raise AngelOneApiError(body.get("message", "Angel One authentication failed"), "auth", retryable=False)

        data = body["data"]
        return AngelOneSession(
            api_key=api_key,
            jwt_token=data["jwtToken"],
            feed_token=data.get("feedToken", ""),
            refresh_token=data.get("refreshToken", ""),
            client_code=client_code,
        )

    return await _retry_async(_attempt)


async def logout(session: AngelOneSession) -> None:
    try:
        await _http().post(
            BASE_URL + ROUTES["logout"],
            headers={**_base_headers(session.api_key), "Authorization": f"Bearer {session.jwt_token}"},
            json={"clientcode": session.client_code},
            timeout=10.0,
        )
    except httpx.HTTPError:
        pass  # best-effort — a failed logout shouldn't block anything


def _parse_json_or_raise(response: httpx.Response, kind: Literal["auth", "network", "data"]) -> dict[str, Any]:
    try:
        return response.json()
    except ValueError as exc:
        # A non-JSON body (e.g. a blank/HTML page) on a 403/5xx from this
        # endpoint has been observed to be transient in practice — retryable.
        raise AngelOneApiError(
            f"Angel One returned a non-JSON response (HTTP {response.status_code}).", kind, retryable=True
        ) from exc


async def get_candle_data(
    session: AngelOneSession,
    exchange: str,
    symbol_token: str,
    interval: AngelOneInterval,
    from_date: str,
    to_date: str,
) -> list[list[Any]]:
    """`from_date`/`to_date` format: 'YYYY-MM-DD HH:MM'. Returns rows of
    [timestamp_iso, open, high, low, close, volume]. Transient failures
    (network errors, non-JSON responses) are retried automatically."""

    async def _attempt() -> list[list[Any]]:
        await _pace()
        call_metrics.record_angelone_call()
        try:
            response = await _http().post(
                BASE_URL + ROUTES["candle_data"],
                headers={**_base_headers(session.api_key), "Authorization": f"Bearer {session.jwt_token}"},
                json={
                    "exchange": exchange,
                    "symboltoken": symbol_token,
                    "interval": interval,
                    "fromdate": from_date,
                    "todate": to_date,
                },
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            raise AngelOneApiError(f"Could not reach Angel One: {exc}", "network", retryable=True) from exc

        if response.status_code == 403:
            _back_off()
        body = _parse_json_or_raise(response, "data")
        if response.status_code != 200 or body.get("status") is not True:
            # A real JSON error body — Angel One deliberately rejected the
            # request (bad token, bad params, etc.), so retrying won't help.
            raise AngelOneApiError(body.get("message", "Unable to load candle data"), "data", retryable=False)

        return body.get("data") or []

    return await _retry_async(_attempt)

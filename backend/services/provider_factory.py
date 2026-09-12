from __future__ import annotations

import asyncio

from backend.providers import tapetide_status
from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.market_data_router import MarketDataRouter
from backend.providers.tapetide_client import TapetideMCPClient
from backend.providers.tapetide_provider import TapetideProvider

_client: TapetideMCPClient | None = None
_provider: TapetideProvider | None = None
_angelone_provider: AngelOneProvider | None = None
_router: MarketDataRouter | None = None

# The Tapetide MCP SDK's streamable_http_client is an @asynccontextmanager
# that spawns a background task group (for its auto-reconnecting GET/SSE
# stream) tied to whichever asyncio Task calls __aenter__(). anyio requires
# a cancel scope to be entered AND exited by that same task. Calling
# __aenter__()/__aexit__() from a short-lived per-request task (as an
# earlier version of reconnect_tapetide() did) works for the immediate call,
# but the background stream task it leaves running is then orphaned from
# its owning task — the next time Tapetide's stream drops and that
# background task tries to reconnect, anyio's cancel-scope teardown hits
# "Attempted to exit cancel scope in a different task than it was entered
# in", which cascades into cancelling FastAPI's lifespan task and crashes
# the whole server (confirmed reproducible: reconnect succeeds, a later
# scan gets a stream failure, then the crash trace appears).
#
# Fix: a single persistent background task owns the Tapetide client for its
# entire life, including across reconnects. Request handlers never call
# __aenter__/__aexit__ themselves — they just signal this task and wait for
# it to report ready.
_owner_task: asyncio.Task | None = None
_reconnect_event: asyncio.Event | None = None
_ready_event: asyncio.Event | None = None
_stop_event: asyncio.Event | None = None
_last_connect_error: str | None = None

# Tapetide's OAuth token endpoint is intermittently flaky (observed: sporadic
# HTTP 500 "error code: 1101" on /token, self-resolving within seconds to
# minutes) — a connect attempt that lands in that window can otherwise sit
# retrying/re-authing for a long time with no feedback. These cap the worst
# case so a failure is reported quickly instead of the caller just waiting.
_TEARDOWN_TIMEOUT_SECONDS = 8
_CONNECT_TIMEOUT_SECONDS = 18


async def _tapetide_owner_loop() -> None:
    global _client, _provider, _router, _last_connect_error
    assert _reconnect_event is not None and _ready_event is not None and _stop_event is not None

    while True:
        old_client, _client = _client, None
        if old_client is not None:
            try:
                await asyncio.wait_for(old_client.__aexit__(None, None, None), timeout=_TEARDOWN_TIMEOUT_SECONDS)
            except Exception:  # noqa: BLE001 — including TimeoutError; the old session may already be broken
                pass

        try:
            new_client = TapetideMCPClient()
            await asyncio.wait_for(new_client.__aenter__(), timeout=_CONNECT_TIMEOUT_SECONDS)
            _client = new_client
            _provider = TapetideProvider(_client)
            if _angelone_provider is not None:
                _router = MarketDataRouter(_provider, _angelone_provider)
            _last_connect_error = None
            tapetide_status.record_reconnected()
        except asyncio.TimeoutError:
            _last_connect_error = (
                f"Timed out after {_CONNECT_TIMEOUT_SECONDS}s — Tapetide's OAuth server is likely being slow/flaky "
                "right now. Try again in a moment."
            )
            tapetide_status.record_disconnected(_last_connect_error)
        except Exception as exc:  # noqa: BLE001 — reported via _last_connect_error, never crashes this task
            _last_connect_error = str(exc)
            tapetide_status.record_disconnected(f"Tapetide connect failed: {exc}")

        _ready_event.set()

        reconnect_wait = asyncio.create_task(_reconnect_event.wait())
        stop_wait = asyncio.create_task(_stop_event.wait())
        try:
            await asyncio.wait({reconnect_wait, stop_wait}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            reconnect_wait.cancel()
            stop_wait.cancel()

        if _stop_event.is_set():
            if _client is not None:
                try:
                    await _client.__aexit__(None, None, None)
                except Exception:  # noqa: BLE001
                    pass
                _client = None
            return

        _reconnect_event.clear()
        _ready_event.clear()


async def startup() -> None:
    global _angelone_provider, _owner_task, _reconnect_event, _ready_event, _stop_event
    _angelone_provider = AngelOneProvider()
    _reconnect_event = asyncio.Event()
    _ready_event = asyncio.Event()
    _stop_event = asyncio.Event()
    _owner_task = asyncio.create_task(_tapetide_owner_loop())
    await _ready_event.wait()
    if _provider is None:
        raise RuntimeError(f"Tapetide failed to connect at startup: {_last_connect_error}")


async def shutdown() -> None:
    global _owner_task, _reconnect_event, _ready_event, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _owner_task is not None:
        await _owner_task
    _owner_task = None
    _reconnect_event = None
    _ready_event = None
    _stop_event = None


async def reconnect_tapetide() -> None:
    """
    Asks the persistent owner task to tear down and rebuild the Tapetide
    session, then waits (bounded) for it to report ready. Never touches
    __aenter__/__aexit__ directly — see _tapetide_owner_loop for why.
    """
    if _reconnect_event is None or _ready_event is None:
        raise RuntimeError("Tapetide owner task is not running — app startup has not run yet.")
    _ready_event.clear()
    _reconnect_event.set()
    # A little above the owner loop's own teardown+connect caps combined, so
    # this only fires if something outside those bounded steps also hangs.
    outer_timeout = _TEARDOWN_TIMEOUT_SECONDS + _CONNECT_TIMEOUT_SECONDS + 5
    try:
        await asyncio.wait_for(_ready_event.wait(), timeout=outer_timeout)
    except asyncio.TimeoutError as exc:
        raise RuntimeError(f"Tapetide reconnect timed out after {outer_timeout}s.") from exc
    if _provider is None:
        raise RuntimeError(f"Tapetide reconnect failed: {_last_connect_error}")


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

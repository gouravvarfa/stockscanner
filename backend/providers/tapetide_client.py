"""
Standalone MCP client for the Tapetide server, independent of any Claude
Code session — this is what lets the FastAPI backend (background scans,
Celery tasks) reach Tapetide on its own.

Auth: MCP OAuth (dynamic client registration + authorization code + PKCE).
On first use it opens the user's browser once; the resulting token and
client registration are cached to a local JSON file so subsequent runs
don't need to re-authenticate until the token expires.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)

from backend.core.config import settings

CALLBACK_PORT = 44601
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://127.0.0.1:{CALLBACK_PORT}{CALLBACK_PATH}"

# Treat a token that expires within this window as already dead, so a refresh
# happens before the access token lapses mid-request rather than after.
EXPIRY_SAFETY_MARGIN_SECONDS = 60


class FileTokenStorage(TokenStorage):
    """
    Persists OAuth tokens + dynamically-registered client info to a local JSON file.

    OAuthToken only carries a RELATIVE `expires_in`, and the MCP client tracks
    the absolute expiry solely in memory (OAuthContext.token_expiry_time, set by
    update_token_expiry() when a token is freshly issued — never when one is
    loaded from storage). So a token restored from disk arrives with
    token_expiry_time=None, which is_token_valid() reads as "no known expiry =
    still valid", making the client attach a long-dead access token, get a 401,
    and fall all the way back to a full browser re-authorization on every
    restart — even though the stored refresh token was still perfectly usable.

    Persisting an absolute `expires_at` alongside the token closes that gap.
    """

    def __init__(self, path: str):
        self._path = Path(path)

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def _write(self, data: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(data, indent=2))

    async def get_tokens(self) -> OAuthToken | None:
        data = self._read().get("tokens")
        if not data:
            return None
        data = dict(data)
        expires_at = data.pop("expires_at", None)
        token = OAuthToken(**data)

        # A token written before `expires_at` was recorded has an unknowable
        # issue time, so it cannot be trusted as live — refresh it rather than
        # gamble a 401 and a browser round-trip on it.
        expired = expires_at is None or (float(expires_at) - time.time()) <= EXPIRY_SAFETY_MARGIN_SECONDS

        if expired:
            if token.refresh_token:
                # Blanking the access token (while leaving refresh_token intact)
                # is what makes the client take the refresh path: is_token_valid()
                # becomes False while can_refresh_token() stays True.
                token.access_token = ""
        elif expires_at is not None:
            token.expires_in = int(float(expires_at) - time.time())
        return token

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._read()
        payload = tokens.model_dump(mode="json", exclude_none=True)
        if tokens.expires_in is not None:
            payload["expires_at"] = time.time() + tokens.expires_in
        data["tokens"] = payload
        self._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        data = self._read().get("client_info")
        return OAuthClientInformationFull(**data) if data else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._read()
        data["client_info"] = client_info.model_dump(mode="json", exclude_none=True)
        self._write(data)


class _CallbackResult:
    def __init__(self) -> None:
        self.code: str | None = None
        self.state: str | None = None
        self.error: str | None = None
        self.event = threading.Event()


def _run_callback_server(result: _CallbackResult) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return
            qs = parse_qs(parsed.query)
            result.code = qs.get("code", [None])[0]
            result.state = qs.get("state", [None])[0]
            result.error = qs.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<h2>Tapetide authorization complete</h2>"
                b"<p>You can close this tab and return to the scanner app.</p>"
            )
            result.event.set()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass

    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def _redirect_handler(authorization_url: str) -> None:
    print(f"\nOpen this URL to authorize the scanner's Tapetide connection:\n{authorization_url}\n")
    webbrowser.open(authorization_url)


def _make_callback_handler():
    async def _callback_handler() -> AuthorizationCodeResult:
        result = _CallbackResult()
        server = _run_callback_server(result)
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: result.event.wait(timeout=300)
            )
        finally:
            server.shutdown()

        if result.error:
            raise RuntimeError(f"Tapetide authorization failed: {result.error}")
        if not result.code:
            raise TimeoutError("Timed out waiting for Tapetide authorization callback")
        return AuthorizationCodeResult(code=result.code, state=result.state)

    return _callback_handler


def build_oauth_provider() -> OAuthClientProvider:
    storage = FileTokenStorage(settings.tapetide_token_cache_path)
    metadata = OAuthClientMetadata(
        redirect_uris=[REDIRECT_URI],
        client_name="NIFTY 200 Scanner (backend)",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
    )
    return OAuthClientProvider(
        server_url=settings.tapetide_mcp_url,
        client_metadata=metadata,
        storage=storage,
        redirect_handler=_redirect_handler,
        callback_handler=_make_callback_handler(),
    )


class TapetideMCPClient:
    """Thin async context manager around an authenticated MCP ClientSession for Tapetide."""

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._cm = None

    async def __aenter__(self) -> "TapetideMCPClient":
        from mcp.client.streamable_http import create_mcp_http_client

        auth = build_oauth_provider()
        http_client = create_mcp_http_client(auth=auth)
        self._transport_cm = streamable_http_client(settings.tapetide_mcp_url, http_client=http_client)
        read_stream, write_stream = await self._transport_cm.__aenter__()
        self._session_cm = ClientSession(read_stream, write_stream)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._session is not None:
            await self._session_cm.__aexit__(*exc)
        await self._transport_cm.__aexit__(*exc)

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        from backend.providers import tapetide_status

        assert self._session is not None, "TapetideMCPClient must be used as an async context manager"
        result = await self._session.call_tool(tool_name, arguments)
        if result.is_error:
            message = f"Tapetide tool '{tool_name}' returned an error: {result.content}"
            tapetide_status.record_error(message)
            raise RuntimeError(message)
        tapetide_status.record_success()
        for block in result.content:
            if getattr(block, "type", None) == "text":
                # Some tools append a non-JSON "[TRUNCATED: ...]" note after an
                # otherwise complete, validly-closed JSON document when the
                # underlying result is large. raw_decode parses just the JSON
                # prefix and ignores that trailing note instead of erroring on it.
                try:
                    obj, _ = json.JSONDecoder().raw_decode(block.text)
                    return obj
                except json.JSONDecodeError:
                    return block.text
        return None

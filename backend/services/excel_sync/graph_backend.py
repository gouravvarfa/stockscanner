"""
Microsoft Graph Excel backend. Talks to the ONE permanent OneDrive workbook
(resolved from its sharing URL) — create worksheet, write headers, write
row ranges — inside a persistent workbook session. Secrets/config come from
backend.core.config.settings (env / .env); nothing is hardcoded.

Auth: OAuth2 refresh-token grant (obtain the refresh token once with
tools/onedrive_auth.py). The app registration needs the delegated
permissions Files.ReadWrite and offline_access.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, Protocol

import httpx

from backend.core.config import settings
from backend.services.excel_sync.rows import HEADERS, LAST_COLUMN

logger = logging.getLogger("scanner.excel_sync.graph")
GRAPH = "https://graph.microsoft.com/v1.0"


class WorkbookBackend(Protocol):
    async def create_sheet(self, name: str) -> bool:
        """Create worksheet + header row. True if newly created, False if a
        sheet with that name already exists (left untouched)."""

    async def write_rows(self, name: str, start_row: int, rows: list[list[Any]]) -> None:
        """Write `rows` into contiguous rows starting at `start_row`
        (idempotent: same range = same cells)."""


def encode_share_url(url: str) -> str:
    return "u!" + base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


class GraphWorkbookBackend:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._token: str | None = None
        self._token_expiry = 0.0
        self._base: str | None = None  # .../drives/{d}/items/{i}/workbook
        self._session_id: str | None = None
        self._lock = asyncio.Lock()

    async def _access_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        data = {
            "client_id": settings.ms_graph_client_id,
            "grant_type": "refresh_token",
            "refresh_token": settings.ms_graph_refresh_token,
            "scope": "https://graph.microsoft.com/Files.ReadWrite offline_access",
        }
        if settings.ms_graph_client_secret:
            data["client_secret"] = settings.ms_graph_client_secret
        r = await self._client.post(
            f"https://login.microsoftonline.com/{settings.ms_graph_tenant}/oauth2/v2.0/token", data=data
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_expiry = time.time() + int(body.get("expires_in", 3600))
        return self._token

    async def _request(self, method: str, url: str, *, json: Any = None, session: bool = True) -> httpx.Response:
        r: httpx.Response | None = None
        for attempt in range(4):
            headers = {"Authorization": f"Bearer {await self._access_token()}"}
            if session and self._session_id:
                headers["workbook-session-id"] = self._session_id
            r = await self._client.request(method, url, headers=headers, json=json)
            if r.status_code in (429, 503, 504):
                await asyncio.sleep(min(float(r.headers.get("Retry-After", 2**attempt)), 30))
                continue
            if r.status_code == 401:
                self._token = None
                continue
            return r
        assert r is not None
        return r

    async def _open_session(self, base: str) -> None:
        s = await self._request("POST", f"{base}/createSession", json={"persistChanges": True}, session=False)
        self._session_id = s.json().get("id") if s.status_code < 300 else None

    async def _ensure_workbook(self) -> str:
        if self._base:
            return self._base
        share = encode_share_url(settings.onedrive_workbook_url)
        r = await self._request("GET", f"{GRAPH}/shares/{share}/driveItem", session=False)
        r.raise_for_status()
        item = r.json()
        self._base = f"{GRAPH}/drives/{item['parentReference']['driveId']}/items/{item['id']}/workbook"
        await self._open_session(self._base)
        return self._base

    async def create_sheet(self, name: str) -> bool:
        async with self._lock:
            base = await self._ensure_workbook()
            exists = await self._request("GET", f"{base}/worksheets/{name}")
            if exists.status_code == 200:
                return False
            r = await self._request("POST", f"{base}/worksheets/add", json={"name": name})
            if r.status_code == 409 or (r.status_code == 400 and "already exists" in r.text.lower()):
                return False
            r.raise_for_status()
            await self._write(base, name, 1, [HEADERS])
            return True

    async def _write(self, base: str, name: str, start_row: int, rows: list[list[Any]]) -> None:
        end = start_row + len(rows) - 1
        url = f"{base}/worksheets/{name}/range(address='A{start_row}:{LAST_COLUMN}{end}')"
        r = await self._request("PATCH", url, json={"values": rows})
        if r.status_code == 404 and self._session_id:  # expired workbook session: reopen once and retry
            await self._open_session(base)
            r = await self._request("PATCH", url, json={"values": rows})
        r.raise_for_status()

    async def write_rows(self, name: str, start_row: int, rows: list[list[Any]]) -> None:
        async with self._lock:
            await self._write(await self._ensure_workbook(), name, start_row, rows)


def get_default_backend() -> WorkbookBackend | None:
    return GraphWorkbookBackend() if settings.excel_sync_configured else None

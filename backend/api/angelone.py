from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.providers.angelone_client import AngelOneApiError, login
from backend.services import angelone_credential_store
from backend.services.provider_factory import get_angelone_provider

router = APIRouter(prefix="/api/expiry/angelone", tags=["angelone"])


class ConnectRequest(BaseModel):
    api_key: str
    client_code: str
    pin: str
    totp_secret: str


class StatusOut(BaseModel):
    configured: bool
    client_code: str | None = None
    message: str
    connected_at: str | None = None


class TestResultOut(BaseModel):
    success: bool
    message: str


@router.get("/status", response_model=StatusOut)
def get_status() -> StatusOut:
    credentials = angelone_credential_store.get_credentials()
    if credentials is None:
        return StatusOut(configured=False, message="Not connected.")
    return StatusOut(
        configured=True,
        client_code=credentials.client_code,
        message=f"Connected as {credentials.client_code}",
        connected_at=credentials.connected_at,
    )


@router.post("/test-connection", response_model=TestResultOut)
async def test_connection(body: ConnectRequest) -> TestResultOut:
    """
    Attempts a real login with the given credentials WITHOUT saving
    anything or touching the currently-active session — lets the Settings
    UI verify new values before committing to them via /connect.
    """
    try:
        session = await login(body.api_key, body.client_code, body.pin, body.totp_secret)
    except AngelOneApiError as exc:
        return TestResultOut(success=False, message=str(exc))
    return TestResultOut(success=True, message=f"Login succeeded as {session.client_code}.")


@router.post("/connect", response_model=StatusOut)
async def connect(body: ConnectRequest) -> StatusOut:
    # Actually attempt a real login before saving anything — never persist
    # credentials we haven't verified work, and never fabricate "connected".
    try:
        session = await login(body.api_key, body.client_code, body.pin, body.totp_secret)
    except AngelOneApiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    connected_at = dt.datetime.utcnow().isoformat()
    angelone_credential_store.save_credentials(
        angelone_credential_store.AngelOneCredentials(
            api_key=body.api_key, client_code=body.client_code, pin=body.pin, totp_secret=body.totp_secret,
            connected_at=connected_at,
        )
    )
    # This one shared provider instance is what scan_service, chart_service,
    # and both expiry scan services all call via get_angelone_provider() —
    # resetting its session here is the ONLY place a new login takes
    # effect, so every consumer picks up the new credentials immediately
    # without needing its own separate connect flow.
    get_angelone_provider().reset_session()

    return StatusOut(configured=True, client_code=session.client_code, message=f"Connected as {session.client_code}", connected_at=connected_at)


@router.post("/disconnect", response_model=StatusOut)
def disconnect() -> StatusOut:
    angelone_credential_store.clear_credentials()
    get_angelone_provider().reset_session()
    return StatusOut(configured=False, message="Disconnected.")

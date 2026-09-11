from __future__ import annotations

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


@router.get("/status", response_model=StatusOut)
def get_status() -> StatusOut:
    credentials = angelone_credential_store.get_credentials()
    if credentials is None:
        return StatusOut(configured=False, message="Not connected.")
    return StatusOut(configured=True, client_code=credentials.client_code, message=f"Connected as {credentials.client_code}")


@router.post("/connect", response_model=StatusOut)
async def connect(body: ConnectRequest) -> StatusOut:
    # Actually attempt a real login before saving anything — never persist
    # credentials we haven't verified work, and never fabricate "connected".
    try:
        session = await login(body.api_key, body.client_code, body.pin, body.totp_secret)
    except AngelOneApiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    angelone_credential_store.save_credentials(
        angelone_credential_store.AngelOneCredentials(
            api_key=body.api_key, client_code=body.client_code, pin=body.pin, totp_secret=body.totp_secret
        )
    )
    get_angelone_provider().reset_session()

    return StatusOut(configured=True, client_code=session.client_code, message=f"Connected as {session.client_code}")


@router.post("/disconnect", response_model=StatusOut)
def disconnect() -> StatusOut:
    angelone_credential_store.clear_credentials()
    get_angelone_provider().reset_session()
    return StatusOut(configured=False, message="Disconnected.")

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.database import get_db
from backend.models.tradingview_signal import TradingViewSignal
from backend.schemas.tradingview import (
    TradingViewSignalOut,
    TradingViewStatusOut,
    TradingViewWebhookPayload,
    TradingViewWebhookResponse,
)
from backend.services import tradingview_service
from backend.services.tradingview_service import TradingViewUnauthorizedError, TradingViewValidationError

router = APIRouter(prefix="/api/tradingview", tags=["tradingview"])


@router.post("/webhook", response_model=TradingViewWebhookResponse)
async def tradingview_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_tradingview_secret: str | None = Header(default=None),
) -> TradingViewWebhookResponse:
    """
    Receives a TradingView alert JSON body (see docs/tradingview_webhook.md).
    A bad/unauthorized/malformed request always returns a normal JSON
    response with success=false — it never raises an unhandled exception
    that could take down the process, per the "a bad webhook must never
    crash the backend" requirement.

    Auth: the secret can be sent either as the `X-TradingView-Secret` header
    (recommended — TradingView alert webhooks support custom headers) or as
    a `"secret"` field inside the JSON body, since some TradingView plans
    only allow editing the message body.
    """
    try:
        raw_body = await request.json()
    except Exception:
        return TradingViewWebhookResponse(success=False, message="Invalid TradingView webhook payload: body is not valid JSON")

    provided_secret = x_tradingview_secret or (raw_body.get("secret") if isinstance(raw_body, dict) else None)
    try:
        tradingview_service.check_authorized(provided_secret)
    except TradingViewUnauthorizedError as exc:
        return TradingViewWebhookResponse(success=False, message=str(exc))

    if isinstance(raw_body, dict):
        raw_body.pop("secret", None)

    try:
        payload = TradingViewWebhookPayload.model_validate(raw_body)
    except ValidationError as exc:
        return TradingViewWebhookResponse(success=False, message=f"Invalid TradingView webhook payload: {exc.errors()[0]['msg']}")

    try:
        tradingview_service.validate_strategy_fields(payload)
    except TradingViewValidationError as exc:
        return TradingViewWebhookResponse(success=False, message=str(exc))

    row, _created = tradingview_service.store_signal(db, payload)

    return TradingViewWebhookResponse(
        success=True,
        message="TradingView signal received",
        signal_id=str(row.id),
        strategy=row.strategy,
        symbol=row.symbol,
    )


@router.get("/status", response_model=TradingViewStatusOut)
def tradingview_status(db: Session = Depends(get_db)) -> TradingViewStatusOut:
    count = db.query(TradingViewSignal).count()
    latest = db.query(TradingViewSignal).order_by(TradingViewSignal.received_at.desc()).first()
    return TradingViewStatusOut(
        enabled=settings.tradingview_enabled,
        configured=settings.tradingview_enabled and bool(settings.tradingview_webhook_secret),
        signal_count=count,
        latest_signal_at=latest.received_at if latest else None,
    )


@router.get("/signals", response_model=list[TradingViewSignalOut])
def list_signals(limit: int = 200, db: Session = Depends(get_db)) -> list[TradingViewSignal]:
    return (
        db.query(TradingViewSignal)
        .order_by(TradingViewSignal.received_at.desc())
        .limit(min(limit, 500))
        .all()
    )

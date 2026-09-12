from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.tradingview_signal import TradingViewSignal
from backend.schemas.tradingview import TradingViewWebhookPayload


class TradingViewValidationError(Exception):
    """A structurally valid JSON body that fails strategy-specific rules."""


class TradingViewUnauthorizedError(Exception):
    """Missing/incorrect webhook secret."""


def check_authorized(provided_secret: str | None) -> None:
    if not settings.tradingview_enabled:
        raise TradingViewUnauthorizedError("TradingView integration is not enabled")
    if not settings.tradingview_webhook_secret:
        # Safe-by-default: even if TRADINGVIEW_ENABLED=true, an empty secret
        # means "not configured" -> refuse rather than accept unauthenticated
        # webhooks.
        raise TradingViewUnauthorizedError("TradingView webhook secret is not configured")
    if provided_secret != settings.tradingview_webhook_secret:
        raise TradingViewUnauthorizedError("Invalid webhook secret")


def _trigger_for(payload: TradingViewWebhookPayload) -> str | None:
    if payload.strategy in ("PRD", "NRD"):
        return payload.divergence_timeframe
    if payload.strategy == "Value Buy":
        return payload.daily_trigger
    return None


def validate_strategy_fields(payload: TradingViewWebhookPayload) -> None:
    """
    Strategy-specific required-field checks beyond the base JSON shape
    (already enforced by the Pydantic model). Raises TradingViewValidationError
    with a message naming exactly what's missing.
    """
    if not payload.signal:
        raise TradingViewValidationError("Payload declares signal=false — TradingView should only alert on confirmed conditions")

    if payload.strategy in ("Strategy One", "GFS", "Advanced GFS"):
        if payload.daily_rsi is None or payload.weekly_rsi is None or payload.monthly_rsi is None:
            raise TradingViewValidationError(f"{payload.strategy} requires daily_rsi, weekly_rsi, and monthly_rsi")

    elif payload.strategy in ("PRD", "NRD"):
        if payload.divergence_type is None:
            raise TradingViewValidationError(f"{payload.strategy} requires divergence_type")
        if payload.divergence_type != payload.strategy:
            raise TradingViewValidationError(
                f"divergence_type '{payload.divergence_type}' does not match strategy '{payload.strategy}'"
            )
        if payload.divergence_timeframe is None:
            raise TradingViewValidationError(f"{payload.strategy} requires divergence_timeframe")
        if payload.divergence_timeframe.capitalize() not in ("Daily", "Weekly", "Monthly"):
            raise TradingViewValidationError(
                f"divergence_timeframe must be one of Daily/Weekly/Monthly, got '{payload.divergence_timeframe}'"
            )

    elif payload.strategy == "SECTOR_RSI":
        if payload.weekly_rsi is None and payload.monthly_rsi is None:
            raise TradingViewValidationError("SECTOR_RSI requires at least one of weekly_rsi or monthly_rsi")

    elif payload.strategy == "Value Buy":
        if payload.monthly_rsi is None:
            raise TradingViewValidationError("Value Buy requires monthly_rsi")
        if payload.weekly_candle is None:
            raise TradingViewValidationError("Value Buy requires weekly_candle")
        if payload.weekly_candle.upper() != "GREEN":
            raise TradingViewValidationError(
                f"Value Buy requires a confirmed GREEN weekly candle, got '{payload.weekly_candle}'"
            )
        if payload.daily_trigger is None:
            raise TradingViewValidationError("Value Buy requires daily_trigger (KEY_REVERSAL or TRENDLINE_BREAKOUT)")


def compute_dedupe_key(payload: TradingViewWebhookPayload) -> str:
    trigger = _trigger_for(payload) or ""
    raw = "|".join([
        payload.symbol.upper(),
        payload.strategy,
        payload.timeframe,
        payload.signal_date.isoformat(),
        trigger,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_latest_sector_rsi(db: Session, nse_index: str) -> TradingViewSignal | None:
    """
    Most recent SECTOR_RSI signal for this NSE sectoral index (e.g.
    "Nifty Healthcare"), if any has ever been delivered. Used only as a
    fallback data source by backend/sector_analysis/engine.py — never
    queried for, or capable of affecting, per-stock strategy evaluation.
    """
    return (
        db.query(TradingViewSignal)
        .filter(TradingViewSignal.strategy == "SECTOR_RSI", TradingViewSignal.symbol == nse_index.upper())
        .order_by(TradingViewSignal.signal_date.desc())
        .first()
    )


def store_signal(db: Session, payload: TradingViewWebhookPayload) -> tuple[TradingViewSignal, bool]:
    """
    Insert the signal, deduped on compute_dedupe_key(). Returns
    (row, created) — created=False means this exact alert was already
    recorded (a re-delivery), and the existing row is returned unchanged
    rather than inserting a duplicate or deleting anything.
    """
    dedupe_key = compute_dedupe_key(payload)
    existing = db.query(TradingViewSignal).filter(TradingViewSignal.dedupe_key == dedupe_key).one_or_none()
    if existing is not None:
        return existing, False

    row = TradingViewSignal(
        dedupe_key=dedupe_key,
        source=payload.source,
        symbol=payload.symbol.upper(),
        exchange=payload.exchange,
        strategy=payload.strategy,
        signal_timeframe=payload.timeframe,
        signal_date=payload.signal_date.replace(tzinfo=None),
        daily_rsi=payload.daily_rsi,
        weekly_rsi=payload.weekly_rsi,
        monthly_rsi=payload.monthly_rsi,
        divergence_type=payload.divergence_type,
        divergence_timeframe=payload.divergence_timeframe,
        trigger=_trigger_for(payload),
        raw_payload=payload.model_dump(mode="json"),
        status="RECEIVED",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, True

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class TradingViewSignal(Base):
    """
    One TradingView Pine Script alert delivery, received via the optional
    webhook (backend/api/tradingview.py). Wholly additive: no existing
    scanner table/model references this, and this table has no foreign key
    into scan_runs/scan_result_rows — a TradingView signal is a separate,
    user-verifiable data point shown alongside (never merged into) the
    existing market-data-driven strategy results.
    """

    __tablename__ = "tradingview_signals"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Deterministic dedupe key: symbol + strategy + timeframe + signal_date +
    # trigger. Unique so a re-delivered TradingView alert (TradingView retries
    # webhooks that don't return 2xx, and users can also fire the same alert
    # twice) never creates a duplicate row.
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)

    source: Mapped[str] = mapped_column(String(30), default="tradingview")
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    exchange: Mapped[str | None] = mapped_column(String(20), nullable=True)
    strategy: Mapped[str] = mapped_column(String(30), index=True)
    signal_timeframe: Mapped[str] = mapped_column(String(20))
    signal_date: Mapped[dt.datetime] = mapped_column(DateTime, index=True)

    daily_rsi: Mapped[float | None] = mapped_column(Float, nullable=True)
    weekly_rsi: Mapped[float | None] = mapped_column(Float, nullable=True)
    monthly_rsi: Mapped[float | None] = mapped_column(Float, nullable=True)

    divergence_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "PRD" | "NRD"
    divergence_timeframe: Mapped[str | None] = mapped_column(String(20), nullable=True)
    trigger: Mapped[str | None] = mapped_column(String(30), nullable=True)  # e.g. KEY_REVERSAL, TRENDLINE_BREAKOUT

    raw_payload: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)
    status: Mapped[str] = mapped_column(String(20), default="RECEIVED")  # RECEIVED | REJECTED

    __table_args__ = (
        Index("ix_tradingview_signals_symbol_strategy", "symbol", "strategy"),
    )

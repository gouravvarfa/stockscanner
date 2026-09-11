from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_type: Mapped[str] = mapped_column(String(20))  # manual|daily|weekly|monthly
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    execution_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    stocks_scanned: Mapped[int] = mapped_column(Integer, default=0)
    stocks_failed: Mapped[int] = mapped_column(Integer, default=0)
    qualifying_sectors: Mapped[int] = mapped_column(Integer, default=0)
    qualifying_stocks: Mapped[int] = mapped_column(Integer, default=0)

    universe_requested: Mapped[int] = mapped_column(Integer, default=0)
    universe_returned: Mapped[int] = mapped_column(Integer, default=0)
    universe_complete: Mapped[bool] = mapped_column(default=False)

    data_source: Mapped[str] = mapped_column(String(50), default="tapetide")
    errors: Mapped[list] = mapped_column(JSON, default=list)

    results: Mapped[list["ScanResultRow"]] = relationship(back_populates="scan_run")


class ScanResultRow(Base):
    __tablename__ = "scan_result_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    scan_run: Mapped[ScanRun] = relationship(back_populates="results")

    rank: Mapped[int] = mapped_column(Integer)
    symbol: Mapped[str] = mapped_column(String(30))
    sector: Mapped[str] = mapped_column(String(100))
    score: Mapped[float] = mapped_column(Float)
    classification: Mapped[str] = mapped_column(String(30))
    bias: Mapped[str] = mapped_column(String(20))  # BULLISH|NEUTRAL|HIGH RISK

    detail: Mapped[dict] = mapped_column(JSON)  # full score breakdown + indicator snapshot

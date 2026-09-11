from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.services import history_service

router = APIRouter(prefix="/api/history", tags=["history"])


class ScanRunOut(BaseModel):
    id: int
    scan_type: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    execution_seconds: float | None
    stocks_scanned: int
    stocks_failed: int
    qualifying_sectors: int
    qualifying_stocks: int
    universe_requested: int
    universe_returned: int
    universe_complete: bool

    class Config:
        from_attributes = True


class ScanResultRowOut(BaseModel):
    rank: int
    symbol: str
    sector: str
    score: float
    classification: str
    bias: str
    detail: dict

    class Config:
        from_attributes = True


@router.get("", response_model=list[ScanRunOut])
def list_runs(limit: int = 20, db: Session = Depends(get_db)) -> list[ScanRunOut]:
    return history_service.list_scan_runs(db, limit)


@router.get("/{scan_id}", response_model=ScanRunOut)
def get_run(scan_id: int, db: Session = Depends(get_db)) -> ScanRunOut:
    run = history_service.get_scan_run(db, scan_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Scan run not found")
    return run


@router.get("/{scan_id}/results", response_model=list[ScanResultRowOut])
def get_run_results(scan_id: int, db: Session = Depends(get_db)) -> list[ScanResultRowOut]:
    run = history_service.get_scan_run(db, scan_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Scan run not found")
    return run.results

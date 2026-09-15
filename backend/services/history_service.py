from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.scan import ScanResultRow, ScanRun
from backend.schemas.scan import ScanResultOut


def persist_scan(db: Session, scan_type: str, result: ScanResultOut) -> ScanRun:
    run = ScanRun(
        scan_type=scan_type,
        started_at=result.started_at,
        finished_at=result.finished_at,
        execution_seconds=result.execution_seconds,
        stocks_scanned=result.stocks_scanned,
        stocks_failed=result.stocks_failed,
        qualifying_stocks=len(result.top10),
        universe_requested=result.universe_requested,
        universe_returned=result.universe_returned,
        universe_complete=result.universe_complete,
        errors=result.errors,
    )
    db.add(run)
    db.flush()

    for row in result.top10:
        db.add(
            ScanResultRow(
                scan_run_id=run.id,
                rank=row.rank,
                symbol=row.symbol,
                score=row.score,
                classification=row.classification,
                bias=row.bias,
                detail=row.model_dump(mode="json"),
            )
        )

    db.commit()
    db.refresh(run)
    return run


def list_scan_runs(db: Session, limit: int = 20) -> list[ScanRun]:
    return db.query(ScanRun).order_by(ScanRun.started_at.desc()).limit(limit).all()


def get_scan_run(db: Session, scan_id: int) -> ScanRun | None:
    return db.get(ScanRun, scan_id)

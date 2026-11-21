"""Weekly Sectors API: which sector and which stocks are moving (see backend/strategies/sector_strength.py)."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.services import sector_strength_service as svc
from backend.services.provider_factory import get_angelone_provider
from backend.strategies.sector_strength_export import build_xlsx
from backend.strategies.sector_strength_pdf import build_pdf

router = APIRouter(prefix="/api/weekly-sectors", tags=["weekly-sectors"])


class RunRequest(BaseModel):
    as_of: str | None = None  # YYYY-MM-DD; empty = the latest close


@router.get("/sectors")
async def sectors() -> list[dict]:
    return [{"key": s["key"], "label": s["label"], "index": s["index"]} for s in svc.SECTORS]


@router.post("/run")
async def run(req: RunRequest) -> dict:
    as_of = None
    if req.as_of:
        try:
            as_of = dt.date.fromisoformat(req.as_of)
        except ValueError as exc:
            raise HTTPException(400, "as_of must be YYYY-MM-DD") from exc
        if as_of > dt.date.today():
            raise HTTPException(400, "as_of is in the future")
    return svc.start_job(get_angelone_provider(), as_of).to_dict()


@router.get("/run/{job_id}")
async def status(job_id: str) -> dict:
    job = svc.get_job(job_id)
    if job is None:
        raise HTTPException(404, "No such report run (the server may have restarted) - run it again.")
    return job.to_dict()


@router.post("/export")
async def export(report: dict = Body(...)) -> Response:
    """Excel from the report the page already shows (nothing is fetched again or stored)."""
    try:
        content = build_xlsx(report)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, f"Not a weekly sector report: {exc}") from exc
    name = f"weekly_sectors_{report.get('end_date') or report.get('as_of') or 'report'}.xlsx"
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.post("/pdf")
async def pdf(report: dict = Body(...)) -> Response:
    """The weekly report as a PDF, built from the report the page already shows."""
    try:
        content = build_pdf(report)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(400, f"Not a weekly sector report: {exc}") from exc
    name = f"weekly_sector_report_{report.get('end_date') or report.get('as_of') or 'report'}.pdf"
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})

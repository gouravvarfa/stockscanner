"""Range Analysis API: the % range move sheet for any NSE stock or index (see backend/strategies/range_move.py)."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import Response

from backend.services import range_analysis_service as svc
from backend.services.provider_factory import get_angelone_provider
from backend.strategies.range_move_export import build_xlsx

router = APIRouter(prefix="/api/range-analysis", tags=["range-analysis"])


def _date(raw: str | None, name: str) -> dt.date | None:
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw if len(raw) > 7 else raw + "-01")
    except ValueError as exc:
        raise HTTPException(400, f"{name} must be YYYY-MM or YYYY-MM-DD") from exc


@router.get("/search")
async def search(q: str = Query("", max_length=40)) -> list[dict]:
    return await svc.search(q)


@router.get("/stock/{symbol}")
async def stock(symbol: str, from_date: str | None = None, to_date: str | None = None) -> dict:
    start, end = _date(from_date, "from_date"), _date(to_date, "to_date")
    if start and end and start > end:
        raise HTTPException(400, "from_date is after to_date")
    try:
        return await svc.analyse(get_angelone_provider(), symbol, start, end)
    except svc.InstrumentNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:  # no months inside the chosen dates
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - one bad response must never crash the app
        raise HTTPException(502, f"Angel One error: {exc}") from exc


@router.post("/export")
async def export(table: dict = Body(...)) -> Response:
    """Builds the Excel from the sheet the page already shows (nothing is fetched or stored on the server)."""
    try:
        content = build_xlsx(table)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, f"Not a range-analysis table: {exc}") from exc
    name = f"{table.get('symbol', 'range')}_range_move_{table.get('filter_from', '')}_to_{table.get('filter_to', '')}.xlsx"
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})

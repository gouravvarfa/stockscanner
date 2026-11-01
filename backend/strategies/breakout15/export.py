"""The .xlsx export of one stored backtest, laid out like the user's manual sheet:
title row, then DATE | TIME | CALL/PUT | N minute candel | N minute candel points | PROFIT | LOSS | PERCENTAGE | POINTS | RISK:REWARD.
TIME is the entry time; candle columns describe the first candle; PERCENTAGE and POINTS describe the trade.

PERCENTAGE and POINTS follow the user's sheet: sizes without a sign; the PROFIT/LOSS columns carry the sign.
"""
from __future__ import annotations

import datetime as dt
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

TITLES = {"NIFTY": "NIFTY 50", "BANKNIFTY": "BANK NIFTY"}
WIDTHS = (12, 8, 11, 18, 24, 10, 10, 13, 10, 14)


def headers(bar_minutes: int) -> list[str]:
    return ["DATE", "TIME", "CALL/PUT", f"{bar_minutes} minute candel", f"{bar_minutes} minute candel points",
            "PROFIT", "LOSS", "PERCENTAGE", "POINTS", "RISK:REWARD"]

THIN = Side(style="thin")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def risk_reward(r: dict) -> str | None:
    """1:x where x = trade points / points risked (entry to stop). A loss is negative, e.g. a full stop is 1:-1.00."""
    entry, stop, pnl = r.get("entry_price"), r.get("stop_loss"), r.get("pnl_points")
    if entry is None or stop is None or pnl is None or entry == stop:
        return None
    return f"1:{pnl / abs(entry - stop):.2f}"


def _row(r: dict) -> list:
    pnl = r.get("pnl_points")
    side = {"CALL": "CALL", "PUT": "PUT", "BOTH": "UNRESOLVED"}.get(r.get("side") or "", "")
    if r["exit_reason"] == "NO_ENTRY":
        side = "NO ENTRY"
    elif r["exit_reason"].startswith("DATA") and pnl is None:
        side = "DATA INCOMPLETE"
    size = None if r.get("first_range_pct") is None else r["first_range_pct"] / 100.0
    eod = None if r.get("pnl_pct") is None else abs(r["pnl_pct"]) / 100.0
    high, low = r.get("first_high"), r.get("first_low")
    entry = r.get("breakout_time")
    return [
        dt.date.fromisoformat(r["date"]), dt.time.fromisoformat(entry[11:16]) if entry else None, side, size,
        None if high is None or low is None else round(high - low, 2),
        "PROFIT" if pnl is not None and pnl > 0 else None,
        "LOSS" if pnl is not None and pnl < 0 else None,
        eod,
        None if pnl is None else round(abs(pnl), 2),
        risk_reward(r),
    ]


def build_xlsx(result: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.merge_cells("A1:J2")
    ws["A1"] = TITLES.get(result["symbol"], result["symbol"])
    ws["A1"].font = Font(bold=True, size=20)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    for col in "ABCDEFGHIJ":
        for row in (1, 2):
            ws[f"{col}{row}"].border = BOX
    for c, text in zip(ws[3], headers(result.get("bar_minutes", 15))):
        c.value = text
        c.font = Font(bold=True)
        c.border = BOX
    for n, r in enumerate(result["rows"], start=4):
        cells = ws[n]
        for c, v in zip(cells, _row(r)):
            c.value = v
        cells[0].number_format = "d-mmm-yy"
        cells[1].number_format = "hh:mm"
        cells[3].number_format = "0.00%"
        cells[4].number_format = "0.00"
        cells[7].number_format = "0.00%"
        cells[8].number_format = "0.00"
        for c in cells:
            c.border = BOX
    for letter, width in zip("ABCDEFGHIJ", WIDTHS):
        ws.column_dimensions[letter].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

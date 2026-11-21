"""Excel for the % Range Move sheet, in the layout of the user's "top range performance" workbook: a navy header row
(YEAR/MONTH, JAN..DEC, AVG MONTHLY RANGE MOVE), 30%+ green, 20-30% orange, January-March 30%+ boxed, the
"JAN-MAR BEST" note on the right, and month-wise statistics underneath. A second sheet lists every month's
open/high/low/close, direction and the formula used, so any cell can be checked by hand."""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from backend.strategies.range_move import MONTHS

NAVY = "1F3A73"
GREEN_FILL, GREEN_FONT = "D8F0DA", "0B7A36"
ORANGE_FILL, ORANGE_FONT = "FBE7C6", "A15C00"
BEST_FILL = "C9EBCB"
THIN = Side(style="thin", color="D5DAE3")
BOX = Side(style="medium", color=NAVY)
CENTER = Alignment(horizontal="center", vertical="center")


def _cell_style(c, level: str, boxed: bool, in_progress: bool) -> None:
    c.alignment = CENTER
    c.number_format = "0.00%"
    c.border = Border(left=BOX if boxed else THIN, right=BOX if boxed else THIN,
                      top=BOX if boxed else THIN, bottom=BOX if boxed else THIN)
    if in_progress:
        c.font = Font(italic=True, color="8A94A6")
        return
    if level == "green":
        c.fill = PatternFill("solid", fgColor=GREEN_FILL)
        c.font = Font(bold=True, color=GREEN_FONT)
    elif level == "orange":
        c.fill = PatternFill("solid", fgColor=ORANGE_FILL)
        c.font = Font(bold=True, color=ORANGE_FONT)
    else:
        c.font = Font(color="3D4656")


def build_xlsx(table: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "RANGE MOVE"
    symbol = table["symbol"]
    title = f"{symbol} - % RANGE MOVE" + (f"  ({table['name']})" if table.get("name") else "")
    ws.merge_cells("A1:N1")
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=15, color=NAVY)
    ws["A1"].alignment = CENTER
    ws.row_dimensions[1].height = 26

    best = set(table.get("jan_mar", {}).get("best", []))
    headers = ["YEAR/MONTH", *MONTHS, "AVG MONTHLY RANGE MOVE"]
    for i, h in enumerate(headers, start=1):
        c = ws.cell(2, i, h)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
        if h in best:
            c.fill = PatternFill("solid", fgColor=BEST_FILL)
            c.font = Font(bold=True, color=GREEN_FONT)
        else:
            c.fill = PatternFill("solid", fgColor=NAVY)
            c.font = Font(bold=True, color="FFFFFF")
    ws.row_dimensions[2].height = 30

    r = 3
    for row in table["rows"]:
        yc = ws.cell(r, 1, row["year"])
        yc.font = Font(bold=True, color="1B2638")
        yc.alignment = CENTER
        yc.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
        for m, cell in enumerate(row["months"], start=2):
            c = ws.cell(r, m, None if cell is None else cell["pct"] / 100)
            if cell is None:
                c.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
                continue
            _cell_style(c, cell["level"], cell["boxed"], cell["in_progress"])
        a = ws.cell(r, 14, None if row["avg"] is None else row["avg"] / 100)
        a.number_format = "0.00%"
        a.font = Font(bold=True, color="1B2638")
        a.alignment = CENTER
        a.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
        r += 1

    # month-wise statistics underneath (complete months only)
    r += 1
    stats = table["month_stats"]
    for label, key, pct in (("AVERAGE", "avg", True), ("MEDIAN", "median", True), ("MONTHS >= 20%", "ge20", False),
                            ("MONTHS >= 30%", "ge30", False)):
        lc = ws.cell(r, 1, label)
        lc.font = Font(bold=True, color="FFFFFF")
        lc.fill = PatternFill("solid", fgColor="44546F")
        lc.alignment = CENTER
        for m, s in enumerate(stats, start=2):
            v = s[key]
            c = ws.cell(r, m, (v / 100 if v is not None else None) if pct else f"{v}/{s['years']}")
            c.alignment = CENTER
            c.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
            c.font = Font(bold=True, color="1B2638")
            if pct:
                c.number_format = "0.00%"
        r += 1

    # notes on the right, like the sheet
    jm = table.get("jan_mar", {})
    counts = jm.get("ge30", {})
    ov = table["overall"]
    notes = [
        ("JAN-MAR BEST: " + (" / ".join(jm.get("best") or []) or "-"), True),
        ("30%+ months: " + " · ".join(f"{k.title()} {v}" for k, v in counts.items()), False),
        ("SPOT" if table.get("kind") != "INDEX" else "INDEX", True),
        (f"Data: {table['data_from']} to {table['data_to']}", False),
        (f"Shown: {table['filter_from']} to {table['filter_to']}", False),
        (f"Months: {ov['months']} · 20%+: {ov['ge20']} · 30%+: {ov['ge30']}", False),
        (f"Most active (median): {ov['most_active']} · Quietest: {ov['quietest']}", False),
        ("Green 30%+, orange 20-30%; boxed = Jan-Mar 30%+", False),
        ("Up month: (H-L)/L, down month: (H-L)/H", False),
        ("The month in progress (grey) is not in any average", False),
    ]
    for i, (text, bold) in enumerate(notes, start=2):
        c = ws.cell(i, 16, text)
        c.font = Font(bold=bold, color=NAVY if bold else "4A566B")

    ws.column_dimensions["A"].width = 14
    for col in range(2, 14):
        ws.column_dimensions[get_column_letter(col)].width = 10
    ws.column_dimensions["N"].width = 16
    ws.column_dimensions["O"].width = 3
    ws.column_dimensions["P"].width = 46
    ws.freeze_panes = "B3"

    # every month, for checking
    md = wb.create_sheet("MONTHLY DATA")
    cols = ["Month", "Open", "High", "Low", "Close", "Prev month close", "Direction", "% Range move", "Formula",
            "First day", "Last day", "Status"]
    for i, h in enumerate(cols, start=1):
        c = md.cell(1, i, h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=NAVY)
        c.alignment = CENTER
    for j, m in enumerate(table.get("monthly", []), start=2):
        vals = [m["label"], m["open"], m["high"], m["low"], m["close"], m["prev_close"], m["direction"].upper(),
                m["pct"] / 100, "(H-L)/L" if m["direction"] == "up" else "(H-L)/H", m["first_day"], m["last_day"],
                "in progress" if m["in_progress"] else ""]
        for i, v in enumerate(vals, start=1):
            c = md.cell(j, i, v)
            if i == 8:
                c.number_format = "0.00%"
    for i, w in enumerate([12, 11, 11, 11, 11, 16, 11, 14, 10, 12, 12, 12], start=1):
        md.column_dimensions[get_column_letter(i)].width = w
    md.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

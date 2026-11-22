"""Excel for the Weekly Sectors report: a summary scorecard, top movers, laggards, study buckets and one sheet per
sector, styled like the weekly report the user shares (navy headers, green / red / amber signals)."""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

NAVY = "15315A"
THIN = Side(style="thin", color="D5DAE3")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")
SIGNAL_STYLE = {
    "Leader": ("E3F3E6", "17703A"), "Turning up": ("DCE8F7", "1F4E8C"),
    "Fading": ("FBF0D3", "8A5A00"), "Laggard": ("FBE3E1", "A42A22"),
}
VERDICT_STYLE = {"STRONG": ("E3F3E6", "17703A"), "MIXED": ("FBF0D3", "8A5A00"), "WEAK": ("FBE3E1", "A42A22"), "N/A": ("EEF1F6", "5B677D")}
DISCLAIMER = "For education only. Not investment advice or a recommendation to buy, sell or hold any security."


def _header(ws, row: int, cols: list[str]) -> None:
    for i, h in enumerate(cols, start=1):
        c = ws.cell(row, i, h)
        c.fill = PatternFill("solid", fgColor=NAVY)
        c.font = Font(bold=True, color="FFFFFF")
        c.alignment = CENTER
        c.border = BORDER


def _pct(c, v, signed_colour: bool = True) -> None:
    c.value = None if v is None else v / 100
    c.number_format = "+0.00%;-0.00%;0.00%"
    c.alignment = CENTER
    c.border = BORDER
    if signed_colour and v is not None:
        c.font = Font(color="17703A" if v > 0 else "A42A22" if v < 0 else "3D4656")


def _pp(c, v) -> None:
    c.value = v
    c.number_format = "+0.00;-0.00;0.00"
    c.alignment = CENTER
    c.border = BORDER
    if v is not None:
        good = v > 0
        c.fill = PatternFill("solid", fgColor="E3F3E6" if good else "FBE3E1")
        c.font = Font(bold=True, color="17703A" if good else "A42A22")


def _chip(c, text: str, styles: dict) -> None:
    fill, font = styles.get(text, ("FFFFFF", "1B2638"))
    c.value = text
    c.fill = PatternFill("solid", fgColor=fill)
    c.font = Font(bold=True, color=font)
    c.alignment = CENTER
    c.border = BORDER


def _widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build_xlsx(report: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "SUMMARY"
    ws["A1"] = "Weekly Sector & Stock Relative Strength"
    ws["A1"].font = Font(bold=True, size=16, color=NAVY)
    b, s = report.get("benchmark", {}), report.get("summary", {})
    lines = [
        f"As of {report.get('as_of')} (last close used: {report.get('end_date')}) · constituents: {report.get('constituents_source', 'NSE')}",
        f"Nifty 50: 1W {b.get('r1w')}% · 1M {b.get('r1m')}%",
        f"Top sector (average of 1W and 1M rank): {s.get('top_sector')} ({s.get('top_sector_r1w')}% 1W, {s.get('top_sector_r1m')}% 1M)",
        "Strong sectors (daily, weekly and monthly RSI all above 60): " + (", ".join(s.get("strong_sectors") or []) or "none"),
        f"Leaders (beat their sector on 1W and 1M): {s.get('leaders')} of {s.get('rows')} · Laggards: {s.get('laggards')} of {s.get('rows')}",
    ]
    for i, t in enumerate(lines, start=2):
        ws.cell(i, 1, t).font = Font(color="3D4656")
    cols = ["Sector", "Index", "1W %", "# 1W", "1M %", "# 1M", "RSI D", "RSI W", "RSI M", "Verdict", "Beat 1W", "Beat 1M",
            "Leaders", "Turning up", "Fading", "Laggards",
            "# 1W last wk", "Rank move", "Quadrant", "Quadrant last wk", "Verdict last wk",
            "> 50 DMA %", "> 200 DMA %", "RSI > 60 %", "52w highs", "Breadth"]
    _header(ws, 8, cols)
    for r, sec in enumerate(report.get("sectors", []), start=9):
        n = len(sec.get("stocks", []))
        vals = [sec["label"], "equal-weight of its stocks" if sec.get("equal_weight") else sec.get("index_label")]
        for i, v in enumerate(vals, start=1):
            c = ws.cell(r, i, v)
            c.border = BORDER
            c.font = Font(bold=i == 1)
        _pct(ws.cell(r, 3), sec.get("r1w"))
        ws.cell(r, 4, sec.get("rank_1w")).alignment = CENTER
        _pct(ws.cell(r, 5), sec.get("r1m"))
        ws.cell(r, 6, sec.get("rank_1m")).alignment = CENTER
        for j, k in enumerate(("d", "w", "m"), start=7):
            v = (sec.get("rsi") or {}).get(k)
            c = ws.cell(r, j, v)
            c.alignment = CENTER
            c.border = BORDER
            if v is not None:
                c.font = Font(bold=True, color="17703A" if v > 60 else "A42A22" if v < 40 else "8A5A00")
        _chip(ws.cell(r, 10), sec.get("verdict", "N/A"), VERDICT_STYLE)
        ws.cell(r, 11, f"{sec.get('beat_1w')}/{n}").alignment = CENTER
        ws.cell(r, 12, f"{sec.get('beat_1m')}/{n}").alignment = CENTER
        for j, k in enumerate(("Leader", "Turning up", "Fading", "Laggard"), start=13):
            ws.cell(r, j, sec.get("counts", {}).get(k)).alignment = CENTER
        prev = sec.get("prev") or {}
        br = sec.get("breadth") or {}
        move = sec.get("rank_change_1w")
        extra = [prev.get("rank_1w"), None if move is None else (f"+{move}" if move > 0 else str(move)), sec.get("quadrant"),
                 prev.get("quadrant"), prev.get("verdict"), br.get("above_50dma"), br.get("above_200dma"), br.get("rsi_above_60"),
                 br.get("new_52w_highs"), br.get("label")]
        for j, v in enumerate(extra, start=17):
            c = ws.cell(r, j, v)
            c.alignment = CENTER
            c.border = BORDER
        if move:
            ws.cell(r, 18).font = Font(bold=True, color="17703A" if move > 0 else "A42A22")
        if br.get("label"):
            _chip(ws.cell(r, 26), br["label"], {"Broad": ("E3F3E6", "17703A"), "Moderate": ("FBF0D3", "8A5A00"), "Narrow": ("FBE3E1", "A42A22")})
    nr = 9 + len(report.get("sectors", [])) + 1
    ws.cell(nr, 1, "Verdict: STRONG = daily, weekly and monthly RSI(14) all above 60; WEAK = all three below 40; otherwise MIXED.").font = Font(italic=True, color="5B677D")
    ws.cell(nr + 1, 1, "1W / 1M = last close vs the close 7 days / 1 calendar month earlier. vs = stock return minus its sector's, in percentage points.").font = Font(italic=True, color="5B677D")
    ws.cell(nr + 2, 1, DISCLAIMER).font = Font(italic=True, color="A42A22")
    ch = report.get("changes") or {}
    lines2 = [
        f"What changed since {ch.get('prev_date')}:",
        "  New STRONG: " + (", ".join(ch.get("new_strong") or []) or "none") + " | No longer STRONG: " + (", ".join(ch.get("dropped_strong") or []) or "none"),
        "  Moved up (1W rank): " + (", ".join(f"{x['label']} #{x['from']} to #{x['to']}" for x in ch.get("risers") or []) or "none")
        + " | Moved down: " + (", ".join(f"{x['label']} #{x['from']} to #{x['to']}" for x in ch.get("fallers") or []) or "none"),
        "  Quadrant changes: " + (", ".join(f"{x['label']} {x['from']} to {x['to']}" for x in ch.get("quadrant_moves") or []) or "none"),
        "Quadrant = 1W and 1M return against the Nifty 50: Leading ahead on both, Improving on the week only, Weakening on the month only, Lagging on neither.",
        "Breadth = share of the sector's stocks above the 50-day average: Broad 70%+, Moderate 40-70%, Narrow below 40%.",
    ]
    for i, t in enumerate(lines2, start=nr + 4):
        ws.cell(i, 1, t).font = Font(bold=i == nr + 4, color="3D4656" if i != nr + 4 else NAVY)
    _widths(ws, [20, 26, 10, 7, 10, 7, 8, 8, 8, 11, 9, 9, 9, 11, 8, 9, 11, 10, 12, 15, 14, 11, 12, 11, 10, 11])
    ws.freeze_panes = "B9"

    # the rotation path: each sector's 1W / 1M return and its return against the Nifty 50, week by week
    ro = wb.create_sheet("ROTATION")
    ro["A1"] = "Sector rotation - the last 5 weeks (return against the Nifty 50, in percentage points)"
    ro["A1"].font = Font(bold=True, size=13, color=NAVY)
    _header(ro, 3, ["Sector", "Week ending", "1W %", "1M %", "vs Nifty 1W", "vs Nifty 1M", "Quadrant"])
    rr = 4
    for sec in report.get("sectors", []):
        for t in sec.get("trail") or []:
            ro.cell(rr, 1, sec["label"]).font = Font(bold=True)
            ro.cell(rr, 2, t.get("date")).alignment = CENTER
            _pct(ro.cell(rr, 3), t.get("r1w"))
            _pct(ro.cell(rr, 4), t.get("r1m"))
            _pp(ro.cell(rr, 5), t.get("rel_1w"))
            _pp(ro.cell(rr, 6), t.get("rel_1m"))
            ro.cell(rr, 7, t.get("quadrant")).alignment = CENTER
            rr += 1
    _widths(ro, [20, 13, 10, 10, 12, 12, 12])
    ro.freeze_panes = "B4"

    def stock_sheet(title: str, rows: list[dict], with_sector: bool) -> None:
        sh = wb.create_sheet(title[:31])
        cols = ["Stock", "Company"] + (["Sector"] if with_sector else []) + ["1W %", "1M %", "vs 1W", "vs 1M", "Signal", "Group"]
        _header(sh, 1, cols)
        for r, x in enumerate(rows, start=2):
            vals = [x["symbol"], x.get("name")] + ([x.get("sector")] if with_sector else [])
            for i, v in enumerate(vals, start=1):
                c = sh.cell(r, i, v)
                c.border = BORDER
                c.font = Font(bold=i == 1)
            o = len(vals)
            _pct(sh.cell(r, o + 1), x["r1w"])
            _pct(sh.cell(r, o + 2), x["r1m"])
            _pp(sh.cell(r, o + 3), x["vs1w"])
            _pp(sh.cell(r, o + 4), x["vs1m"])
            _chip(sh.cell(r, o + 5), x["signal"], SIGNAL_STYLE)
            g = sh.cell(r, o + 6, x.get("group"))
            g.border = BORDER
            g.alignment = CENTER
        _widths(sh, [14, 34] + ([18] if with_sector else []) + [10, 10, 9, 9, 12, 13])
        sh.freeze_panes = "B2"

    stock_sheet("TOP MOVERS", report.get("top_movers", []), True)
    stock_sheet("LAGGARDS", report.get("laggards", []), True)

    bk = wb.create_sheet("STUDY BUCKETS")
    titles = {"strength_leaders": "Strength leaders - leaders in strong sectors",
              "watch": "Watch - near-leaders and pullbacks in strong sectors",
              "stock_specific": "Stock-specific - leaders outside the strong sectors",
              "relative_weakness": "Relative weakness - laggards and bounce-only in strong sectors"}
    r = 1
    for key, title in titles.items():
        bk.cell(r, 1, title).font = Font(bold=True, color=NAVY, size=12)
        r += 1
        for sec, syms in (report.get("buckets", {}).get(key) or {}).items():
            bk.cell(r, 1, sec).font = Font(bold=True)
            bk.cell(r, 2, ", ".join(syms))
            r += 1
        r += 1
    bk.cell(r, 1, DISCLAIMER).font = Font(italic=True, color="A42A22")
    _widths(bk, [22, 120])

    for sec in report.get("sectors", []):
        stock_sheet(sec["label"].upper(), sec.get("stocks", []), False)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

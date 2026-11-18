"""The .xlsx export of one stored backtest, laid out like the user's manual sheet:
title row, then DATE | TIME | CALL/PUT | N minute candel | N minute candel points | PROFIT | LOSS | PERCENTAGE | POINTS | RISK:REWARD.
TIME is the entry time; candle columns describe the first candle; PERCENTAGE and POINTS describe the trade.

PERCENTAGE and POINTS follow the user's sheet: sizes without a sign; the PROFIT/LOSS columns carry the sign.

Beside the table (one empty column gap, like the Top-Bottom export) is a summary: trades, CALL/PUT, wins/losses,
win rate, net points, lot size, net P&L in rupees, profit factor and max drawdown. Rupees = index points x the
CURRENT lot size of the index future (lot sizes changed over the years, so older trades are an approximation).
"""
from __future__ import annotations

import datetime as dt
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

TITLES = {"NIFTY": "NIFTY 50", "BANKNIFTY": "BANK NIFTY"}
# Fallback when the live scrip master is not reachable (NSE lot sizes, Nov 2026).
DEFAULT_LOT_SIZE = {"NIFTY": 65, "BANKNIFTY": 30}
LABEL_FILL = PatternFill("solid", fgColor="F2F2F2")
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


def summary_rows(result: dict, lot_size: int | None) -> list[tuple[str, object]]:
    """The side summary. Only trades with a P&L count (no-entry / incomplete days are listed separately)."""
    rows = result["rows"]
    traded = [r for r in rows if r.get("pnl_points") is not None]
    pts = [r["pnl_points"] for r in traded]
    wins = [p for p in pts if p > 0]
    losses = [p for p in pts if p < 0]
    lot = lot_size or DEFAULT_LOT_SIZE.get(result["symbol"])
    equity = peak = max_dd = 0.0
    for p in pts:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    gross_win, gross_loss = sum(wins), -sum(losses)
    rupees = (lambda x: round(x * lot, 2)) if lot else (lambda x: None)
    return [
        ("Total Trades", len(traded)),
        ("CALL Trades", sum(r.get("side") == "CALL" for r in traded)),
        ("PUT Trades", sum(r.get("side") == "PUT" for r in traded)),
        ("Winning Trades", len(wins)),
        ("Losing Trades", len(losses)),
        ("No Entry Days", sum(r.get("exit_reason") == "NO_ENTRY" for r in rows)),
        ("Win Rate %", round(100 * len(wins) / len(traded), 2) if traded else None),
        ("Net P&L (Points)", round(sum(pts), 2)),
        ("Lot Size", lot),
        ("Net P&L (Rs.)", rupees(sum(pts))),
        ("Gross Profit (Rs.)", rupees(gross_win)),
        ("Gross Loss (Rs.)", rupees(-gross_loss)),
        ("Profit Factor", round(gross_win / gross_loss, 2) if gross_loss else None),
        ("Average Win (Points)", round(gross_win / len(wins), 2) if wins else None),
        ("Average Loss (Points)", round(-gross_loss / len(losses), 2) if losses else None),
        ("Best Trade (Points)", round(max(pts), 2) if pts else None),
        ("Worst Trade (Points)", round(min(pts), 2) if pts else None),
        ("Max Drawdown (Points)", round(max_dd, 2)),
        ("Max Drawdown (Rs.)", rupees(max_dd)),
    ]


def build_xlsx(result: dict, lot_size: int | None = None) -> bytes:
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
    # Summary beside the table: column K left empty as a gap, labels in L, values in M.
    ws["L3"] = "SUMMARY"
    ws["L3"].font = Font(bold=True)
    for i, (label, value) in enumerate(summary_rows(result, lot_size), start=4):
        lc, vc = ws.cell(i, 12, label), ws.cell(i, 13, value)
        lc.font = Font(bold=True)
        lc.fill = LABEL_FILL
        lc.border = vc.border = BOX
        if isinstance(value, float):
            vc.number_format = "#,##0.00"
    ws.column_dimensions["K"].width = 3
    ws.column_dimensions["L"].width = 24
    ws.column_dimensions["M"].width = 14
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

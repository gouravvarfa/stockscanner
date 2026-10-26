"""Excel export for a finished System One backtest. Writes exactly the
stored result (same rows, same column order as the UI table); never
recomputes anything."""
from __future__ import annotations

import io

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from backend.services.system_one_backtest_service import PNL_NOTE, StoredSystemOneBacktest

HEADER_FILL = PatternFill("solid", fgColor="FFD966")
HEADER_FONT = Font(bold=True)
GREEN_FILL = PatternFill("solid", fgColor="C6EFCE")
GREEN_FONT = Font(color="006100")
RED_FILL = PatternFill("solid", fgColor="FFC7CE")
RED_FONT = Font(color="9C0006")
THIN_BORDER = Border(*(Side(style="thin", color="D9D9D9") for _ in range(4)))

DATE_FORMAT = "dd-mmm-yyyy"
MONEY_FORMAT = "#,##0.00"
PNL_FORMAT = "#,##0.00;-#,##0.00"

# Same order as the table in the UI (frontend SystemOneBacktest.tsx).
TRADE_HEADERS = [
    "Entry Date", "Entry Price", "Stop Loss", "Risk Per Share", "Risk Per Trade",
    "Quantity", "Exit Price", "Exit Date", "P&L Amount", "Status",
]


def _autosize(ws, min_width: int = 12, max_width: int = 60) -> None:
    for col_cells in ws.columns:
        length = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
        ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(max(length + 2, min_width), max_width)


def build_excel(stored: StoredSystemOneBacktest) -> bytes:
    wb = openpyxl.Workbook()

    # ---- Sheet 1: Trades — one row per trade, header on row 1 ---------------
    ws = wb.active
    ws.title = "Trades"
    ws.append(TRADE_HEADERS)
    for c in range(1, len(TRADE_HEADERS) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font, cell.border = HEADER_FILL, HEADER_FONT, THIN_BORDER
        cell.alignment = Alignment(horizontal="center")

    for t in stored.result.trades:
        # Open trades leave the exit cells empty — never 0.
        ws.append([
            t.entry_date.date(), t.entry_price, t.stop_loss, t.risk_per_share, t.risk_per_trade,
            t.quantity, t.exit_price, t.exit_date.date() if t.exit_date is not None else None,
            t.pnl_amount, t.status,
        ])
        row = ws.max_row
        for col, fmt in ((1, DATE_FORMAT), (2, MONEY_FORMAT), (3, MONEY_FORMAT), (4, MONEY_FORMAT),
                         (5, MONEY_FORMAT), (6, "0"), (7, MONEY_FORMAT), (8, DATE_FORMAT), (9, PNL_FORMAT)):
            ws.cell(row=row, column=col).number_format = fmt
        for col in range(1, len(TRADE_HEADERS) + 1):
            ws.cell(row=row, column=col).border = THIN_BORDER
        pnl_cell = ws.cell(row=row, column=9)
        if t.pnl_amount is not None and t.pnl_amount > 0:
            pnl_cell.fill, pnl_cell.font = GREEN_FILL, GREEN_FONT
        elif t.pnl_amount is not None and t.pnl_amount < 0:
            pnl_cell.fill, pnl_cell.font = RED_FILL, RED_FONT
    ws.freeze_panes = "A2"
    _autosize(ws)

    # ---- Sheet 2: Summary, settings and skipped signals ---------------------
    s = stored.result.summary()
    summary = wb.create_sheet("Summary")
    summary.append(["Field", "Value"])
    rows = [
        ("Strategy", "System One"),
        ("Symbol", stored.symbol),
        ("Trading Symbol", stored.trading_symbol),
        ("Timeframe", "Weekly"),
        ("From Date", stored.from_date.date()),
        ("To Date", stored.to_date.date()),
        ("Data Available From", stored.data_available_from.date()),
        ("Data Available To", stored.data_available_to.date()),
        ("Reference Capital", stored.config.reference_capital),
        ("Risk Per Trade %", stored.config.risk_per_trade_pct),
        ("Risk Per Trade", stored.config.risk_per_trade),
        ("Total Trades", s.total_trades),
        ("Closed Trades", s.closed_trades),
        ("Open Trades", s.open_trades),
        ("Winning Trades", s.winning_trades),
        ("Losing Trades", s.losing_trades),
        ("Net Realised P&L (closed trades only)", s.net_realized_pnl),
        ("Note", PNL_NOTE),
    ]
    for label, value in rows:
        summary.append([label, value])
        cell = summary.cell(row=summary.max_row, column=2)
        if hasattr(value, "year"):
            cell.number_format = DATE_FORMAT
        elif isinstance(value, float):
            cell.number_format = PNL_FORMAT
    for w in stored.result.warnings:
        summary.append(["Warning", w])
    if stored.result.skipped:
        summary.append([])
        summary.append(["Skipped Signal Date", "Reason"])
        for sk in stored.result.skipped:
            summary.append([sk.signal_date.date(), sk.reason])
            summary.cell(row=summary.max_row, column=1).number_format = DATE_FORMAT
    _autosize(summary, max_width=90)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

"""Multi-sheet Excel export for a finished Top-Bottom backtest — spec
section 20. Exports exactly the backtest that was run; never regenerates
or recomputes anything."""
from __future__ import annotations

import io

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from backend.strategies.top_bottom.models import BacktestResult

TITLE_FONT = Font(bold=True, size=16)
HEADER_FILL = PatternFill("solid", fgColor="FFD966")
HEADER_FONT = Font(bold=True)
GREEN_FILL = PatternFill("solid", fgColor="C6EFCE")
GREEN_FONT = Font(color="006100")
RED_FILL = PatternFill("solid", fgColor="FFC7CE")
RED_FONT = Font(color="9C0006")
THIN_BORDER = Border(*(Side(style="thin", color="D9D9D9") for _ in range(4)))
LABEL_FILL = PatternFill("solid", fgColor="F2F2F2")


def _autosize(ws, min_width: int = 10, max_width: int = 40) -> None:
    for col_cells in ws.columns:
        length = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
        ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(max(length + 2, min_width), max_width)


def build_excel(result: BacktestResult) -> bytes:
    wb = openpyxl.Workbook()

    # ---- Sheet 1: Trade Results ----------------------------------------
    # A clean, at-a-glance layout: title, a Totals block (Total Trades and
    # every other headline stat, visible without switching sheets), then
    # the trade-by-trade table with BUY/SELL and P&L color-coded exactly
    # like a typical trading journal — green for profit/BUY, red for
    # loss/SELL.
    trades_ws = wb.active
    trades_ws.title = "Trade Results"
    s = result.statistics

    title = f"{result.trading_symbol} — TOP BOTTOM"
    trades_ws.merge_cells("A1:F1")
    trades_ws["A1"] = title
    trades_ws["A1"].font = TITLE_FONT

    lot_size = result.trades[0].lot_size if result.trades else 0
    net_pnl_amount = sum(t.pnl_amount or 0 for t in result.trades) if lot_size else None
    totals = [
        ("Total Trades", s.total_trades), ("Buy Trades", s.buy_trades), ("Sell Trades", s.sell_trades),
        ("Winning Trades", s.winning_trades), ("Losing Trades", s.losing_trades), ("Win Rate %", round(s.win_rate, 2)),
        ("Net P&L %", round(s.net_pnl_pct, 2)), ("Net P&L (Points)", round(sum(t.pnl_points or 0 for t in result.trades), 2)),
        ("Lot Size", lot_size or "N/A"),
        ("Net P&L (Rs.)", round(net_pnl_amount, 2) if net_pnl_amount is not None else "N/A"),
        ("Profit Factor", round(s.profit_factor, 2) if s.profit_factor is not None else "N/A"),
        ("Max Drawdown %", round(s.max_drawdown_pct, 2)), ("Average Holding (days)", round(s.average_holding_days, 2)),
    ]
    header_row = 2
    for i, (label, value) in enumerate(totals):
        col = 8 + (i // 6) * 2  # two stacked columns of up to 6 rows each, starting at column H
        row = header_row + (i % 6)
        label_cell = trades_ws.cell(row=row, column=col, value=label)
        value_cell = trades_ws.cell(row=row, column=col + 1, value=value)
        label_cell.font = Font(bold=True)
        label_cell.fill = LABEL_FILL
        value_cell.alignment = Alignment(horizontal="right")

    header = ["Date", "Buy/Sell", "Entry", "Exit", "Point", "Profit / Loss"]
    for c, text in enumerate(header, start=1):
        cell = trades_ws.cell(row=header_row, column=c, value=text)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = THIN_BORDER

    row = header_row + 1
    for t in result.trades:
        date_cell = trades_ws.cell(row=row, column=1, value=t.entry_date.date())
        dir_cell = trades_ws.cell(row=row, column=2, value="buy" if t.direction == "BUY" else "sell")
        entry_cell = trades_ws.cell(row=row, column=3, value=t.entry_price)
        exit_cell = trades_ws.cell(row=row, column=4, value=t.exit_price)
        point_cell = trades_ws.cell(row=row, column=5, value=round(t.pnl_points, 2) if t.pnl_points is not None else None)
        # Real rupee P&L = points x the contract's ACTUAL exchange lot size
        # (from Angel One's own scrip master, never a guessed/hardcoded
        # multiplier) — shown as "N/A" rather than a fabricated 0 or wrong
        # figure on the rare row where the lot size wasn't resolved.
        pnl_value = round(t.pnl_amount, 2) if t.pnl_amount is not None else "N/A"
        pnl_cell = trades_ws.cell(row=row, column=6, value=pnl_value)

        is_win = (t.pnl_points or 0) > 0
        is_loss = (t.pnl_points or 0) < 0
        dir_cell.font = GREEN_FONT if t.direction == "BUY" else RED_FONT
        for cell in (point_cell, pnl_cell):
            if is_win:
                cell.fill = GREEN_FILL
                cell.font = GREEN_FONT
            elif is_loss:
                cell.fill = RED_FILL
                cell.font = RED_FONT
        for cell in (date_cell, dir_cell, entry_cell, exit_cell, point_cell, pnl_cell):
            cell.border = THIN_BORDER
        row += 1

    _autosize(trades_ws)
    for col_letter in ("H", "J", "L"):
        trades_ws.column_dimensions[col_letter].width = 20

    # ---- Sheet 2: Full Trade Detail (every field, for audit) -----------
    detail = wb.create_sheet("Trade Detail")
    detail.append([
        "Trade #", "Date", "Time", "Symbol", "Expiry", "Direction", "System Point",
        "Entry Price", "Initial SL", "Trailing Stop (at exit)", "Exit Price", "Exit Date",
        "Exit Reason", "Reversal Event ID", "P&L Points", "P&L %", "Holding Period", "Status",
    ])
    for n, t in enumerate(result.trades, start=1):
        detail.append([
            n, t.entry_date.date(), t.entry_date.time(), t.trading_symbol, t.expiry, t.direction,
            t.system_point, t.entry_price, t.initial_sl, t.active_stop,
            t.exit_price, t.exit_date.date() if t.exit_date else "", t.exit_reason,
            t.reversal_event_id, t.pnl_points, t.pnl_pct, t.holding_days, t.status,
        ])
    _autosize(detail)

    # ---- Sheet 3: Backtest Summary --------------------------------------
    summary = wb.create_sheet("Backtest Summary")
    summary_rows = [
        ("Strategy", "Top-Bottom (Trailing Stop & Reverse)"),
        ("Symbol", result.symbol),
        ("Trading Symbol", result.trading_symbol),
        ("Expiry", result.expiry),
        ("Instrument Type", result.instrument_class),
        ("Timeframe", result.timeframe),
        ("From Date", result.coverage.requested_from),
        ("To Date", result.coverage.requested_to),
        ("Data Available From", result.coverage.available_from),
        ("Data Available To", result.coverage.available_to),
        ("Data Complete", result.coverage.is_complete),
        ("Total Signals", s.total_signals),
        ("Buy Signals", s.buy_signals),
        ("Sell Signals", s.sell_signals),
        ("Total Trades", s.total_trades),
        ("Buy Trades", s.buy_trades),
        ("Sell Trades", s.sell_trades),
        ("Winning Trades", s.winning_trades),
        ("Losing Trades", s.losing_trades),
        ("Win Rate %", round(s.win_rate, 2)),
        ("Gross Profit %", round(s.gross_profit_pct, 2)),
        ("Gross Loss %", round(s.gross_loss_pct, 2)),
        ("Net P&L %", round(s.net_pnl_pct, 2)),
        ("Profit Factor", round(s.profit_factor, 2) if s.profit_factor is not None else "N/A"),
        ("Max Drawdown %", round(s.max_drawdown_pct, 2)),
        ("Average Trade %", round(s.average_trade_pct, 2)),
        ("Best Trade %", round(s.best_trade_pct, 2)),
        ("Worst Trade %", round(s.worst_trade_pct, 2)),
        ("Average Holding Period (days)", round(s.average_holding_days, 2)),
        ("Expectancy %", round(s.expectancy_pct, 2)),
    ]
    summary.append(["Field", "Value"])
    for r in summary_rows:
        summary.append(r)
    _autosize(summary)

    # ---- Sheet 4: Equity Curve -------------------------------------------
    equity = wb.create_sheet("Equity Curve")
    equity.append(["Date", "Trade #", "Equity", "Cumulative P&L %", "Drawdown %"])
    for e in result.equity_curve:
        equity.append([e.date.date(), e.trade_number, round(e.equity, 4), round(e.cumulative_pnl_pct, 4), round(e.drawdown_pct, 4)])
    _autosize(equity)

    # ---- Sheet 5: Signal Log ----------------------------------------------
    signals = wb.create_sheet("Signal Log")
    signals.append(["Date", "Time", "Symbol", "Signal", "System Point", "Entry Price", "Reversal Event ID", "Reason"])
    for sig in result.signals:
        reason = (
            f"Reversal: crossed {'above' if sig.direction == 'BUY' else 'below'} System Point ({sig.system_point})"
            if sig.reversal_event_id
            else f"Breakout: close {'above' if sig.direction == 'BUY' else 'below'} latest {'Top' if sig.direction == 'BUY' else 'Bottom'} ({sig.system_point})"
        )
        signals.append([
            sig.signal_date.date(), sig.signal_date.time(), result.trading_symbol, sig.direction,
            sig.system_point, sig.entry_price, sig.reversal_event_id or "", reason,
        ])
    _autosize(signals)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

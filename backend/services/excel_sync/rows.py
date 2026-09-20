from __future__ import annotations

import datetime as dt
from typing import Any

from backend.services.excel_sync.naming import _MONTHS, to_ist
from backend.services.instrument_classifier import get_instrument_type

HEADERS = [
    "Scan ID", "Scan Date", "Scan Time", "Scan Type", "Symbol", "Instrument Type", "Strategy", "Timeframe",
    "Status", "Price", "RSI", "Signal", "A Date", "B Date", "A Price", "B Price", "A RSI", "B RSI",
    "A-B Distance", "Details", "Updated At",
]
LAST_COLUMN = "U"  # len(HEADERS) == 21


def _d(v: Any) -> str:
    if v is None:
        return ""
    return str(v)[:10]


def _num(v: Any) -> Any:
    return "" if v is None else (round(float(v), 4) if isinstance(v, (int, float)) else v)


class RowContext:
    def __init__(self, scan_id: str, scan_type: str, started_at: dt.datetime):
        t = to_ist(started_at)
        self.scan_id, self.scan_type = scan_id, scan_type
        self.date = f"{t.day:02d}-{_MONTHS[t.month - 1]}-{t.year}"
        self.time = t.strftime("%H:%M:%S")

    def base(self, symbol: str) -> list[Any]:
        now = to_ist(dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")
        row = [""] * len(HEADERS)
        row[0], row[1], row[2], row[3] = self.scan_id, self.date, self.time, self.scan_type
        row[4], row[5] = symbol, get_instrument_type(symbol)
        row[20] = now
        return row


def _rsi_for(signal: Any, timeframe: str) -> Any:
    return {"daily": signal.daily_rsi, "weekly": signal.weekly_rsi, "monthly": signal.monthly_rsi}.get(timeframe.lower())


def signal_rows(ctx: RowContext, symbol: str, strategy: str, signal: Any) -> list[tuple[tuple, list[Any]]]:
    """(dedupe_key, row) pairs for one qualifying (or PRD_FORMING) signal.
    Never re-derives strategy logic — only reads the signal's own fields."""
    extra = getattr(signal, "extra", {}) or {}
    price = extra.get("current_price")
    out: list[tuple[tuple, list[Any]]] = []

    if strategy == "PRD Forming":
        for f in extra.get("forming", []):
            r = ctx.base(symbol)
            tf = str(f.get("timeframe", ""))
            r[6], r[7], r[8], r[9], r[10] = "PRD", tf.upper(), "PRD_FORMING", _num(price), _num(_rsi_for(signal, tf))
            r[11] = "PRD_FORMING"
            r[12], r[13], r[14], r[15] = _d(f.get("a_date")), _d(f.get("b_date")), _num(f.get("a_low")), _num(f.get("b_low"))
            r[16], r[17], r[18] = _num(f.get("a_rsi")), _num(f.get("b_rsi")), f.get("ab_distance", "")
            r[19] = (signal.explanation or "")[:400]
            out.append(((symbol, "PRD", tf.upper(), "PRD_FORMING", _d(f.get("a_date"))), r))
        return out

    status = extra.get("status") if strategy in ("PRD", "NRD") else None
    divs = extra.get("divergences") or []
    if strategy in ("PRD", "NRD") and divs:
        for d in divs:
            r = ctx.base(symbol)
            tf = str(d.get("timeframe", ""))
            a_date = d.get("a_date", d.get("swing1_date"))
            b_date = d.get("b_date", d.get("swing2_date"))
            r[6], r[7], r[8] = strategy, tf.upper(), status or "QUALIFIED"
            r[9], r[10], r[11] = _num(price), _num(_rsi_for(signal, tf)), status or "QUALIFIED"
            r[12], r[13] = _d(a_date), _d(b_date)
            r[14], r[15] = _num(d.get("a_low", d.get("swing1_price"))), _num(d.get("b_low", d.get("swing2_price")))
            r[16], r[17] = _num(d.get("a_rsi", d.get("rsi1"))), _num(d.get("b_rsi", d.get("rsi2")))
            if d.get("ab_distance") is not None:
                r[18] = d["ab_distance"]
            elif d.get("swing1_bar") is not None and d.get("swing2_bar") is not None:
                r[18] = d["swing2_bar"] - d["swing1_bar"]
            r[19] = (signal.explanation or "")[:400]
            out.append(((symbol, strategy, tf.upper(), r[8], _d(a_date)), r))
        return out

    r = ctx.base(symbol)
    r[6], r[8], r[9], r[11] = strategy, "QUALIFIED", _num(price), "QUALIFIED"
    r[10] = _num(signal.weekly_rsi if signal.weekly_rsi is not None else signal.daily_rsi)
    r[19] = (getattr(signal, "explanation", "") or "")[:400]
    return [((symbol, strategy, "", "QUALIFIED", ""), r)]


def status_row(ctx: RowContext, symbol: str, status: str, details: str = "") -> tuple[tuple, list[Any]]:
    r = ctx.base(symbol)
    r[8], r[19] = status, details[:400]
    return (symbol, "", "", status, ""), r

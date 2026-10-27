"""Parses the user's manual trade sheet (DATE | CALL/PUT | 15 minute candle size |
PROFIT | LOSS | EOD) so it can be compared with the backtest. Read-only and
in-memory; the workbook is never stored."""
from __future__ import annotations

import datetime as dt
import io
from dataclasses import asdict, dataclass

import openpyxl

MAX_BYTES = 2_000_000


class ExcelImportError(ValueError):
    pass


@dataclass
class ManualRow:
    date: str
    side: str | None  # CALL | PUT | None
    candle_pct: float | None
    outcome: str | None  # PROFIT | LOSS | None
    eod_pct: float | None


def _date(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%y", "%d-%b-%Y"):
            try:
                return dt.datetime.strptime(v.strip(), fmt).date()
            except ValueError:
                pass
    return None


def _num(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().rstrip("%").replace(",", ""))
        except ValueError:
            return None
    return None


def _to_pct(values: list[float | None]) -> list[float | None]:
    """Excel percent cells hold fractions (0.0031 = 0.31%). If the column's typical (median) value is
    tiny treat the column as fractions — one typo'd outlier must not flip the whole column; otherwise
    the values were already typed as percentages."""
    nums = sorted(abs(v) for v in values if v is not None)
    scale = 100.0 if nums and nums[len(nums) // 2] <= 0.1 else 1.0
    return [None if v is None else round(v * scale, 4) for v in values]


def parse_workbook(content: bytes) -> tuple[list[dict], list[str]]:
    if len(content) > MAX_BYTES:
        raise ExcelImportError("Excel file too large (max 2 MB)")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ExcelImportError(f"Could not read this as an .xlsx file: {exc}") from exc
    rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    header_i = next((i for i, r in enumerate(rows) if any(isinstance(c, str) and c.strip().upper() == "DATE" for c in r)), None)
    if header_i is None:
        raise ExcelImportError("No header row with a DATE column found")
    head = [str(c or "").strip().upper() for c in rows[header_i]]

    def col(*needles: str) -> int | None:
        return next((i for i, h in enumerate(head) if any(n in h for n in needles)), None)

    c_date, c_side = col("DATE"), col("CALL", "PUT", "SIDE")
    c_size, c_profit, c_loss, c_eod = col("CANDEL", "CANDLE", "SIZE"), col("PROFIT"), col("LOSS"), col("EOD")
    if c_date is None:
        raise ExcelImportError("DATE column not found")

    def cell(r, i):
        return r[i] if i is not None and i < len(r) else None

    parsed: list[tuple[dt.date, str | None, float | None, str | None, float | None]] = []
    skipped: list[str] = []
    for n, r in enumerate(rows[header_i + 1:], start=header_i + 2):
        if all(c is None for c in r):
            continue
        d = _date(cell(r, c_date))
        if d is None:
            skipped.append(f"row {n}: unreadable date")
            continue
        side = str(cell(r, c_side) or "").strip().upper() or None
        side = side if side in ("CALL", "PUT") else None
        text = " ".join(str(cell(r, i) or "") for i in (c_profit, c_loss)).upper()
        outcome = "PROFIT" if "PROFIT" in text else "LOSS" if "LOSS" in text else None
        parsed.append((d, side, _num(cell(r, c_size)), outcome, _num(cell(r, c_eod))))
    sizes, eods = _to_pct([p[2] for p in parsed]), _to_pct([p[4] for p in parsed])
    out = [asdict(ManualRow(p[0].isoformat(), p[1], sizes[i], p[3], eods[i])) for i, p in enumerate(parsed)]
    return out, skipped

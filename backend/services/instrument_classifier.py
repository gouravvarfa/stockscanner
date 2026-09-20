"""
ONE centralized FUTURE / EQUITY classification.

get_instrument_type(symbol) -> "FUTURE" if the normalized NSE symbol is on
the F&O stock list in the project's own NSE_Futures_Stocks_*.xlsx, else
"EQUITY". This is DISPLAY metadata only — it is never a strategy filter;
every stock is still scanned exactly the same way.
"""
from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Literal

import openpyxl

InstrumentType = Literal["FUTURE", "EQUITY"]

_FUTURES_GLOB = "NSE_Futures_Stocks_*.xlsx"
_futures_cache: frozenset[str] | None = None
_futures_file: str | None = None


def normalize_symbol(symbol: str | None) -> str:
    """Upper-case, trim, drop an exchange prefix (NSE:) and Angel One's
    "-EQ/-BE/-BZ" series suffix. Punctuation that is part of a real ticker
    (M&M, BAJAJ-AUTO) is kept."""
    s = (symbol or "").strip().upper()
    if ":" in s:
        s = s.split(":", 1)[1]
    s = re.sub(r"-(EQ|BE|BZ)$", "", s)
    return re.sub(r"\s+", "", s)


def _find_futures_file() -> Path | None:
    matches = sorted(glob.glob(_FUTURES_GLOB))
    return Path(matches[-1]) if matches else None


def load_futures_symbols() -> frozenset[str]:
    global _futures_cache, _futures_file
    if _futures_cache is not None:
        return _futures_cache
    path = _find_futures_file()
    symbols: set[str] = set()
    if path is not None:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        header = [str(c).strip() if c is not None else "" for c in next(rows, ())]
        col = header.index("NSE Symbol") if "NSE Symbol" in header else 1
        for row in rows:
            if col < len(row) and row[col]:
                symbols.add(normalize_symbol(str(row[col])))
        _futures_file = str(path)
    _futures_cache = frozenset(symbols)
    return _futures_cache


def futures_file_in_use() -> str | None:
    load_futures_symbols()
    return _futures_file


def reset_cache() -> None:
    global _futures_cache, _futures_file
    _futures_cache = None
    _futures_file = None


def get_instrument_type(symbol: str | None) -> InstrumentType:
    return "FUTURE" if normalize_symbol(symbol) in load_futures_symbols() else "EQUITY"

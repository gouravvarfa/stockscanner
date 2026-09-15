"""
Master universe loader — reads the single Excel file that is now the sole,
authoritative source of the scanner's stock universe:

  A_Group_Stock_List.xlsx -> every strategy (Strategy One, GFS, Advanced GFS,
                             PRD, NRD, Value Buy) and both Expiry levels

This replaced the earlier NIFTY 200 / NIFTY 500 split; those sheets are no
longer read. The BSE A Group scrip names in that file were mapped to NSE
trading symbols against NSE's own published symbol/company-name master and
each result verified to exist in Angel One's scrip master — rows whose
Symbol cell is blank are constituents that have since been delisted or
merged, and are skipped rather than guessed at.

No other source (Tapetide, NSE scraping, hardcoded lists) is ever consulted
for these. Symbols are read exactly as given — never padded, deduplicated
beyond exact-match, or fabricated. A missing file or an unexpected column
layout raises immediately rather than silently returning a partial/empty
universe, since a scan proceeding on a wrong/empty list would be worse than
failing loudly.

Loaded once per process and cached in memory (the files are static content
for a given trading list; if the Excel files change on disk, restart the
backend to pick up the new list) — this avoids re-parsing the same ~500-row
sheet on every scan.
"""
from __future__ import annotations

from pathlib import Path

import openpyxl

A_GROUP_PATH = Path("A_Group_Stock_List.xlsx")

_a_group_cache: list[str] | None = None


def _load_symbol_column(path: Path, symbol_column: str) -> list[str]:
    if not path.exists():
        raise RuntimeError(f"Universe file not found: {path}. It must exist in the project root.")

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(min_row=1, max_row=1, values_only=True)
    header = list(next(rows, ()))
    if symbol_column not in header:
        raise RuntimeError(
            f"Universe file '{path}' is missing the expected '{symbol_column}' column "
            f"(found columns: {header}) — refusing to guess."
        )
    idx = header.index(symbol_column)

    symbols: list[str] = []
    seen: set[str] = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if idx >= len(row) or row[idx] is None:
            continue
        symbol = str(row[idx]).strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)

    if not symbols:
        raise RuntimeError(f"Universe file '{path}' yielded zero symbols — refusing to run a scan on an empty universe.")

    return symbols


def load_a_group_universe() -> list[str]:
    """
    The BSE "A Group" universe — now the single universe every strategy runs
    over. Rows whose Symbol cell is blank are A-Group constituents that have
    since been delisted or merged and have no current NSE listing; they are
    skipped rather than guessed at (see the sheet's Match Status column).
    """
    global _a_group_cache
    if _a_group_cache is None:
        _a_group_cache = _load_symbol_column(A_GROUP_PATH, "Symbol")
    return list(_a_group_cache)


def reset_cache_for_tests() -> None:
    global _a_group_cache
    _a_group_cache = None

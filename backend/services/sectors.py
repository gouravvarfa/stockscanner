"""A-Group symbol -> sector (NSE industry classification), from
backend/data/a_group_sectors.csv. Display-only; never used by strategies."""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "data" / "a_group_sectors.csv"


@lru_cache(maxsize=1)
def _sectors() -> dict[str, str]:
    try:
        with open(_PATH, encoding="utf-8") as fh:
            return {r["symbol"].strip().upper(): r["sector"].strip() for r in csv.DictReader(fh)}
    except OSError:
        return {}


_INDUSTRY = Path(__file__).resolve().parent.parent / "data" / "nse_industry.csv"


@lru_cache(maxsize=1)
def _industries() -> dict[str, str]:
    """NSE's industry tag for ~1,000 stocks (Nifty Total Market + Microcap 250) - the fallback for stocks outside the
    A Group list (2026-11-23: sectors now include every NSE stock of their industry, e.g. Karnataka Bank)."""
    try:
        with open(_INDUSTRY, encoding="utf-8") as fh:
            return {r["symbol"].strip().upper(): r["industry"].strip() for r in csv.DictReader(fh)}
    except OSError:
        return {}


def sector_for(symbol: str) -> str | None:
    key = symbol.strip().upper()
    return _sectors().get(key) or _industries().get(key) or None

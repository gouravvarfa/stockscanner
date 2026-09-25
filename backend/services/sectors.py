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


def sector_for(symbol: str) -> str | None:
    return _sectors().get(symbol.strip().upper()) or None

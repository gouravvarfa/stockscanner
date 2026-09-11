"""
Maps a Tapetide sector-index name (from backend/config/sector_mapping.py) to
Angel One's own index `name` field, for fetching enough history (500+ days)
to compute monthly RSI — Tapetide's get_index_history has no pagination and
caps at ~6 months per call, nowhere near enough for a 15+-month monthly RSI.

Built from the ACTUAL Angel One index catalog (AMXIDX rows in their public
scrip master), not guessed. Only ~9 of Tapetide's ~21 mapped sectors have a
real Angel One equivalent — sectors with no entry here have their monthly
sector RSI reported as genuinely unavailable, not approximated.
"""
from __future__ import annotations

TAPETIDE_INDEX_TO_ANGELONE_NAME: dict[str, str] = {
    "Nifty Bank": "BANKNIFTY",
    "Nifty IT": "NIFTY IT",
    "Nifty Auto": "NIFTY AUTO",
    "Nifty FMCG": "NIFTY FMCG",
    "Nifty Energy": "NIFTY ENERGY",
    "Nifty Metal": "NIFTY METAL",
    "Nifty Realty": "NIFTY REALTY",
    "Nifty Media": "NIFTY MEDIA",
    "Nifty Financial Services": "FINNIFTY",
}

# The NIFTY 50 benchmark itself is always resolvable via Angel One.
NIFTY_50_ANGELONE_NAME = "NIFTY"


def resolve_angelone_index_name(tapetide_index_name: str) -> str | None:
    return TAPETIDE_INDEX_TO_ANGELONE_NAME.get(tapetide_index_name)

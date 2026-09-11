"""
Maps Tapetide's per-stock `Sector` label (from market_heatmap) to the real
NSE sectoral index name used for get_index_history / get_index_performance.

The two taxonomies do not line up 1:1. This mapping was built by cross
referencing the actual NIFTY 200 heatmap sector labels observed against the
real list of ~35 NSE sectoral indices returned by
get_index_performance(category="sectoral") on 2026-09-09 — it is not guessed.

Where no reasonable NSE sectoral index exists for a Tapetide sector, the
value is None. The sector-analysis engine MUST treat None as
"DATA UNAVAILABLE" for that sector's index-level return/RSI — it must never
silently substitute an approximate index (per spec section 36/29).
"""
from __future__ import annotations

TAPETIDE_SECTOR_TO_NSE_INDEX: dict[str, str | None] = {
    "Banks": "Nifty Bank",
    "Information Technology": "Nifty IT",
    "Financial Services": "Nifty Financial Services",
    "Automobiles": "Nifty Auto",
    "FMCG": "Nifty FMCG",
    "Healthcare": "Nifty Healthcare",
    "Metals & Mining": "Nifty Metal",
    "Oil & Gas": "Nifty Oil & Gas",
    "Energy": "Nifty Energy",
    "Power": "Nifty Power",
    "Telecom": "Nifty Telecommunications",
    "Construction": "Nifty Construction",
    "Retail": "Nifty Retail",
    "Chemicals": "Nifty Chemicals",
    "Realty": "Nifty Realty",
    "Insurance": "Nifty Insurance",
    "Capital Goods": "Nifty Capital Goods",
    "Media": "Nifty Media",
    "Consumer Durables": "Nifty Consumer Durables",
    "NBFC": "Nifty NBFC",
    "Cement": "Nifty Cement",
    # No dedicated NSE sectoral index exists for these Tapetide sectors
    # (confirmed against the full sectoral index catalog) — sector-level
    # return/RSI for stocks in these sectors must be reported unavailable
    # rather than approximated.
    "Petroleum Products": None,
    "Consumer Goods": None,
    "Food Products": None,
    "Transport": None,
    "Services": None,
    "Textiles": None,
    "Diversified": None,
}

# SPECULATIVE, NOT YET VERIFIED: NSE publishes "Nifty India Defence" as a
# THEMATIC index (not one of the ~35 "sectoral" ones the mapping above was
# cross-referenced against), so it's untested whether get_index_history
# actually recognizes this exact name. Angel One's own index catalog also has
# no defence-specific entry (checked directly — confirmed absent), so if this
# doesn't resolve, "Aerospace & Defense" has no working source from either
# provider and must fall back to DATA UNAVAILABLE (the existing error-handling
# in sector_analysis already does this safely on any fetch failure). Added
# provisionally because Tapetide's own daily quota was exhausted at the time
# this was written, blocking a direct verification call — CONFIRM before
# trusting its sector RSI/return numbers.
TAPETIDE_SECTOR_TO_NSE_INDEX["Aerospace & Defense"] = "Nifty India Defence"


def resolve_sector_index(tapetide_sector: str) -> str | None:
    """Return the NSE sectoral index name for a Tapetide sector, or None if unmapped."""
    return TAPETIDE_SECTOR_TO_NSE_INDEX.get(tapetide_sector)

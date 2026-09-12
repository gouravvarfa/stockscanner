"""
Maps the real NSE sectoral index name (as used elsewhere — see
sector_mapping.py's TAPETIDE_SECTOR_TO_NSE_INDEX values) to its Yahoo
Finance ticker, for the sectors where Yahoo's feed is actually verified
live.

IMPORTANT — verified 2026-09-12: most "^CNX..." NSE sectoral tickers on
Yahoo Finance stopped updating on 2026-07-17 (confirmed by direct check —
Auto, FMCG, Metal, Energy, Realty, Media, Financial Services, PSU Bank,
Infra, Consumption, Commodities, MNC, Services all dead/stale). Only a
handful of tickers are still genuinely live. Mapping ONLY those — everything
else is intentionally left unmapped (None) so Yahoo mode reports that
sector as unavailable rather than silently serving 2-month-old data as if
it were current. Re-verify before adding any entry here.
"""
from __future__ import annotations

NSE_INDEX_TO_YAHOO_TICKER: dict[str, str] = {
    "Nifty Bank": "^NSEBANK",
    "Nifty IT": "^CNXIT",
    "Nifty Healthcare": "^CNXPHARMA",  # NSE has no distinct "healthcare" feed on Yahoo; Nifty Pharma is the closest live proxy
}

NIFTY_50_YAHOO_TICKER = "^NSEI"


def resolve_yahoo_index_ticker(nse_index_name: str) -> str | None:
    """Return the Yahoo Finance ticker for an NSE sectoral index name, or None if unmapped/unverified-live."""
    return NSE_INDEX_TO_YAHOO_TICKER.get(nse_index_name)

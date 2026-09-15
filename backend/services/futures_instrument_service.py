"""
Futures-only instrument search for the Top-Bottom Backtesting module.

Deliberately isolated from every other instrument-resolution path in the
app (angelone_scrip_master.resolve_equity/resolve_index used by the main
scanner and chart are untouched) — this module must NEVER be able to return
a cash/equity, ETF, mutual-fund, or options symbol.

Two layers of defense against a non-futures symbol leaking through:
  1. Only rows with instrumenttype FUTSTK/FUTIDX from Angel One's own live
     scrip master are ever considered (see angelone_scrip_master.py).
  2. For stock futures, the underlying must also be on NSE's current F&O
     stock list (ALLOWED_FNO_STOCK_UNDERLYINGS below) — belt-and-suspenders
     in case a stale/delisted FUTSTK row briefly lingers in the master.
Index futures (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY) are always allowed
without the stock allow-list, since they are not stocks.
"""
from __future__ import annotations

from backend.providers import angelone_scrip_master as scrip_master
from backend.providers.angelone_scrip_master import FutureContract

# NSE's current F&O-eligible stock underlyings (ticker roots). Reviewed
# 2026-09; NSE revises this list periodically — a stock genuinely removed
# from F&O will stop appearing in Angel One's own FUTSTK rows anyway, so
# this list only ever narrows, never has to be perfectly in sync with NSE.
ALLOWED_FNO_STOCK_UNDERLYINGS: frozenset[str] = frozenset(
    """
    AARTIIND ABB ABBOTINDIA ACC ADANIENT ADANIPORTS ABCAPITAL ABFRL ALKEM
    AMBUJACEM APOLLOHOSP APOLLOTYRE ASHOKLEY ASIANPAINT ASTRAL ATUL AUBANK
    AUROPHARMA AXISBANK BAJAJ-AUTO BAJFINANCE BAJAJFINSV BALKRISIND
    BALRAMCHIN BANDHANBNK BANKBARODA BATAINDIA BERGEPAINT BEL BHARATFORG
    BHEL BPCL BHARTIARTL BIOCON BSOFT BOSCHLTD BRITANNIA CANFINHOME CANBK
    CHAMBLFERT CHOLAFIN CIPLA CUB COALINDIA COFORGE COLPAL CONCOR
    COROMANDEL CROMPTON CUMMINSIND DABUR DALBHARAT DEEPAKNTR DELTACORP
    DIVISLAB DIXON DLF LALPATHLAB DRREDDY EICHERMOT ESCORTS EXIDEIND GAIL
    GLENMARK GMRINFRA GODREJCP GODREJPROP GRANULES GRASIM GUJGASLTD GNFC
    HAVELLS HCLTECH HDFCAMC HDFCBANK HDFCLIFE HEROMOTOCO HINDALCO HAL
    HINDCOPPER HINDPETRO HINDUNILVR ICICIBANK ICICIGI ICICIPRULI IDFCFIRSTB
    INDIAMART IEX IOC IRCTC IGL INDUSTOWER INDUSINDBK NAUKRI INFY INDIGO
    IPCALAB ITC JINDALSTEL JKCEMENT JSWSTEEL JUBLFOOD KOTAKBANK LTTS LTIM
    LT LAURUSLABS LICHSGFIN LUPIN MGL M&MFIN M&M MANAPPURAM MARICO MARUTI
    MFSL METROPOLIS MOTHERSON MPHASIS MRF MUTHOOTFIN NATIONALUM NAVINFLUOR
    NESTLEIND NMDC NTPC OBEROIRLTY ONGC OFSS PAGEIND PERSISTENT PETRONET
    PIIND PIDILITIND PEL POLYCAB PFC POWERGRID PNB PVRINOX RBLBANK RECLTD
    RELIANCE SBICARD SBILIFE SHREECEM SHRIRAMFIN SIEMENS SRF SBIN SAIL
    SUNPHARMA SUNTV SYNGENE TATACHEM TATACOMM TCS TATACONSUM TATAMOTORS
    TATAPOWER TATASTEEL TECHM FEDERALBNK INDIACEM INDHOTEL RAMCOCEM TITAN
    TORNTPHARM TRENT TVSMOTOR ULTRACEMCO UBL MCDOWELL-N UPL VEDL IDEA
    VOLTAS WHIRLPOOL WIPRO ZEEL ZYDUSLIFE
    """.split()
)


class NotAFutureError(ValueError):
    """Raised when a caller asks this service to resolve something that is
    not a currently listed NFO futures contract — never silently coerced
    into one."""


def _is_allowed(contract: FutureContract) -> bool:
    return contract.is_index or contract.underlying.upper() in ALLOWED_FNO_STOCK_UNDERLYINGS


async def search_futures(query: str, limit: int = 25) -> list[FutureContract]:
    """Every live futures contract (all expiries) whose underlying matches `query`."""
    raw = await scrip_master.search_futures(query, limit=limit * 3)
    return [c for c in raw if _is_allowed(c)][:limit]


async def list_contracts(underlying: str) -> list[FutureContract]:
    """All live expiries for one underlying, nearest expiry first."""
    raw = await scrip_master.get_future_contracts(underlying)
    return [c for c in raw if _is_allowed(c)]


async def nearest_contract(underlying: str) -> FutureContract | None:
    """The current/nearest liquid contract for a symbol — the default the UI preselects."""
    contracts = await list_contracts(underlying)
    return contracts[0] if contracts else None


async def resolve_contract(underlying: str, expiry: str | None) -> FutureContract:
    """
    Resolves one exact contract. `expiry` is an ISO date ('2026-09-29')
    matching a live contract's expiry; if omitted, the nearest expiry is
    used. Raises NotAFutureError if the underlying has no live futures
    contract at all, or no contract at that exact expiry — never
    substitutes a different one silently.
    """
    contracts = await list_contracts(underlying)
    if not contracts:
        raise NotAFutureError(
            f"'{underlying}' has no live NSE futures contract. "
            "Top-Bottom strategy is available only for Futures."
        )
    if expiry is None:
        return contracts[0]
    for c in contracts:
        if c.expiry == expiry:
            return c
    available = ", ".join(c.expiry for c in contracts)
    raise NotAFutureError(
        f"No live '{underlying}' futures contract expiring {expiry}. Available expiries: {available}."
    )

"""
Equity symbol search for the Top-Bottom Backtesting module, restricted to
the BSE "A Group" universe (A_Group_Stock_List.xlsx) — the same list the
main scanner runs on, loaded through the existing universe_loader.

Mirrors futures_instrument_service.py's two-layer safety approach: the
symbol must be in the A Group universe AND resolve to a real NSE cash
listing in Angel One's own scrip master. Anything else is rejected rather
than silently scanned.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.providers import angelone_scrip_master as scrip_master
from backend.services import universe_loader


@dataclass
class EquityInstrument:
    symbol: str  # A Group / NSE ticker root, e.g. "ADANIGREEN"
    trading_symbol: str  # Angel One listing, e.g. "ADANIGREEN-EQ"
    token: str
    exch_seg: str  # always "NSE"


class NotAnAGroupEquityError(ValueError):
    """The symbol is not in the A Group universe, or has no live NSE cash
    listing — never coerced into some other symbol."""


def search_equities(query: str, limit: int = 25) -> list[str]:
    """A Group symbols matching `query`. Symbols starting with the query
    rank first, then symbols merely containing it."""
    q = query.strip().upper()
    if not q:
        return []
    universe = universe_loader.load_a_group_universe()
    starts = [s for s in universe if s.startswith(q)]
    contains = [s for s in universe if q in s and not s.startswith(q)]
    return (starts + contains)[:limit]


async def resolve_equity(symbol: str) -> EquityInstrument:
    symbol = symbol.strip().upper()
    if symbol not in set(universe_loader.load_a_group_universe()):
        raise NotAnAGroupEquityError(
            f"'{symbol}' is not in the A Group stock list."
        )
    match = await scrip_master.resolve_equity(symbol)
    if match is None:
        raise NotAnAGroupEquityError(f"'{symbol}' has no live NSE equity listing.")
    return EquityInstrument(
        symbol=symbol,
        trading_symbol=match.trading_symbol,
        token=match.token,
        exch_seg=match.exch_seg,
    )

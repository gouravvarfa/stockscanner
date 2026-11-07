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

import difflib
import re
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
    found = starts + contains

    # Also match by company name ("Divi's Laboratories"), ignoring punctuation.
    def norm(text: str) -> str:
        return re.sub(r"[^A-Z0-9 ]", "", text.upper())

    nq = norm(q)
    q_tokens = nq.split()
    squashed = nq.replace(" ", "")
    for s in universe:
        if s in found:
            continue
        name = norm(universe_loader.company_name_for(s) or "")
        tokens = name.split()
        if squashed and squashed in s.replace(" ", ""):
            found.append(s)
        elif q_tokens and all(any(t.startswith(qt) for t in tokens) for qt in q_tokens):
            found.append(s)

    # Typo tolerance ("Devis Labs" -> DIVISLAB): fuzzy fallback only if nothing matched.
    if not found:
        close = difflib.get_close_matches(squashed, universe, n=limit, cutoff=0.6)
        found = close or difflib.get_close_matches(
            squashed, [s for s in universe], n=limit, cutoff=0.5
        )
        if not found:
            for s in universe:
                name = norm(universe_loader.company_name_for(s) or "").replace(" ", "")
                if name and difflib.SequenceMatcher(None, squashed, name[: len(squashed) + 4]).ratio() >= 0.7:
                    found.append(s)
    return found[:limit]


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

"""
Explicit, verified capability declarations for each market-data provider.

These are NOT guesses — each flag reflects behavior actually confirmed in
this project:
- Tapetide: its own `get_price_history` tool description states plainly
  "Only end-of-day bars exist: intraday values like 1m/5m/15m/1h ... are NOT
  supported and return an explanatory error" — confirmed by a live call.
  Sector/universe data confirmed via `market_heatmap`/`get_index_history`.
- Angel One: 15m/1h/daily candles and stock-future resolution were all
  exercised with real live calls (see Expiry Level 1/5). It has no NIFTY-200
  universe or sector-return concept in this integration — its scrip master
  is a symbol/token directory only, not a ranked/sectored universe.

Weekly/monthly are not separate provider capabilities: both providers only
ever return daily bars from the network, and weekly/monthly series are
*always* derived locally afterward via backend/indicators/resample.py — so a
provider's weekly/monthly capability is identical to its daily capability.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_name: str
    supports_daily: bool
    supports_weekly: bool
    supports_monthly: bool
    supports_15m: bool
    supports_1h: bool
    supports_universe: bool  # NIFTY 200 constituent list with sector tags
    supports_sector_data: bool  # NSE sectoral index return/RSI series
    supports_stock_futures: bool  # F&O stock-future contract resolution + candles
    supports_options: bool  # not wired into the router in this project


TAPETIDE_CAPABILITIES = ProviderCapabilities(
    provider_name="TAPETIDE",
    supports_daily=True,
    supports_weekly=True,
    supports_monthly=True,
    supports_15m=False,
    supports_1h=False,
    supports_universe=True,
    supports_sector_data=True,
    supports_stock_futures=False,
    supports_options=False,
)

ANGEL_ONE_CAPABILITIES = ProviderCapabilities(
    provider_name="ANGEL_ONE",
    supports_daily=True,
    supports_weekly=True,
    supports_monthly=True,
    supports_15m=True,
    supports_1h=True,
    supports_universe=False,
    supports_sector_data=False,
    supports_stock_futures=True,
    supports_options=False,
)


def capability_for_timeframe(caps: ProviderCapabilities, timeframe: str) -> bool:
    return {
        "1d": caps.supports_daily,
        "1w": caps.supports_weekly,
        "1mo": caps.supports_monthly,
        "15m": caps.supports_15m,
        "1h": caps.supports_1h,
    }.get(timeframe, False)

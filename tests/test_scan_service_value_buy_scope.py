import pandas as pd

from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
from backend.services.scan_service import run_full_scan


def _ohlc(n, base=100.0, step=0.0, start="2023-01-02"):
    idx = pd.bdate_range(start, periods=n)
    closes = [base + step * i for i in range(n)]
    return pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000] * n},
        index=idx,
    )


class FakeProvider:
    """
    "Banks" -> resolve_sector_index gives a real mapping ("Nifty Bank"), and
    is given strongly-outperforming, high-RSI index data -> qualifies.
    "Textiles" -> resolve_sector_index maps to None (no NSE index at all,
    per backend/config/sector_mapping.py) -> permanently unavailable, never
    qualifies, regardless of the stock's own data.
    """

    def __init__(self):
        self.stock_fetch_calls: dict[str, int] = {}

    async def get_universe(self, index_slug="nifty-200"):
        stocks = [
            {"symbol": "STRONGBANKSTOCK", "sector": "Banks"},
            {"symbol": "WEAKSECTORSTOCK", "sector": "Textiles"},
        ]
        return {"stocks": stocks, "requested": 2, "returned": 2, "complete": True, "sources": [], "note": None}

    async def get_index_ohlc(self, index_name, interval="3m"):
        if index_name == "Nifty Bank":
            return _ohlc(100, base=100.0, step=2.0)  # strong uptrend -> high RSI, clear outperformance
        return _ohlc(100, base=100.0, step=0.05)  # NIFTY 50 benchmark: mild rise

    async def get_stock_ohlcv(self, symbol, days=800):
        self.stock_fetch_calls[symbol] = self.stock_fetch_calls.get(symbol, 0) + 1
        return _ohlc(70, base=100.0, step=0.1)

    async def get_sector_performance(self, *a, **kw): raise NotImplementedError
    async def screen_technical(self, *a, **kw): raise NotImplementedError
    async def get_batch_quotes(self, *a, **kw): raise NotImplementedError


async def test_value_buy_runs_on_stocks_outside_qualifying_sectors():
    provider = FakeProvider()

    outcome = await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    assert "Banks" in outcome.qualifying_sectors
    assert "Textiles" not in outcome.qualifying_sectors

    # The sector-dependent strategies (Strategy One and friends) only ever
    # see sector-qualified stocks -> unaffected by the Value Buy scope change.
    all_result_symbols = {r.symbol for r in outcome.all_results}
    assert "STRONGBANKSTOCK" in all_result_symbols
    assert "WEAKSECTORSTOCK" not in all_result_symbols

    # But Value Buy's own candidate fetch was still attempted for the
    # non-qualifying-sector stock — it is NOT skipped just because its
    # sector never qualified.
    assert provider.stock_fetch_calls.get("WEAKSECTORSTOCK", 0) >= 1
    assert provider.stock_fetch_calls.get("STRONGBANKSTOCK", 0) >= 1


async def test_universe_results_include_every_analyzed_stock_without_affecting_top10_scope():
    provider = FakeProvider()

    outcome = await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    # The TRUE NIFTY 200 master universe (for the NIFTY 200 Scanner page)
    # includes BOTH the sector-qualified stock and the non-qualifying-sector
    # one — unlike all_results/qualifying_results/top10, which stay
    # Strategy-One-scoped.
    universe_by_symbol = {e.symbol: e for e in outcome.nifty200_universe}
    assert set(universe_by_symbol) == {"STRONGBANKSTOCK", "WEAKSECTORSTOCK"}

    # Every successfully-analyzed universe row has a recorded data source
    # (reused from the same fetch already made for that stock — no extra
    # provider calls) and status OK.
    assert universe_by_symbol["STRONGBANKSTOCK"].data_source == "tapetide"
    assert universe_by_symbol["STRONGBANKSTOCK"].status == "OK"
    assert universe_by_symbol["WEAKSECTORSTOCK"].data_source == "tapetide"
    assert universe_by_symbol["WEAKSECTORSTOCK"].status == "OK"

    # Sector metadata on each universe row is STOCK metadata (from the
    # universe provider), not derived from sector-index performance.
    assert universe_by_symbol["STRONGBANKSTOCK"].sector == "Banks"
    assert universe_by_symbol["WEAKSECTORSTOCK"].sector == "Textiles"

    # all_results/qualifying_results/top10 remain exactly as scoped before —
    # this new list is additive, not a replacement.
    all_result_symbols = {r.symbol for r in outcome.all_results}
    assert all_result_symbols == {"STRONGBANKSTOCK"}


async def test_master_universe_keeps_stock_with_unavailable_data_instead_of_dropping_it():
    class FlakyProvider(FakeProvider):
        async def get_stock_ohlcv(self, symbol, days=800):
            if symbol == "WEAKSECTORSTOCK":
                # Too few bars -> analyze_stock() returns None for this symbol.
                self.stock_fetch_calls[symbol] = self.stock_fetch_calls.get(symbol, 0) + 1
                return _ohlc(10, base=100.0, step=0.1)
            return await super().get_stock_ohlcv(symbol, days)

    provider = FlakyProvider()
    outcome = await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    universe_by_symbol = {e.symbol: e for e in outcome.nifty200_universe}

    # The stock is NEVER removed from the master universe just because its
    # own analysis failed — it stays present, marked unavailable.
    assert set(universe_by_symbol) == {"STRONGBANKSTOCK", "WEAKSECTORSTOCK"}
    weak = universe_by_symbol["WEAKSECTORSTOCK"]
    assert weak.status == "DATA_UNAVAILABLE"
    assert weak.status_reason
    # No fabricated price/RSI values for a stock that couldn't be analyzed.
    assert weak.current_price is None
    assert weak.daily_rsi is None
    assert weak.weekly_rsi is None
    assert weak.monthly_rsi is None
    # Sector metadata is still preserved even though analysis failed.
    assert weak.sector == "Textiles"

    strong = universe_by_symbol["STRONGBANKSTOCK"]
    assert strong.status == "OK"
    assert strong.current_price is not None


async def test_master_universe_count_matches_provider_universe_not_analysis_success():
    provider = FakeProvider()
    outcome = await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    # No fake/padded stocks: the master universe has exactly as many entries
    # as the authoritative universe provider returned, no more, no less.
    assert len(outcome.nifty200_universe) == outcome.universe_returned == 2
    assert outcome.universe_requested == 2
    assert outcome.universe_complete is True

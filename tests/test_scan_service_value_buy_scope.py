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

from dataclasses import dataclass

import pandas as pd

from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
from backend.providers.market_data_router import MarketDataRouter
from backend.services.scan_service import run_full_scan


def _ohlc(n, base=100.0, step=0.0, start="2023-01-02"):
    idx = pd.bdate_range(start, periods=n)
    closes = [base + step * i for i in range(n)]
    return pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000] * n},
        index=idx,
    )


@dataclass
class FakeScripMatch:
    token: str
    trading_symbol: str
    exch_seg: str = "NSE"


class TapetideCallGuard:
    """
    Raises if Tapetide's per-index/per-stock daily-history call is used for
    anything Angel One already covers — proves the call-budget optimization
    (reuse the Angel One 600-day series for daily too, prefer Angel One for
    per-stock OHLCV in AUTO mode) actually skips the redundant Tapetide call,
    not just that the end result happens to be correct.
    """

    def __init__(self):
        self.get_index_ohlc_calls: list[str] = []
        self.get_stock_ohlcv_calls: list[str] = []

    async def get_universe(self, index_slug="nifty-200"):
        stocks = [
            {"symbol": "HDFCBANK", "sector": "Banks"},  # Banks -> Nifty Bank -> Angel One covered
            {"symbol": "SUNPHARMA", "sector": "Healthcare"},  # Healthcare -> no Angel One coverage
        ]
        return {"stocks": stocks, "requested": 2, "returned": 2, "complete": True, "sources": [], "note": None}

    async def get_index_ohlc(self, index_name, interval="3m"):
        self.get_index_ohlc_calls.append(index_name)
        if index_name == "Nifty Healthcare":
            return _ohlc(100, base=100.0, step=0.05)  # only Tapetide has this one
        raise AssertionError(f"Tapetide get_index_ohlc('{index_name}') should not be called — Angel One covers it")

    async def get_stock_ohlcv(self, symbol, days=800):
        self.get_stock_ohlcv_calls.append(symbol)
        if symbol == "HDFCBANK":
            raise AssertionError("Tapetide get_stock_ohlcv('HDFCBANK') should not be called — Angel One succeeds first")
        return _ohlc(70, base=100.0, step=0.1)

    async def get_sector_performance(self, *a, **kw): raise NotImplementedError
    async def screen_technical(self, *a, **kw): raise NotImplementedError
    async def get_batch_quotes(self, *a, **kw): raise NotImplementedError


class FakeAngelOneProvider:
    def __init__(self):
        self.get_intraday_ohlc_calls: list[str] = []

    async def resolve_index(self, name: str):
        # "NIFTY" (benchmark) and "BANKNIFTY" (Nifty Bank sector) both resolve.
        return FakeScripMatch(token=f"TOK-{name}", trading_symbol=name)

    async def resolve_equity(self, symbol: str):
        if symbol == "HDFCBANK":
            return FakeScripMatch(token="TOK-HDFCBANK", trading_symbol=symbol)
        return None  # SUNPHARMA not resolvable on Angel One -> must fall back to Tapetide

    async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
        self.get_intraday_ohlc_calls.append(symbol_token)
        return _ohlc(600, base=100.0, step=0.3)


async def test_sector_and_benchmark_daily_reuse_angelone_series_no_duplicate_tapetide_call():
    tapetide = TapetideCallGuard()
    angelone = FakeAngelOneProvider()
    router = MarketDataRouter(tapetide, angelone)

    outcome = await run_full_scan(
        tapetide, DEFAULT_STRATEGY_CONFIG, stock_history_days=70,
        market_data_router=router, data_source_mode="auto", angelone_provider=angelone,
    )

    # Nifty Bank (Angel-One-covered) never hit Tapetide's get_index_ohlc.
    assert "Nifty Bank" not in tapetide.get_index_ohlc_calls
    # Nifty Healthcare (not Angel-One-covered) still had to use Tapetide.
    assert "Nifty Healthcare" in tapetide.get_index_ohlc_calls
    # NIFTY 50 benchmark also came from Angel One, not Tapetide.
    assert "Nifty 50" not in tapetide.get_index_ohlc_calls

    # HDFCBANK's daily OHLCV came from Angel One first (no Tapetide call at
    # all — the guard would have raised otherwise); SUNPHARMA fell back to
    # Tapetide only because Angel One has no equity match for it.
    assert "HDFCBANK" not in tapetide.get_stock_ohlcv_calls
    assert "SUNPHARMA" in tapetide.get_stock_ohlcv_calls

    assert outcome.data_source_summary.get("ANGEL_ONE", 0) >= 1

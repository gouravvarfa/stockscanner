from dataclasses import dataclass

import pandas as pd
import pytest

from backend.config.expiry_level_1_config import ExpiryLevel1Config
from backend.providers.market_data_router import MarketDataRouter
from backend.services.expiry_scan_service import run_expiry_level_1_scan


@dataclass
class FakeScripMatch:
    token: str
    trading_symbol: str
    exch_seg: str = "NSE"


def _bars_15m(rsi_path_closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-06-03 09:15", periods=len(rsi_path_closes), freq="15min")
    return pd.DataFrame(
        {"open": rsi_path_closes, "high": rsi_path_closes, "low": rsi_path_closes,
         "close": rsi_path_closes, "volume": [1000] * len(rsi_path_closes)},
        index=idx,
    )


def _bars_1h(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-06-03 09:00", periods=len(closes), freq="1h")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1000] * len(closes)},
        index=idx,
    )


# A close-price path engineered so RSI(14) lands inside the [58, 65] band on
# the final bar (verified: current RSI=60.0).
_SIGNAL_15M_CLOSES = [100, 102, 100, 102, 100, 102, 100, 102, 100, 102, 100, 102, 100, 102, 106]
_SIGNAL_1H_CLOSES = [100 + i for i in range(20)]  # steady uptrend -> RSI well above 65


class FakeAngelOneProvider:
    def __init__(self, fail_symbols: set[str] | None = None, no_match_symbols: set[str] | None = None):
        self.fail_symbols = fail_symbols or set()
        self.no_match_symbols = no_match_symbols or set()

    async def resolve_index(self, name: str):
        if name in self.no_match_symbols:
            return None
        return FakeScripMatch(token=f"TOK-{name}", trading_symbol=name)

    async def resolve_equity(self, symbol: str):
        if symbol in self.no_match_symbols:
            return None
        return FakeScripMatch(token=f"TOK-{symbol}", trading_symbol=symbol)

    async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
        symbol = symbol_token.replace("TOK-", "")
        if symbol in self.fail_symbols:
            raise RuntimeError(f"Simulated Angel One failure for {symbol}")
        if interval == "FIFTEEN_MINUTE":
            return _bars_15m(_SIGNAL_15M_CLOSES)
        return _bars_1h(_SIGNAL_1H_CLOSES)


class FakeTapetideProvider:
    def __init__(self, stocks: list[dict], fail_universe: bool = False):
        self._stocks = stocks
        self._fail_universe = fail_universe

    async def get_universe(self, index_slug="nifty-200"):
        if self._fail_universe:
            raise RuntimeError("Simulated Tapetide quota exhaustion")
        return {"stocks": self._stocks, "requested": len(self._stocks), "returned": len(self._stocks),
                "complete": True, "sources": [], "note": None}

    async def get_index_ohlc(self, *a, **kw): raise NotImplementedError
    async def get_stock_ohlcv(self, *a, **kw): raise NotImplementedError
    async def get_sector_performance(self, *a, **kw): raise NotImplementedError
    async def screen_technical(self, *a, **kw): raise NotImplementedError
    async def get_batch_quotes(self, *a, **kw): raise NotImplementedError


def _set_angelone_configured(monkeypatch, configured: bool, tmp_path) -> None:
    from backend.core.config import settings
    from backend.services import angelone_credential_store

    # Isolate from the real project's angelone_credentials.json (a saved
    # connection from actually using the app) by pointing the store at a
    # scratch path that doesn't exist yet.
    monkeypatch.setattr(angelone_credential_store, "CREDENTIAL_PATH", tmp_path / "angelone_credentials.json")

    value = "x" if configured else ""
    monkeypatch.setattr(settings, "angelone_api_key", value)
    monkeypatch.setattr(settings, "angelone_client_code", value)
    monkeypatch.setattr(settings, "angelone_pin", value)
    monkeypatch.setattr(settings, "angelone_totp_secret", value)


@pytest.fixture(autouse=True)
def angelone_configured(monkeypatch, tmp_path):
    _set_angelone_configured(monkeypatch, True, tmp_path)


async def test_returns_unconfigured_message_when_angelone_missing(monkeypatch, tmp_path):
    _set_angelone_configured(monkeypatch, False, tmp_path)
    tapetide = FakeTapetideProvider([])
    angelone = FakeAngelOneProvider()
    outcome = await run_expiry_level_1_scan(tapetide, MarketDataRouter(tapetide, angelone), ExpiryLevel1Config())
    assert not outcome.angelone_configured
    assert outcome.index_signals == []
    assert outcome.stock_signals == []
    assert any("not connected" in e for e in outcome.errors)


async def test_index_and_stock_signals_kept_separate():
    tapetide = FakeTapetideProvider([{"symbol": "RELIANCE", "sector": "Petroleum Products"}])
    angelone = FakeAngelOneProvider()
    outcome = await run_expiry_level_1_scan(tapetide, MarketDataRouter(tapetide, angelone), ExpiryLevel1Config())

    assert len(outcome.index_signals) == 2  # NIFTY, BANKNIFTY
    assert {s.symbol for s in outcome.index_signals} == {"NIFTY", "BANKNIFTY"}
    assert all(s.instrument_type == "INDEX" for s in outcome.index_signals)

    assert len(outcome.stock_signals) == 1
    assert outcome.stock_signals[0].symbol == "RELIANCE"
    assert outcome.stock_signals[0].instrument_type == "STOCK"
    assert outcome.stock_signals[0].sector == "Petroleum Products"


async def test_one_bad_symbol_does_not_crash_the_scan():
    tapetide = FakeTapetideProvider([
        {"symbol": "RELIANCE", "sector": "Petroleum Products"},
        {"symbol": "BADSTOCK", "sector": "Unknown"},
        {"symbol": "TCS", "sector": "Information Technology"},
    ])
    angelone = FakeAngelOneProvider(fail_symbols={"BADSTOCK"})
    outcome = await run_expiry_level_1_scan(tapetide, MarketDataRouter(tapetide, angelone), ExpiryLevel1Config())

    assert outcome.symbols_failed == 1
    assert "BADSTOCK" in outcome.failed_symbols
    # The good symbols still produced signals despite the bad one failing.
    stock_symbols = {s.symbol for s in outcome.stock_signals}
    assert "RELIANCE" in stock_symbols
    assert "TCS" in stock_symbols
    assert "BADSTOCK" not in stock_symbols


async def test_unmapped_instrument_is_isolated_not_fatal():
    tapetide = FakeTapetideProvider([{"symbol": "NOTOKEN", "sector": "Unknown"}])
    angelone = FakeAngelOneProvider(no_match_symbols={"NOTOKEN"})
    outcome = await run_expiry_level_1_scan(tapetide, MarketDataRouter(tapetide, angelone), ExpiryLevel1Config())

    assert "NOTOKEN" in outcome.failed_symbols
    assert outcome.stock_signals == []


async def test_tapetide_universe_failure_does_not_block_index_signals():
    # Index signals need only Angel One — a Tapetide outage/quota issue
    # (which only affects the stock universe lookup) must not stop NIFTY/
    # BANKNIFTY signals from coming through.
    tapetide = FakeTapetideProvider([], fail_universe=True)
    angelone = FakeAngelOneProvider()
    outcome = await run_expiry_level_1_scan(tapetide, MarketDataRouter(tapetide, angelone), ExpiryLevel1Config())

    assert len(outcome.index_signals) == 2
    assert outcome.stock_signals == []
    assert any("Stock universe unavailable" in e for e in outcome.errors)

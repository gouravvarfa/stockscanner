from dataclasses import dataclass

import pandas as pd
import pytest

from backend.config.expiry_level_5_config import ExpiryLevel5Config
from backend.providers.market_data_router import MarketDataRouter
from backend.services.expiry_level_5_scan_service import run_expiry_level_5_scan


@dataclass
class FakeScripMatch:
    token: str
    trading_symbol: str
    exch_seg: str = "NFO"


def _rally_rows():
    return [(100 + 10 * i, 100 + 10 * i + 2, 100 + 10 * i - 1, 100 + 10 * i + 1) for i in range(11)]


def _signal_df():
    idx = pd.bdate_range("2024-01-01", periods=13)
    rows = _rally_rows() + [(141, 142, 138, 140), (141, 146, 141, 145)]
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    for o, h, l, c in rows:
        data["open"].append(o)
        data["high"].append(h)
        data["low"].append(l)
        data["close"].append(c)
        data["volume"].append(1000)
    return pd.DataFrame(data, index=idx)


def _no_signal_df():
    idx = pd.bdate_range("2024-01-01", periods=11)
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    for o, h, l, c in _rally_rows():
        data["open"].append(o)
        data["high"].append(h)
        data["low"].append(l)
        data["close"].append(c)
        data["volume"].append(1000)
    return pd.DataFrame(data, index=idx)


class FakeAngelOneProvider:
    def __init__(self, signal_symbols: set[str] | None = None, fail_symbols: set[str] | None = None,
                 no_future_symbols: set[str] | None = None):
        self.signal_symbols = signal_symbols or set()
        self.fail_symbols = fail_symbols or set()
        self.no_future_symbols = no_future_symbols or set()

    async def resolve_stock_future(self, symbol: str):
        if symbol in self.no_future_symbols:
            return None
        return FakeScripMatch(token=f"TOK-{symbol}", trading_symbol=f"{symbol}FUT")

    async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
        symbol = symbol_token.replace("TOK-", "")
        if symbol in self.fail_symbols:
            raise RuntimeError(f"Simulated Angel One failure for {symbol}")
        return _signal_df() if symbol in self.signal_symbols else _no_signal_df()


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


def _isolate_credential_store(monkeypatch, tmp_path, configured: bool) -> None:
    from backend.core.config import settings
    from backend.services import angelone_credential_store

    monkeypatch.setattr(angelone_credential_store, "CREDENTIAL_PATH", tmp_path / "angelone_credentials.json")
    value = "x" if configured else ""
    monkeypatch.setattr(settings, "angelone_api_key", value)
    monkeypatch.setattr(settings, "angelone_client_code", value)
    monkeypatch.setattr(settings, "angelone_pin", value)
    monkeypatch.setattr(settings, "angelone_totp_secret", value)


@pytest.fixture(autouse=True)
def angelone_configured(monkeypatch, tmp_path):
    _isolate_credential_store(monkeypatch, tmp_path, True)


async def test_returns_unconfigured_message_when_angelone_missing(monkeypatch, tmp_path):
    _isolate_credential_store(monkeypatch, tmp_path, False)
    tapetide = FakeTapetideProvider([])
    angelone = FakeAngelOneProvider()
    outcome = await run_expiry_level_5_scan(tapetide, MarketDataRouter(tapetide, angelone), ExpiryLevel5Config())
    assert not outcome.angelone_configured
    assert outcome.signals == []


async def test_produces_signal_for_qualifying_stock():
    tapetide = FakeTapetideProvider([{"symbol": "RELIANCE", "sector": "Petroleum Products"}])
    angelone = FakeAngelOneProvider(signal_symbols={"RELIANCE"})
    outcome = await run_expiry_level_5_scan(tapetide, MarketDataRouter(tapetide, angelone), ExpiryLevel5Config())

    assert len(outcome.signals) == 1
    assert outcome.signals[0].symbol == "RELIANCE"
    assert outcome.signals[0].signal == "BUY_CE"
    assert outcome.signals[0].instrument_type == "STOCK_FUTURE"


async def test_stock_without_a_listed_future_is_skipped_not_failed():
    tapetide = FakeTapetideProvider([{"symbol": "SMALLCAP", "sector": "Unknown"}])
    angelone = FakeAngelOneProvider(no_future_symbols={"SMALLCAP"})
    outcome = await run_expiry_level_5_scan(tapetide, MarketDataRouter(tapetide, angelone), ExpiryLevel5Config())

    assert outcome.signals == []
    assert "SMALLCAP" not in outcome.failed_symbols  # no future listed isn't a scan failure


async def test_one_bad_symbol_does_not_crash_the_scan():
    tapetide = FakeTapetideProvider([
        {"symbol": "RELIANCE", "sector": "Petroleum Products"},
        {"symbol": "BADSTOCK", "sector": "Unknown"},
    ])
    angelone = FakeAngelOneProvider(signal_symbols={"RELIANCE"}, fail_symbols={"BADSTOCK"})
    outcome = await run_expiry_level_5_scan(tapetide, MarketDataRouter(tapetide, angelone), ExpiryLevel5Config())

    assert "BADSTOCK" in outcome.failed_symbols
    assert len(outcome.signals) == 1
    assert outcome.signals[0].symbol == "RELIANCE"


async def test_tapetide_failure_reported_but_not_fatal():
    tapetide = FakeTapetideProvider([], fail_universe=True)
    angelone = FakeAngelOneProvider()
    outcome = await run_expiry_level_5_scan(tapetide, MarketDataRouter(tapetide, angelone), ExpiryLevel5Config())

    assert outcome.angelone_configured
    assert outcome.signals == []
    assert any("Stock universe unavailable" in e for e in outcome.errors)

from dataclasses import dataclass

import pandas as pd
import pytest

from backend.providers.market_data_router import DataUnavailableError, MarketDataRouter


def _df(value=100.0):
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    return pd.DataFrame({"open": [value] * 5, "high": [value] * 5, "low": [value] * 5,
                          "close": [value] * 5, "volume": [1000] * 5}, index=idx)


@dataclass
class FakeMatch:
    token: str
    trading_symbol: str
    exch_seg: str = "NSE"


class FakeTapetideProvider:
    def __init__(self, fail: bool = False, value: float = 100.0):
        self.fail = fail
        self.value = value
        self.calls = 0

    async def get_stock_ohlcv(self, symbol, days=500):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Simulated Tapetide failure")
        return _df(self.value)

    async def get_universe(self, *a, **kw): raise NotImplementedError
    async def get_index_ohlc(self, *a, **kw): raise NotImplementedError
    async def get_sector_performance(self, *a, **kw): raise NotImplementedError
    async def screen_technical(self, *a, **kw): raise NotImplementedError
    async def get_batch_quotes(self, *a, **kw): raise NotImplementedError


class FakeAngelOneProvider:
    def __init__(self, fail: bool = False, no_match: bool = False, value: float = 200.0):
        self.fail = fail
        self.no_match = no_match
        self.value = value
        self.calls = 0

    async def resolve_equity(self, symbol):
        return None if self.no_match else FakeMatch(token=f"TOK-{symbol}", trading_symbol=symbol)

    async def resolve_index(self, symbol):
        return None if self.no_match else FakeMatch(token=f"TOK-{symbol}")

    async def resolve_stock_future(self, symbol):
        return None if self.no_match else FakeMatch(token=f"TOK-{symbol}", exch_seg="NFO")

    async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Simulated Angel One failure")
        return _df(self.value)


async def test_explicit_tapetide_mode_uses_tapetide():
    tapetide = FakeTapetideProvider(value=111)
    angelone = FakeAngelOneProvider(value=222)
    router = MarketDataRouter(tapetide, angelone)

    result = await router.get_candles("RELIANCE", "daily", 500, "tapetide")
    assert result.data_source == "TAPETIDE"
    assert result.selection_mode == "TAPETIDE"
    assert not result.fallback_used
    assert result.data["close"].iloc[0] == 111


async def test_explicit_tapetide_mode_never_falls_back_on_failure():
    tapetide = FakeTapetideProvider(fail=True)
    angelone = FakeAngelOneProvider()
    router = MarketDataRouter(tapetide, angelone)

    with pytest.raises(RuntimeError):
        await router.get_candles("RELIANCE", "daily", 500, "tapetide")
    assert angelone.calls == 0  # never touched


async def test_explicit_tapetide_mode_on_15m_returns_clear_unavailable():
    tapetide = FakeTapetideProvider()
    angelone = FakeAngelOneProvider()
    router = MarketDataRouter(tapetide, angelone)

    with pytest.raises(DataUnavailableError, match="not available from Tapetide"):
        await router.get_candles("NIFTY", "15m", 5, "tapetide")
    assert angelone.calls == 0


async def test_explicit_angel_one_mode_uses_angel_one():
    tapetide = FakeTapetideProvider(value=111)
    angelone = FakeAngelOneProvider(value=222)
    router = MarketDataRouter(tapetide, angelone)

    result = await router.get_candles("RELIANCE", "daily", 500, "angel_one")
    assert result.data_source == "ANGEL_ONE"
    assert not result.fallback_used
    assert result.data["close"].iloc[0] == 222
    assert tapetide.calls == 0


async def test_explicit_angel_one_mode_never_falls_back_on_failure():
    tapetide = FakeTapetideProvider(value=111)
    angelone = FakeAngelOneProvider(fail=True)
    router = MarketDataRouter(tapetide, angelone)

    with pytest.raises(RuntimeError):
        await router.get_candles("RELIANCE", "daily", 500, "angel_one")
    assert tapetide.calls == 0  # never touched


async def test_auto_uses_tapetide_when_capability_and_call_succeed():
    tapetide = FakeTapetideProvider(value=111)
    angelone = FakeAngelOneProvider(value=222)
    router = MarketDataRouter(tapetide, angelone)

    result = await router.get_candles("RELIANCE", "daily", 500, "auto")
    assert result.data_source == "TAPETIDE"
    assert result.selection_mode == "AUTO"
    assert not result.fallback_used


async def test_auto_skips_straight_to_angel_one_for_15m_capability_gap():
    tapetide = FakeTapetideProvider()
    angelone = FakeAngelOneProvider(value=222)
    router = MarketDataRouter(tapetide, angelone)

    result = await router.get_candles("NIFTY", "15m", 5, "auto")
    assert result.data_source == "ANGEL_ONE"
    assert result.fallback_used
    assert "does not provide" in result.fallback_reason
    assert tapetide.calls == 0  # never attempted — known capability gap


async def test_auto_falls_back_to_angel_one_on_tapetide_failure():
    tapetide = FakeTapetideProvider(fail=True)
    angelone = FakeAngelOneProvider(value=222)
    router = MarketDataRouter(tapetide, angelone)

    result = await router.get_candles("RELIANCE", "daily", 500, "auto")
    assert result.data_source == "ANGEL_ONE"
    assert result.fallback_used
    assert "Tapetide failed" in result.fallback_reason
    assert result.data["close"].iloc[0] == 222


async def test_auto_reports_clear_unavailable_when_both_fail():
    tapetide = FakeTapetideProvider(fail=True)
    angelone = FakeAngelOneProvider(fail=True)
    router = MarketDataRouter(tapetide, angelone)

    with pytest.raises(DataUnavailableError, match="Neither provider"):
        await router.get_candles("RELIANCE", "daily", 500, "auto")


async def test_no_data_mixing_result_comes_from_single_provider():
    tapetide = FakeTapetideProvider(fail=True)
    angelone = FakeAngelOneProvider(value=222)
    router = MarketDataRouter(tapetide, angelone)

    result = await router.get_candles("RELIANCE", "daily", 500, "auto")
    # Every value in the returned frame is from the SAME provider call.
    assert (result.data["close"] == 222).all()
    assert (result.data["open"] == 222).all()

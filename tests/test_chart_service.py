from dataclasses import dataclass

import pandas as pd
import pytest

from backend.providers.market_data_router import DataUnavailableError
from backend.services import chart_service


@dataclass
class FakeScripMatch:
    token: str
    trading_symbol: str
    exch_seg: str = "NSE"


def _bars(n: int, freq: str, base: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq=freq)
    closes = [base + i * 0.1 for i in range(n)]
    return pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000.0] * n},
        index=idx,
    )


class FakeAngelOneProvider:
    def __init__(self, bars_by_interval: dict[str, pd.DataFrame], no_match: bool = False):
        self.bars_by_interval = bars_by_interval
        self.no_match = no_match
        self.requested_intervals: list[str] = []

    async def resolve_equity(self, symbol: str):
        if self.no_match:
            return None
        return FakeScripMatch(token="TOK-1", trading_symbol=symbol)

    async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
        self.requested_intervals.append(interval)
        return self.bars_by_interval.get(interval, pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))


async def test_native_timeframe_passes_through_directly():
    provider = FakeAngelOneProvider({"FIFTEEN_MINUTE": _bars(50, "15min")})
    df = await chart_service.get_candles(provider, "RELIANCE", "15m")
    assert len(df) == 50
    assert provider.requested_intervals == ["FIFTEEN_MINUTE"]


async def test_4h_is_aggregated_from_real_one_hour_bars_not_fabricated():
    provider = FakeAngelOneProvider({"ONE_HOUR": _bars(40, "1h")})
    df = await chart_service.get_candles(provider, "RELIANCE", "4H")
    assert provider.requested_intervals == ["ONE_HOUR"]
    # Aggregated bars must be fewer than the raw hourly bars (real resampling, not 1:1).
    assert 0 < len(df) < 40


async def test_1w_is_aggregated_from_real_daily_bars():
    provider = FakeAngelOneProvider({"ONE_DAY": _bars(60, "B")})  # business days
    df = await chart_service.get_candles(provider, "RELIANCE", "1W")
    assert provider.requested_intervals == ["ONE_DAY"]
    assert 0 < len(df) < 60


async def test_unsupported_timeframe_rejected():
    provider = FakeAngelOneProvider({})
    with pytest.raises(chart_service.ChartUnsupportedTimeframeError):
        await chart_service.get_candles(provider, "RELIANCE", "2H")


async def test_unknown_symbol_raises_data_unavailable():
    provider = FakeAngelOneProvider({}, no_match=True)
    with pytest.raises(DataUnavailableError):
        await chart_service.get_candles(provider, "NOTASYMBOL", "1D")


async def test_empty_base_bars_returns_empty_without_error():
    provider = FakeAngelOneProvider({"ONE_DAY": pd.DataFrame(columns=["open", "high", "low", "close", "volume"])})
    df = await chart_service.get_candles(provider, "RELIANCE", "1M")
    assert df.empty


class FakeLongHistoryProvider:
    """Cup's fetch_cup_history() calls resolve_equity + get_daily_ohlc_range
    (never get_intraday_ohlc) — a distinct fake so long_history=True is
    proven to go through that path, not the normal short-window one."""

    def __init__(self, bars: pd.DataFrame):
        self.bars = bars
        self.range_calls = 0

    async def resolve_equity(self, symbol: str):
        return FakeScripMatch(token="TOK-1", trading_symbol=symbol)

    async def get_daily_ohlc_range(self, exch_seg, token, from_dt, to_dt):
        self.range_calls += 1
        return self.bars

    async def get_intraday_ohlc(self, *a, **kw):
        raise AssertionError("long_history=True must never call the short-window get_intraday_ohlc path")


async def test_long_history_uses_cup_chunked_fetch_not_the_short_window(monkeypatch):
    from backend.config.cup_config import DEFAULT_CUP_CONFIG
    from backend.core.cache import cache
    from backend.providers.cup_history import _cache_key

    monkeypatch.setattr(DEFAULT_CUP_CONFIG, "chunk_delay_seconds", 0.0)  # skip the real rate-limit pacing in tests
    cache.delete(_cache_key("LONGHISTTEST"))
    provider = FakeLongHistoryProvider(_bars(400, "B"))
    df = await chart_service.get_candles(provider, "LONGHISTTEST", "1M", long_history=True)
    assert provider.range_calls > 0
    assert not df.empty


async def test_long_history_ignored_for_intraday_timeframes():
    # long_history only applies to 1D/1W/1M — an intraday request must still
    # take the normal short-window path even if the flag is passed.
    provider = FakeAngelOneProvider({"FIFTEEN_MINUTE": _bars(50, "15min")})
    df = await chart_service.get_candles(provider, "RELIANCE", "15m", long_history=True)
    assert len(df) == 50

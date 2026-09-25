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


async def test_long_history_uses_cup_chunked_fetch_not_the_short_window(monkeypatch, tmp_path):
    from backend.config.cup_config import DEFAULT_CUP_CONFIG
    from backend.providers import cup_disk_cache

    monkeypatch.setattr(DEFAULT_CUP_CONFIG, "chunk_delay_seconds", 0.0)  # skip the real rate-limit pacing in tests
    monkeypatch.setattr(cup_disk_cache, "CACHE_DIR", tmp_path / "cup_history")  # isolated, never the real on-disk cache
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


# ---------------------------------------------------------------------------
# APLAPOLLO regression (2026-09-25): the 1M chart must show the CURRENT
# in-progress month as its latest candle, built from real Angel One daily
# bars (never fabricated, never hardcoded to any real stock's actual
# TradingView values) — not silently drop it and show last month instead.
# ---------------------------------------------------------------------------

def _daily_bars_spanning_into_current_month(n_prior_month_days: int, n_current_month_days: int) -> pd.DataFrame:
    """Business days ending "today" (deterministic relative to whenever the
    test runs, exactly like the real Angel One feed) so the fixture always
    genuinely spans into a real, currently in-progress month — the same
    situation APLAPOLLO was reported in for September 2026."""
    total = n_prior_month_days + n_current_month_days
    idx = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=total)
    closes = [100.0 + i * 0.5 for i in range(total)]
    return pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000.0] * total},
        index=idx,
    )


async def test_aplapollo_style_1m_chart_shows_the_current_month_as_latest_candle():
    bars = _daily_bars_spanning_into_current_month(45, 5)
    provider = FakeAngelOneProvider({"ONE_DAY": bars})
    df = await chart_service.get_candles(provider, "APLAPOLLO", "1M")
    now = pd.Timestamp.now()
    assert df.index[-1].year == now.year
    assert df.index[-1].month == now.month
    # The partial current-month candle must be built only from the real
    # current-month days actually present in the fetched daily bars.
    current_month_days = bars[(bars.index.year == now.year) & (bars.index.month == now.month)]
    latest = df.iloc[-1]
    assert latest["open"] == pytest.approx(float(current_month_days["open"].iloc[0]))
    assert latest["close"] == pytest.approx(float(current_month_days["close"].iloc[-1]))
    assert latest["high"] == pytest.approx(float(current_month_days["high"].max()))
    assert latest["low"] == pytest.approx(float(current_month_days["low"].min()))
    assert latest["volume"] == pytest.approx(float(current_month_days["volume"].sum()))


async def test_aplapollo_style_1m_previous_completed_month_still_present_before_current():
    bars = _daily_bars_spanning_into_current_month(45, 5)
    provider = FakeAngelOneProvider({"ONE_DAY": bars})
    df = await chart_service.get_candles(provider, "APLAPOLLO", "1M")
    now = pd.Timestamp.now()
    # At least one earlier, fully-completed month must still be present
    # immediately before the current live one — the fix must ADD the
    # current month, never remove history that was already there.
    assert len(df) >= 2
    prev = df.index[-2]
    assert (prev.year, prev.month) != (now.year, now.month)


async def test_aplapollo_style_1m_live_rsi_and_bollinger_source_includes_current_month():
    """The chart's RSI/Bollinger Bands are computed client-side FROM this
    exact candle series (frontend/src/chart/chartStudies.ts) — proving the
    current month is the last row here is sufficient to prove live RSI/BB
    will include it too, without duplicating the RSI/BB implementation in
    this backend test."""
    bars = _daily_bars_spanning_into_current_month(45, 5)
    provider = FakeAngelOneProvider({"ONE_DAY": bars})
    df = await chart_service.get_candles(provider, "APLAPOLLO", "1M")
    now = pd.Timestamp.now()
    assert (df.index[-1].year, df.index[-1].month) == (now.year, now.month)

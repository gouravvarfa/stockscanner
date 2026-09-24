import datetime as dt

import pandas as pd
import pytest

from backend.providers.angelone_scrip_master import FutureContract
from backend.services import futures_instrument_service, top_bottom_backtest_service
from backend.services.top_bottom_backtest_service import (
    InsufficientDataError,
    TopBottomValidationError,
    run_futures_backtest,
)


def _ohlc(n, base=100.0, step=0.5, start="2025-01-01"):
    idx = pd.bdate_range(start, periods=n)
    closes = [base + step * i for i in range(n)]
    return pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000] * n},
        index=idx,
    )


class FakeAngelOneProvider:
    def __init__(self, df: pd.DataFrame | None = None, raise_error: Exception | None = None):
        self._df = df if df is not None else _ohlc(60)
        self._raise = raise_error

    async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
        if self._raise:
            raise self._raise
        return self._df

    async def get_daily_ohlc_range(self, exch_seg, symbol_token, from_dt, to_dt):
        if self._raise:
            raise self._raise
        return self._df


_RELIANCE_FUT = FutureContract(
    underlying="RELIANCE", trading_symbol="RELIANCE29SEP26FUT", token="68777",
    exch_seg="NFO", expiry="2026-09-29", is_index=False, lot_size=500,
)


@pytest.fixture(autouse=True)
def fake_contract_resolution(monkeypatch):
    async def fake_resolve(underlying, expiry):
        if underlying.upper() != "RELIANCE":
            raise futures_instrument_service.NotAFutureError(
                f"'{underlying}' has no live NSE futures contract. Top-Bottom strategy is available only for Futures."
            )
        return _RELIANCE_FUT

    monkeypatch.setattr(futures_instrument_service, "resolve_contract", fake_resolve)


async def test_unsupported_instrument_type_is_rejected():
    # Only EQUITY (NSE cash) and FUTURES (NFO) are valid segments — anything
    # else (options, commodity, a typo) must fail loudly, never fall through
    # to some default segment.
    provider = FakeAngelOneProvider()
    with pytest.raises(TopBottomValidationError, match="Unsupported instrument_type"):
        await run_futures_backtest(
            provider, "RELIANCE", "OPTIDX", "1D",
            dt.datetime(2025, 1, 1), dt.datetime(2025, 3, 1),
        )


async def test_symbol_with_no_live_future_is_rejected():
    provider = FakeAngelOneProvider()
    with pytest.raises(TopBottomValidationError, match="Top-Bottom strategy is available only for Futures"):
        await run_futures_backtest(
            provider, "NOTAFUTURESSYMBOL", "FUTURES", "1D",
            dt.datetime(2025, 1, 1), dt.datetime(2025, 3, 1),
        )


async def test_date_range_filters_to_only_requested_window():
    df = _ohlc(60, start="2025-01-01")
    provider = FakeAngelOneProvider(df)

    from_date = pd.Timestamp("2025-01-10").to_pydatetime()
    to_date = pd.Timestamp("2025-01-20").to_pydatetime()
    result = await run_futures_backtest(provider, "RELIANCE", "FUTURES", "1D", from_date, to_date)

    # coverage reports the FULL fetched range (for honest "data available"
    # messaging) even though the engine itself only runs on the clipped
    # window — every signal/trade must fall strictly inside it.
    for s in result.signals:
        assert from_date <= s.signal_date <= to_date
    for t in result.trades:
        assert from_date <= t.entry_date <= to_date


class FakeChunkTrackingProvider:
    """Tracks whether the single-call or chunked-date-range path was used —
    proves a pre-2022-style from_date actually triggers chunking instead of
    silently getting the same truncated single call as before."""

    def __init__(self, df: pd.DataFrame):
        self._df = df
        self.single_call_days: list[int] = []
        self.range_calls: list[tuple[dt.datetime, dt.datetime]] = []

    async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
        self.single_call_days.append(days_back)
        return self._df

    async def get_daily_ohlc_range(self, exch_seg, symbol_token, from_dt, to_dt):
        self.range_calls.append((from_dt, to_dt))
        return self._df


async def test_backtest_before_the_old_lookback_window_uses_chunked_fetch(monkeypatch):
    """2026-09-24, explicit user direction: a from_date older than the
    previous fixed ~4.1y (1500-day) single-call lookback must still run a
    full backtest, via the same chunked fetch Cup Breakout's history uses —
    not silently clipped to whatever a single call happens to return."""
    from backend.config.cup_config import DEFAULT_CUP_CONFIG

    monkeypatch.setattr(DEFAULT_CUP_CONFIG, "chunk_delay_seconds", 0.0)  # skip real rate-limit pacing in tests
    old_start = dt.datetime.now() - dt.timedelta(days=2000)  # well before the old 1500-day window
    df = _ohlc(30, start=old_start.strftime("%Y-%m-%d"))
    provider = FakeChunkTrackingProvider(df)

    from_date = old_start
    to_date = old_start + dt.timedelta(days=40)
    result = await run_futures_backtest(provider, "RELIANCE", "FUTURES", "1D", from_date, to_date)

    assert provider.range_calls, "expected the chunked date-range path, not a single get_intraday_ohlc call"
    assert not provider.single_call_days
    assert result is not None


async def test_recent_backtest_still_uses_a_single_call_not_chunked():
    """The default/common case (from_date within the old ~4.1y window) must
    NOT start chunking — that would add unnecessary delay to every ordinary
    request, not just the genuinely-old ones this feature is for."""
    df = _ohlc(60)
    provider = FakeChunkTrackingProvider(df)
    from_date = pd.Timestamp("2025-01-10").to_pydatetime()
    to_date = pd.Timestamp("2025-01-20").to_pydatetime()

    await run_futures_backtest(provider, "RELIANCE", "FUTURES", "1D", from_date, to_date)

    assert provider.single_call_days
    assert not provider.range_calls


async def test_insufficient_historical_data_raises_clear_error_not_fabricated_result():
    provider = FakeAngelOneProvider(pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))
    with pytest.raises(InsufficientDataError, match="unavailable"):
        await run_futures_backtest(
            provider, "RELIANCE", "FUTURES", "1D",
            dt.datetime(2025, 1, 1), dt.datetime(2025, 3, 1),
        )


async def test_date_range_entirely_outside_available_data_raises_insufficient_data():
    df = _ohlc(60, start="2025-01-01")
    provider = FakeAngelOneProvider(df)
    with pytest.raises(InsufficientDataError, match="Insufficient historical data"):
        await run_futures_backtest(
            provider, "RELIANCE", "FUTURES", "1D",
            dt.datetime(2030, 1, 1), dt.datetime(2030, 3, 1),
        )


async def test_one_bad_symbol_data_error_is_reported_cleanly_not_a_crash():
    provider = FakeAngelOneProvider(raise_error=RuntimeError("Angel One returned a non-JSON response (HTTP 403)."))
    with pytest.raises(RuntimeError, match="403"):
        await run_futures_backtest(
            provider, "RELIANCE", "FUTURES", "1D",
            dt.datetime(2025, 1, 1), dt.datetime(2025, 3, 1),
        )
    # The service itself didn't crash the process / raise an unrelated
    # exception type — the API layer (backend/api/top_bottom.py) converts
    # this into a clean HTTP 502, verified separately in test_api.py.


async def test_result_is_retrievable_after_backtest_completes():
    provider = FakeAngelOneProvider(_ohlc(60))
    result = await run_futures_backtest(
        provider, "RELIANCE", "FUTURES", "1D",
        dt.datetime(2025, 1, 1), dt.datetime(2025, 3, 1),
    )
    fetched = top_bottom_backtest_service.get_result(result.backtest_id)
    assert fetched is not None
    assert fetched.backtest_id == result.backtest_id


async def test_unknown_backtest_id_returns_none_not_an_exception():
    assert top_bottom_backtest_service.get_result("does-not-exist") is None


async def test_no_position_carries_in_from_before_the_requested_from_date():
    """
    Regression for a real user report: a BUY opened well before from_date
    (using data the provider happens to also return before the window) must
    NOT appear as an "already open" position inside the reported result —
    the backtest starts FLAT exactly at from_date. A structure point that
    forms while flat (like TATASTEEL's 12-Jan Top in the user's example)
    must be evaluated fresh, using only bars at/after from_date.
    """
    # A clean up/down/up wiggle BEFORE the window that would, under the old
    # warm-up-context behavior, already have opened and be holding a BUY
    # by the time the window starts.
    pre_window = [100.0, 80.0, 90.0, 85.0, 95.0, 110.0, 100.0, 120.0]
    in_window = [90.0, 80.0, 85.0, 70.0, 79.0, 65.0, 70.0, 55.0, 62.0, 45.0, 55.0, 63.0]
    idx = pd.bdate_range("2025-01-01", periods=len(pre_window) + len(in_window))
    closes = pre_window + in_window
    df = pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000] * len(closes)},
        index=idx,
    )
    provider = FakeAngelOneProvider(df)

    from_date = idx[len(pre_window)].to_pydatetime()  # window starts exactly where in_window begins
    to_date = idx[-1].to_pydatetime()

    result = await run_futures_backtest(provider, "RELIANCE", "FUTURES", "1D", from_date, to_date)

    # No trade's entry_date is before from_date — nothing carried in.
    for t in result.trades:
        assert t.entry_date >= from_date

    # coverage still honestly reports the FULL data the provider had
    # (for "insufficient data" messaging), even though the engine itself
    # only used the clipped window.
    assert result.coverage.available_from < from_date
    assert result.coverage.requested_from == from_date

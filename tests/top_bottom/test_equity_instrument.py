"""
Phase-1 scope: NSE EQUITY (ADANIGREEN). Verifies the equity path resolves
through the existing cash scrip-master lookup, uses lot size 1 (per share),
and that the result carries the full price series the chart needs.
"""
import datetime as dt

import pandas as pd
import pytest

from backend.providers import angelone_scrip_master as scrip_master
from backend.providers.angelone_scrip_master import ScripMatch
from backend.services.top_bottom_backtest_service import (
    TopBottomValidationError,
    run_futures_backtest,
)


def _ohlc(n, start="2025-01-01"):
    idx = pd.bdate_range(start, periods=n)
    closes = [100.0 + (i % 7) * 3 - (i % 5) * 2 for i in range(n)]
    return pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000] * n},
        index=idx,
    )


class FakeAngelOneProvider:
    def __init__(self, df):
        self._df = df

    async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
        self.last_exch_seg = exch_seg
        return self._df

    async def get_daily_ohlc_range(self, exch_seg, symbol_token, from_dt, to_dt):
        self.last_exch_seg = exch_seg
        return self._df


@pytest.fixture(autouse=True)
def fake_equity_resolution(monkeypatch):
    async def fake_resolve_equity(symbol):
        if symbol != "ADANIGREEN":
            return None
        return ScripMatch(token="3563", trading_symbol="ADANIGREEN-EQ", exch_seg="NSE")

    monkeypatch.setattr(scrip_master, "resolve_equity", fake_resolve_equity)


async def test_adanigreen_equity_backtest_runs_on_nse_cash():
    provider = FakeAngelOneProvider(_ohlc(90))
    result = await run_futures_backtest(
        provider, "ADANIGREEN", "EQUITY", "1D",
        dt.datetime(2025, 1, 1), dt.datetime(2025, 5, 1),
    )

    assert result.symbol == "ADANIGREEN"
    assert result.trading_symbol == "ADANIGREEN-EQ"
    assert result.exch_seg == "NSE"
    assert result.expiry == ""  # cash equity has no expiry
    assert provider.last_exch_seg == "NSE"


async def test_equity_uses_lot_size_one_so_pnl_is_per_share():
    provider = FakeAngelOneProvider(_ohlc(90))
    result = await run_futures_backtest(
        provider, "ADANIGREEN", "EQUITY", "1D",
        dt.datetime(2025, 1, 1), dt.datetime(2025, 5, 1),
    )
    assert result.trades, "expected the oscillating series to produce trades"
    for t in result.trades:
        assert t.lot_size == 1
        assert t.pnl_amount == t.pnl_points


async def test_symbol_outside_the_a_group_universe_is_rejected():
    # The equity side is restricted to the A Group list — an unknown (or
    # simply non-A-Group) symbol must fail loudly, never be substituted.
    provider = FakeAngelOneProvider(_ohlc(90))
    with pytest.raises(TopBottomValidationError, match="not in the A Group stock list"):
        await run_futures_backtest(
            provider, "NOSUCHSTOCK", "EQUITY", "1D",
            dt.datetime(2025, 1, 1), dt.datetime(2025, 5, 1),
        )


async def test_result_carries_the_full_price_series_for_the_chart():
    provider = FakeAngelOneProvider(_ohlc(90))
    from_date = dt.datetime(2025, 1, 1)
    to_date = dt.datetime(2025, 5, 1)
    result = await run_futures_backtest(provider, "ADANIGREEN", "EQUITY", "1D", from_date, to_date)

    # The chart must get every bar in the window — not just the handful of
    # bars a trade happened to touch.
    assert len(result.price_series) > len(result.trades) * 2
    for p in result.price_series:
        assert from_date <= p.date <= to_date


async def test_result_carries_system_point_and_stop_loss_lines():
    provider = FakeAngelOneProvider(_ohlc(90))
    result = await run_futures_backtest(
        provider, "ADANIGREEN", "EQUITY", "1D",
        dt.datetime(2025, 1, 1), dt.datetime(2025, 5, 1),
    )
    assert result.system_point_line, "GREEN System Point line must be provided"
    assert result.stop_loss_line, "RED Stop Loss line must be provided"


def test_equity_search_returns_only_a_group_symbols():
    from backend.services import equity_instrument_service, universe_loader

    universe = set(universe_loader.load_a_group_universe())
    results = equity_instrument_service.search_equities("ADANI")

    assert results, "expected ADANI* matches in the A Group list"
    assert all(s in universe for s in results)
    assert "ADANIGREEN" in results


def test_equity_search_ranks_prefix_matches_first():
    from backend.services import equity_instrument_service

    results = equity_instrument_service.search_equities("TATA")
    prefix = [s for s in results if s.startswith("TATA")]
    assert results[: len(prefix)] == prefix


def test_equity_search_is_empty_for_blank_query():
    from backend.services import equity_instrument_service

    assert equity_instrument_service.search_equities("   ") == []

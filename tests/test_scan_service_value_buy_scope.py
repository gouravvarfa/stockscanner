from dataclasses import dataclass

import pandas as pd

from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
from backend.services import universe_loader
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


class FakeAngelOneProvider:
    """
    Every symbol resolves and returns a 70-bar series, RSI-neutral enough
    that Strategy One/GFS/etc typically won't qualify but Value Buy might
    depending on the caller's override — tests set up specific series per
    symbol via `series_by_symbol` when a particular outcome is needed.
    """

    def __init__(self, series_by_symbol: dict[str, pd.DataFrame] | None = None, fail_symbols: set[str] | None = None):
        self.series_by_symbol = series_by_symbol or {}
        self.fail_symbols = fail_symbols or set()
        self.fetch_calls: dict[str, int] = {}

    async def resolve_equity(self, symbol: str):
        return FakeScripMatch(token=f"TOK-{symbol}", trading_symbol=symbol)

    async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
        symbol = symbol_token.replace("TOK-", "")
        self.fetch_calls[symbol] = self.fetch_calls.get(symbol, 0) + 1
        if symbol in self.fail_symbols:
            raise RuntimeError(f"Simulated Angel One failure for {symbol}")
        return self.series_by_symbol.get(symbol, _ohlc(70, base=100.0, step=0.1))


def _set_universe(monkeypatch, symbols: list[str]) -> None:
    """All six strategies now share the single BSE A Group universe."""
    monkeypatch.setattr(universe_loader, "load_a_group_universe", lambda: list(symbols))


async def test_all_strategies_run_over_the_a_group_universe(monkeypatch):
    _set_universe(monkeypatch, ["AAA", "BBB"])
    provider = FakeAngelOneProvider()

    outcome = await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    assert {r.symbol for r in outcome.all_results} == {"AAA", "BBB"}


async def test_value_buy_shares_the_same_universe_as_the_other_strategies(monkeypatch):
    # Value Buy used to have its own, larger NIFTY 500 universe. It now runs
    # over the same A Group list, so no symbol is scanned for Value Buy that
    # the other five strategies did not also see.
    _set_universe(monkeypatch, ["AAA", "BBB"])
    provider = FakeAngelOneProvider()

    await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    assert set(provider.fetch_calls) == {"AAA", "BBB"}


async def test_each_symbol_is_fetched_from_angelone_only_once(monkeypatch):
    # The Value Buy pass must be served from the cache populated by the main
    # pass — re-fetching would double every scan's Angel One call count.
    _set_universe(monkeypatch, ["AAA", "BBB", "CCC"])
    provider = FakeAngelOneProvider()

    await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    assert provider.fetch_calls == {"AAA": 1, "BBB": 1, "CCC": 1}


async def test_master_universe_matches_the_a_group_excel_exactly(monkeypatch):
    _set_universe(monkeypatch, ["AAA", "BBB", "CCC"])
    provider = FakeAngelOneProvider()

    outcome = await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    assert {e.symbol for e in outcome.nifty200_universe} == {"AAA", "BBB", "CCC"}
    assert outcome.universe_requested == 3
    assert outcome.universe_returned == 3
    assert outcome.universe_complete is True
    assert outcome.value_buy_universe_requested == 3
    assert outcome.value_buy_universe_returned == 3
    assert outcome.stocks_scanned == 3


async def test_unavailable_stock_is_kept_in_universe_with_status(monkeypatch):
    _set_universe(monkeypatch, ["GOODSTOCK", "BADSTOCK"])
    provider = FakeAngelOneProvider(fail_symbols={"BADSTOCK"})

    outcome = await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    universe_by_symbol = {e.symbol: e for e in outcome.nifty200_universe}
    assert set(universe_by_symbol) == {"GOODSTOCK", "BADSTOCK"}

    bad = universe_by_symbol["BADSTOCK"]
    assert bad.status == "DATA_UNAVAILABLE"
    assert bad.status_reason
    assert bad.current_price is None
    assert bad.daily_rsi is None

    good = universe_by_symbol["GOODSTOCK"]
    assert good.status == "OK"
    assert good.current_price is not None
    assert good.data_source == "ANGEL_ONE"


async def test_a_failed_symbol_is_only_counted_once_despite_two_passes(monkeypatch):
    # Both passes walk the same list now, so a broken symbol must not be
    # reported as two separate failures.
    _set_universe(monkeypatch, ["GOODSTOCK", "BADSTOCK"])
    provider = FakeAngelOneProvider(fail_symbols={"BADSTOCK"})

    outcome = await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    assert outcome.failed_symbols == ["BADSTOCK"]
    assert outcome.stocks_failed == 1


async def test_no_fake_stocks_are_added_beyond_the_excel_list(monkeypatch):
    _set_universe(monkeypatch, ["ONLYONE"])
    provider = FakeAngelOneProvider()

    outcome = await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    assert len(outcome.nifty200_universe) == 1
    assert outcome.nifty200_universe[0].symbol == "ONLYONE"


async def test_on_progress_callback_fires_once_per_symbol(monkeypatch):
    _set_universe(monkeypatch, ["GOODSTOCK", "BADSTOCK"])
    provider = FakeAngelOneProvider(fail_symbols={"BADSTOCK"})

    calls: list[tuple[str, bool, str | None]] = []
    await run_full_scan(
        provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70,
        on_progress=lambda symbol, success, error: calls.append((symbol, success, error)),
    )

    assert len(calls) == 2
    by_symbol = {c[0]: c for c in calls}
    assert by_symbol["GOODSTOCK"][1] is True
    assert by_symbol["GOODSTOCK"][2] is None
    assert by_symbol["BADSTOCK"][1] is False
    assert by_symbol["BADSTOCK"][2] is not None


async def test_on_progress_is_optional_and_backward_compatible(monkeypatch):
    # No on_progress passed at all — must behave exactly as before.
    _set_universe(monkeypatch, ["ONLYONE"])
    provider = FakeAngelOneProvider()
    outcome = await run_full_scan(provider, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)
    assert outcome.stocks_scanned == 1

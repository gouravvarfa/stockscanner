import gc
import weakref

import pandas as pd
import pytest

from backend.config.cup_config import CupConfig
from backend.providers import cup_disk_cache
from backend.services import universe_loader
from backend.services.cup_scan_service import run_cup_scan


class FakeMatch:
    exch_seg = "NSE"
    token = "TOK"


def _flat_daily_series(n_months: int, price: float) -> pd.DataFrame:
    """One daily bar per month (month-end) + a trailing stub, matching
    tests/test_cup.py's _monthly_frame helper, so to_monthly() sees exactly
    `n_months` completed flat months — flat/short enough to never qualify
    as a Cup (used for the "doesn't qualify" / NO_SIGNAL-style filler)."""
    idx = pd.bdate_range("2020-01-01", periods=n_months, freq="BME")
    df = pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 1000.0}, index=idx)
    stub = pd.DataFrame(
        {"open": price, "high": price, "low": price, "close": price, "volume": 0.0},
        index=[idx[-1] + pd.Timedelta(days=5)],
    )
    return pd.concat([df, stub])


def _cup_daily_series() -> pd.DataFrame:
    """A clean, valid, qualifying cup: rim 1000 -> low 600 -> recovery to 950
    (NEAR_BREAKOUT), built the same way tests/test_cup.py does."""
    rows = []
    y, m = 2015, 1
    def add(price):
        nonlocal y, m
        d = pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)
        rows.append((d, price, price, price, price, 1000.0))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    for _ in range(3):
        add(400.0)
    add(1000.0)
    for i in range(36):
        add(1000.0 - (400.0 / 36) * (i + 1))
    for i in range(36):
        add(600.0 + (350.0 / 36) * (i + 1))
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
    stub = pd.DataFrame(
        {"open": 950.0, "high": 950.0, "low": 950.0, "close": 950.0, "volume": 0.0},
        index=[df.index.max() + pd.Timedelta(days=5)],
    )
    return pd.concat([df, stub])


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    # Every test gets its own throwaway on-disk Cup cache — never touches
    # the real .cache/cup_history/ the running app uses.
    monkeypatch.setattr(cup_disk_cache, "CACHE_DIR", tmp_path / "cup_history")
    yield


def _patched_provider(monthly_series_by_symbol, fail_symbols=None):
    """Angel One's real fetch always resolves ONE symbol per call in this
    scan (no cross-symbol interleaving inside a single get_daily_ohlc_range
    call), so a provider that tracks "current symbol" via resolve_equity
    (called first, per stock) is sufficient to route each fetch correctly."""
    provider = type("FakeCupProvider", (), {"calls": {}})()

    async def resolve_equity(symbol: str):
        provider._current_symbol = symbol
        if symbol not in monthly_series_by_symbol and symbol not in (fail_symbols or set()):
            return None
        return FakeMatch()

    async def get_daily_ohlc_range(exch_seg, token, from_dt, to_dt):
        symbol = provider._current_symbol
        provider.calls[symbol] = provider.calls.get(symbol, 0) + 1
        if symbol in (fail_symbols or set()):
            raise RuntimeError(f"Simulated Angel One failure for {symbol}")
        return monthly_series_by_symbol.get(symbol, pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))

    provider.resolve_equity = resolve_equity
    provider.get_daily_ohlc_range = get_daily_ohlc_range
    return provider


def _set_universe(monkeypatch, symbols):
    monkeypatch.setattr(universe_loader, "load_a_group_universe", lambda: list(symbols))


CONFIG = CupConfig(history_years=2, chunk_years=2, chunk_delay_seconds=0)


async def test_qualifying_stock_appears_in_results_others_dont(monkeypatch):
    _set_universe(monkeypatch, ["AAA", "CUPQUALIFIES"])
    provider = _patched_provider({
        "AAA": _flat_daily_series(20, 100.0),
        "CUPQUALIFIES": _cup_daily_series(),
    })
    outcome = await run_cup_scan(provider, CONFIG, max_concurrent_fetches=2)
    symbols_with_results = {r["symbol"] for r in outcome.results}
    assert symbols_with_results == {"CUPQUALIFIES"}
    assert outcome.stocks_scanned == 2
    assert outcome.stocks_failed == 0


async def test_one_stock_failure_does_not_stop_the_scan(monkeypatch):
    _set_universe(monkeypatch, ["AAA", "FAILSYM", "CUPQUALIFIES"])
    provider = _patched_provider(
        {"AAA": _flat_daily_series(20, 100.0), "CUPQUALIFIES": _cup_daily_series()},
        fail_symbols={"FAILSYM"},
    )
    outcome = await run_cup_scan(provider, CONFIG, max_concurrent_fetches=2)
    assert outcome.stocks_failed == 1
    assert "FAILSYM" in outcome.failed_symbols
    assert outcome.stocks_scanned == 2  # AAA + CUPQUALIFIES still processed
    assert {r["symbol"] for r in outcome.results} == {"CUPQUALIFIES"}


async def test_progress_and_result_callbacks_fire_progressively(monkeypatch):
    _set_universe(monkeypatch, ["AAA", "CUPQUALIFIES"])
    provider = _patched_provider({"AAA": _flat_daily_series(20, 100.0), "CUPQUALIFIES": _cup_daily_series()})
    progressed = []
    resulted = []
    await run_cup_scan(
        provider, CONFIG, max_concurrent_fetches=2,
        on_progress=lambda symbol, ok, err: progressed.append((symbol, ok)),
        on_result=lambda symbol, qualifying: resulted.append((symbol, [n for n, _ in qualifying])),
    )
    assert set(progressed) == {("AAA", True), ("CUPQUALIFIES", True)}
    assert ("CUPQUALIFIES", ["CUP"]) in resulted
    assert ("AAA", []) in resulted  # reported (progress), but not qualifying


async def test_instrument_type_is_attached_via_existing_classifier(monkeypatch):
    _set_universe(monkeypatch, ["CUPQUALIFIES"])
    provider = _patched_provider({"CUPQUALIFIES": _cup_daily_series()})
    outcome = await run_cup_scan(provider, CONFIG, max_concurrent_fetches=1)
    assert outcome.results[0]["instrument_type"] in ("FUTURE", "EQUITY")


async def test_cache_writes_are_per_symbol_not_one_giant_store(monkeypatch):
    """2026-09-24 memory fix: scanning N stocks must produce N separate
    on-disk cache files (backend/providers/cup_disk_cache.py), never one
    shared/growing store the way the old shared FileCache did."""
    symbols = [f"SYM{i}" for i in range(10)]
    _set_universe(monkeypatch, symbols)
    provider = _patched_provider({s: _flat_daily_series(20, 100.0 + i) for i, s in enumerate(symbols)})
    await run_cup_scan(provider, CONFIG, max_concurrent_fetches=3)

    files = list(cup_disk_cache.CACHE_DIR.glob("*.pkl"))
    assert len(files) == len(symbols)
    for sym in symbols:
        assert cup_disk_cache.load(sym) is not None


async def test_raw_daily_dataframes_are_not_retained_after_each_stock_finishes(monkeypatch):
    """Memory requirement (2026-09-24): 'Stock A: fetch/load -> analyze ->
    release memory' — not all 615 histories held at once. Patches
    fetch_cup_history directly (below cup_history's own chunking/caching)
    so each symbol's raw DataFrame identity can be tracked via a weakref;
    once run_cup_scan finishes, none of those per-stock raw DataFrames may
    still be referenced anywhere (cup_scan_service only ever keeps the
    tiny `cup_result` dict, never the DataFrame itself)."""
    import backend.services.cup_scan_service as cup_scan_service_module

    symbols = [f"MEMSYM{i}" for i in range(8)]
    _set_universe(monkeypatch, symbols)
    live_refs: list[weakref.ReferenceType] = []

    async def fake_fetch_cup_history(angelone, symbol, config):
        df = _flat_daily_series(20, 100.0)  # a fresh object every call, not a shared/reused one
        live_refs.append(weakref.ref(df))
        return df

    monkeypatch.setattr(cup_scan_service_module, "fetch_cup_history", fake_fetch_cup_history)

    provider = _patched_provider({})  # unused — fetch_cup_history is patched directly above
    await run_cup_scan(provider, CONFIG, max_concurrent_fetches=3)

    assert len(live_refs) == len(symbols)
    gc.collect()
    still_alive = [i for i, ref in enumerate(live_refs) if ref() is not None]
    assert still_alive == [], f"{len(still_alive)}/{len(symbols)} raw daily DataFrames were still referenced after the scan"

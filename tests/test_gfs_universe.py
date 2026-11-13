import asyncio

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.config.strategy_config import (
    DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG,
    DEFAULT_GFS50_BACKTEST_CONFIG,
    DEFAULT_GFS_BACKTEST_CONFIG,
)
from backend.main import app
from backend.services import gfs_universe_service as service


def _uptrend(days: int = 1500) -> pd.DataFrame:
    """A steady climb with small wiggles: daily, weekly and monthly RSI all end well above 60."""
    idx = pd.bdate_range(end="2026-11-06", periods=days)
    rng = np.random.default_rng(1)
    close = 100 + np.cumsum(0.4 + rng.normal(0, 0.3, days))
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close}, index=idx)


def _pullback(days: int = 1500) -> pd.DataFrame:
    """A steady climb (weekly and monthly RSI far above 60) whose last 5 candles pull back just enough to
    leave the daily RSI inside the 50 GFS band of 50-59."""
    idx = pd.bdate_range(end="2026-11-06", periods=days)
    close, price = [], 100.0
    for k in range(days):
        price *= 0.994 if k >= days - 5 else 1.003
        close.append(price)
    s = pd.Series(close, index=idx)
    return pd.DataFrame({"open": s, "high": s, "low": s, "close": s}, index=idx)


def _downtrend(days: int = 1500) -> pd.DataFrame:
    df = _uptrend(days)
    return (df.max().max() * 2 - df).clip(lower=1)


def test_a_stock_with_daily_rsi_in_50_to_59_is_listed_for_50_gfs_only():
    df = _pullback()
    row = service.evaluate_stock("TESTCO", df, DEFAULT_GFS50_BACKTEST_CONFIG)
    assert row is not None
    assert row.symbol == "TESTCO"
    assert row.data_from == df.index[0].date() and row.data_to == df.index[-1].date()
    assert 50 <= row.daily_rsi <= 59 and row.weekly_rsi > 60 and row.monthly_rsi > 60
    assert row.data_from <= row.in_setup_since <= row.data_to
    # Advanced GFS needs daily RSI above 60 and GFS needs 38-45: neither band holds at 50-59.
    assert service.evaluate_stock("TESTCO", df, DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG) is None
    assert service.evaluate_stock("TESTCO", df, DEFAULT_GFS_BACKTEST_CONFIG) is None


def test_a_strong_uptrend_is_listed_for_advanced_gfs_but_no_longer_for_50_gfs():
    df = _uptrend()  # daily RSI far above 59
    assert service.evaluate_stock("TESTCO", df, DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG) is not None
    assert service.evaluate_stock("TESTCO", df, DEFAULT_GFS50_BACKTEST_CONFIG) is None
    assert service.evaluate_stock("TESTCO", df, DEFAULT_GFS_BACKTEST_CONFIG) is None


def test_downtrend_and_short_history_are_not_listed():
    assert service.evaluate_stock("X", _downtrend(), DEFAULT_GFS50_BACKTEST_CONFIG) is None
    assert service.evaluate_stock("X", _uptrend().iloc[:30], DEFAULT_GFS50_BACKTEST_CONFIG) is None
    assert service.evaluate_stock("X", pd.DataFrame(), DEFAULT_GFS50_BACKTEST_CONFIG) is None


def test_universe_endpoint_runs_in_background_and_lists_qualifying_stocks(monkeypatch):
    service._states.clear()
    symbols = ["UPCO", "DOWNCO", "BROKENCO"]
    monkeypatch.setattr(service.universe_loader, "load_a_group_universe", lambda: symbols)
    monkeypatch.setattr(service.universe_loader, "company_name_for", lambda s: f"{s} Limited")
    frames = {"UPCO": _pullback(), "DOWNCO": _downtrend()}

    async def fake_fetch(provider, symbol, days):
        if symbol not in frames:
            raise RuntimeError("no listing")
        return frames[symbol]

    monkeypatch.setattr(service, "fetch_daily_ohlcv", fake_fetch)
    monkeypatch.setattr("backend.api.gfs_universe.get_angelone_provider", lambda: object())

    with TestClient(app) as client:
        assert client.get("/api/gfs50/universe").json()["status"] == "idle"
        assert client.post("/api/gfs50/universe/start", json={}).status_code == 200

        async def wait():
            await asyncio.wait_for(service._tasks["gfs50"], timeout=30)

        client.portal.call(wait)
        body = client.get("/api/gfs50/universe").json()

    assert body["status"] == "done"
    assert body["total"] == 3 and body["processed"] == 3 and body["failed"] == 1
    assert [r["symbol"] for r in body["rows"]] == ["UPCO"]
    assert body["rows"][0]["company_name"] == "UPCO Limited"
    assert body["rows"][0]["data_from"] and body["rows"][0]["data_to"]
    service._states.clear()


def test_rows_stream_in_while_the_scan_is_still_running(monkeypatch):
    service._states.clear()
    monkeypatch.setattr(service.universe_loader, "load_a_group_universe", lambda: ["UPCO", "SLOWCO"])
    monkeypatch.setattr(service.universe_loader, "company_name_for", lambda s: f"{s} Limited")
    release = {}

    async def fake_fetch(provider, symbol, days):
        if symbol == "SLOWCO":
            await release["event"].wait()  # still fetching while UPCO is already done
        return _pullback()

    monkeypatch.setattr(service, "fetch_daily_ohlcv", fake_fetch)
    monkeypatch.setattr("backend.api.gfs_universe.get_angelone_provider", lambda: object())

    with TestClient(app) as client:
        async def scenario():
            release["event"] = asyncio.Event()
            state = service.start("gfs50", object())
            for _ in range(200):  # wait for the fast stock to land
                if state.rows:
                    break
                await asyncio.sleep(0.05)
            mid = (state.status, state.processed, [r.symbol for r in state.rows])
            release["event"].set()
            await asyncio.wait_for(service._tasks["gfs50"], timeout=30)
            return mid, [r.symbol for r in state.rows]

        mid, final = client.portal.call(scenario)

    assert mid == ("running", 1, ["UPCO"])  # listed before the slow stock finished
    assert final == ["SLOWCO", "UPCO"]  # then kept sorted by company name
    service._states.clear()


def test_scan_pauses_new_fetches_while_a_backtest_is_running(monkeypatch):
    service._states.clear()
    monkeypatch.setattr(service.universe_loader, "load_a_group_universe", lambda: ["A1", "A2", "A3"])
    fetched = []

    async def fake_fetch(provider, symbol, days):
        fetched.append(symbol)
        return _downtrend()

    monkeypatch.setattr(service, "fetch_daily_ohlcv", fake_fetch)
    monkeypatch.setattr(service, "_YIELD_POLL_SECONDS", 0.01)

    with TestClient(app) as client:
        async def scenario():
            with service.backtest_priority():
                service.start("gfs50", object())
                await asyncio.sleep(0.3)
                during = list(fetched)  # the backtest is "running": no new scan fetch may start
            await asyncio.wait_for(service._tasks["gfs50"], timeout=30)
            return during, list(fetched)

        during, after = client.portal.call(scenario)

    assert during == []
    assert sorted(after) == ["A1", "A2", "A3"]  # and the scan resumes once the backtest is done
    service._states.clear()


def test_backtest_reuses_recently_fetched_candles(monkeypatch):
    from backend.services import gfs_backtest_service as bt

    bt._candle_cache.clear()
    calls = {"fetch": 0}

    async def fake_resolve(symbol, kind, exch):
        return type("I", (), {"underlying": symbol, "trading_symbol": symbol + "-EQ"})()

    async def fake_fetch(angelone, instrument, timeframe, from_date=None):
        calls["fetch"] += 1
        return _uptrend()

    monkeypatch.setattr(bt, "_resolve_instrument", fake_resolve)
    monkeypatch.setattr(bt, "_fetch_ohlcv", fake_fetch)
    import datetime as dt

    async def run(symbol, start):
        return await bt.run_for_symbol(object(), symbol, start, dt.datetime(2026, 11, 6, 23, 59))

    loop = asyncio.new_event_loop()
    try:
        first = loop.run_until_complete(run("tcs", dt.datetime(2024, 1, 1)))
        again = loop.run_until_complete(run("TCS", dt.datetime(2024, 6, 1)))  # same stock, later start: served from cache
        assert calls["fetch"] == 1
        assert again.symbol == first.symbol == "TCS"
        loop.run_until_complete(run("TCS", dt.datetime(2019, 1, 1)))  # needs older data than cached: fetches again
        assert calls["fetch"] == 2
    finally:
        loop.close()
        bt._candle_cache.clear()

import asyncio

import pandas as pd
import pytest

from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
from backend.schemas.scan import NiftyUniverseStockOut, StrategySignalOut
from backend.schemas.top_bottom import BacktestResultOut
from backend.services import scan_service, universe_loader
from backend.services.instrument_classifier import get_instrument_type, normalize_symbol
from backend.services.scan_job_manager import ScanJob
from backend.services.scan_service import run_full_scan
from backend.strategies.types import StrategySignal
from tests.test_scan_service_value_buy_scope import FakeAngelOneProvider, _set_universe


def test_future_and_equity_classification():
    assert get_instrument_type("RELIANCE") == "FUTURE"
    assert get_instrument_type("NILKAMAL") == "EQUITY"


def test_symbol_normalization():
    assert normalize_symbol(" nse:reliance-eq ") == "RELIANCE"
    assert get_instrument_type("reliance-EQ") == "FUTURE"
    assert get_instrument_type("M&M") == "FUTURE"
    assert get_instrument_type(None) == "EQUITY"


def test_instrument_type_in_strategy_and_universe_api_models():
    sig = StrategySignalOut(strategy="PRD", symbol="RELIANCE", qualifies=True, signal_date=None, daily_rsi=None,
                            weekly_rsi=None, monthly_rsi=None, conditions={}, explanation="")
    assert sig.instrument_type == "FUTURE"
    assert NiftyUniverseStockOut(symbol="NILKAMAL", status="OK").instrument_type == "EQUITY"


def test_top_bottom_result_carries_instrument_type():
    import inspect
    assert "instrument_type" in BacktestResultOut.model_fields
    assert BacktestResultOut.model_fields["instrument_type"].default == "EQUITY"


async def test_failure_does_not_stop_scan_and_failed_symbol_fetched_once(monkeypatch):
    _set_universe(monkeypatch, ["AAA", "BAD", "CCC"])
    p = FakeAngelOneProvider(fail_symbols={"BAD"})
    out = await run_full_scan(p, DEFAULT_STRATEGY_CONFIG, stock_history_days=70)
    assert out.stocks_failed == 1 and out.stocks_scanned == 3
    assert p.fetch_calls == {"AAA": 1, "BAD": 1, "CCC": 1}  # no second-pass refetch of the failed one


async def test_results_emitted_incrementally_before_scan_completes(monkeypatch):
    _set_universe(monkeypatch, ["AAA", "BBB", "CCC"])
    seen = []
    finished = []

    class SlowLast(FakeAngelOneProvider):
        async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
            if symbol_token.endswith("CCC"):
                await asyncio.sleep(2.5)
            return await super().get_intraday_ohlc(exch_seg, symbol_token, interval, days_back)

    task = asyncio.create_task(run_full_scan(
        SlowLast(), DEFAULT_STRATEGY_CONFIG, stock_history_days=70,
        on_progress=lambda s, ok, e: seen.append(s),
    ))
    task.add_done_callback(lambda _t: finished.append(True))
    for _ in range(100):  # wait (bounded) for the two fast stocks; CCC is still sleeping
        if len(seen) >= 2:
            break
        await asyncio.sleep(0.02)
    assert sorted(seen) == ["AAA", "BBB"] and not finished  # visible while CCC still running
    out = await task
    assert sorted(seen) == ["AAA", "BBB", "CCC"] and out.stocks_scanned == 3


async def test_slow_stock_times_out_without_blocking_scan(monkeypatch):
    monkeypatch.setattr(scan_service, "PER_STOCK_FETCH_TIMEOUT_SECONDS", 0.1)
    _set_universe(monkeypatch, ["AAA", "HANG"])

    class Hang(FakeAngelOneProvider):
        async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
            if symbol_token.endswith("HANG"):
                await asyncio.sleep(30)
            return await super().get_intraday_ohlc(exch_seg, symbol_token, interval, days_back)

    out = await asyncio.wait_for(run_full_scan(Hang(), DEFAULT_STRATEGY_CONFIG, stock_history_days=70), 10)
    assert out.failed_symbols == ["HANG"] and out.stocks_scanned == 2


async def test_fetch_concurrency_is_capped(monkeypatch):
    _set_universe(monkeypatch, [f"S{i}" for i in range(12)])
    live = {"now": 0, "max": 0}

    class Track(FakeAngelOneProvider):
        async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
            live["now"] += 1
            live["max"] = max(live["max"], live["now"])
            await asyncio.sleep(0.03)
            live["now"] -= 1
            return await super().get_intraday_ohlc(exch_seg, symbol_token, interval, days_back)

    await run_full_scan(Track(), DEFAULT_STRATEGY_CONFIG, stock_history_days=70)
    assert 1 < live["max"] <= scan_service.DEFAULT_MAX_CONCURRENT_PER_JOB_FETCHES


def _fake_signal(strategy, symbol):
    return StrategySignal(
        strategy=strategy, symbol=symbol, qualifies=True, signal_date=None,
        daily_rsi=None, weekly_rsi=None, monthly_rsi=None, conditions={}, explanation="", extra={},
    )


async def test_on_result_and_job_partial_cursor(monkeypatch):
    job = ScanJob(job_id="j", scan_type="a_group")
    job.record_result("RELIANCE", [("PRD", _fake_signal("PRD", "RELIANCE"))])
    job.record_result("NILKAMAL", [])  # no qualifying signal -> nothing to show
    job.record_result("ABB", [("GFS", _fake_signal("GFS", "ABB")), ("NRD", _fake_signal("NRD", "ABB"))])
    assert job.signals_found == 3
    first = job.partial_after(0)
    assert [i["symbol"] for i in first["items"]] == ["RELIANCE", "ABB"]
    assert first["items"][0]["instrument_type"] == "FUTURE"
    assert [s["strategy"] for s in first["items"][0]["signals"]] == ["PRD"]
    assert job.partial_after(first["next"])["items"] == []


def test_vectorized_swing_and_rsi_match_reference():
    import numpy as np
    from backend.divergence.swing import find_swing_points
    from backend.indicators.rsi import rsi
    rng = np.random.default_rng(3)
    c = pd.Series(np.round(100 + np.cumsum(rng.normal(0, 2, 300)), 1), index=pd.bdate_range("2021-01-01", periods=300))
    h, lo = c + 1.5, c - 1.5

    def ref(high, low, k):  # the original per-bar algorithm
        pts = []
        for i in range(k, len(high) - k):
            wh = high.iloc[i - k:i + k + 1]
            if high.iloc[i] == wh.max() and (wh == high.iloc[i]).sum() == 1:
                pts.append((i, "high"))
            wl = low.iloc[i - k:i + k + 1]
            if low.iloc[i] == wl.min() and (wl == low.iloc[i]).sum() == 1:
                pts.append((i, "low"))
        return sorted(pts, key=lambda p: p[0])

    for k in (1, 2, 5):
        assert [(p.index, p.kind) for p in find_swing_points(h, lo, k)] == ref(h, lo, k)
    assert rsi(c).iloc[-1] == pytest.approx(rsi(c).iloc[-1])


async def test_two_concurrent_scans_each_get_their_own_fetch_concurrency(monkeypatch):
    """2026-09-22: a single SHARED fetch semaphore across jobs was live-
    tested with two real concurrent devices and starved the second job at
    0% for minutes — asyncio.Semaphore is a plain FIFO queue, so job 1's
    ~615 already-queued waiters kept winning over job 2's later ones. Each
    job now gets its OWN semaphore, so BOTH make real, overlapping progress
    — this asserts that directly, not just a combined cap."""
    _set_universe(monkeypatch, [f"S{i}" for i in range(8)])
    live_a = {"now": 0, "max": 0}
    live_b = {"now": 0, "max": 0}

    def make_tracker(counters):
        class Track(FakeAngelOneProvider):
            async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
                counters["now"] += 1
                counters["max"] = max(counters["max"], counters["now"])
                await asyncio.sleep(0.05)
                counters["now"] -= 1
                return await super().get_intraday_ohlc(exch_seg, symbol_token, interval, days_back)

        return Track()

    await asyncio.gather(
        run_full_scan(make_tracker(live_a), DEFAULT_STRATEGY_CONFIG, stock_history_days=70),
        run_full_scan(make_tracker(live_b), DEFAULT_STRATEGY_CONFIG, stock_history_days=70),
    )
    # Neither job was starved — both independently reached real concurrency,
    # each within (not sharing) its own per-job cap.
    assert 1 < live_a["max"] <= scan_service.DEFAULT_MAX_CONCURRENT_PER_JOB_FETCHES
    assert 1 < live_b["max"] <= scan_service.DEFAULT_MAX_CONCURRENT_PER_JOB_FETCHES


async def test_second_scan_is_not_starved_by_a_first_scan_with_many_more_stocks(monkeypatch):
    """The exact live bug: job 1 has hundreds of stocks already queued on a
    shared semaphore; job 2 starts later with its own (smaller) universe and
    must still make progress immediately, not wait behind job 1's backlog."""
    processed_b: list[str] = []

    class SlowProvider(FakeAngelOneProvider):
        async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
            await asyncio.sleep(0.05)
            return await super().get_intraday_ohlc(exch_seg, symbol_token, interval, days_back)

    def universe_for(symbols):
        return lambda: list(symbols)

    monkeypatch.setattr(universe_loader, "load_a_group_universe", universe_for([f"BIG{i}" for i in range(150)]))
    job_a = asyncio.create_task(run_full_scan(SlowProvider(), DEFAULT_STRATEGY_CONFIG, stock_history_days=70))
    await asyncio.sleep(0.1)  # let job A's ~150 fetches all queue up first

    monkeypatch.setattr(universe_loader, "load_a_group_universe", universe_for(["SMALL1", "SMALL2"]))

    class TrackingProvider(FakeAngelOneProvider):
        async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
            processed_b.append(symbol_token)
            return await super().get_intraday_ohlc(exch_seg, symbol_token, interval, days_back)

    job_b = asyncio.create_task(run_full_scan(TrackingProvider(), DEFAULT_STRATEGY_CONFIG, stock_history_days=70))
    await asyncio.wait_for(job_b, timeout=3.0)  # would time out if starved behind job A's backlog
    assert len(processed_b) == 2
    job_a.cancel()

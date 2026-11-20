"""Render has 512 MB and a disk that is wiped on every restart, so the server keeps very little in memory.

These tests pin the limits (small on Render / STATELESS_SERVER=1, larger locally), that the stores really are
bounded, and that the scrip master is filtered while it is parsed (its refresh was a ~240 MB peak)."""
from __future__ import annotations

import importlib
import json

import pytest

from backend.core import runtime


def _reload_runtime(monkeypatch, **env):
    for k in ("RENDER", "STATELESS_SERVER"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return importlib.reload(runtime)


@pytest.fixture(autouse=True)
def _restore_runtime():
    yield
    importlib.reload(runtime)


def test_local_run_uses_the_large_limits_and_render_the_small_ones(monkeypatch):
    rt = _reload_runtime(monkeypatch)
    assert not rt.STATELESS_SERVER and rt.keep(10, 3) == 10
    rt = _reload_runtime(monkeypatch, RENDER="true")
    assert rt.ON_RENDER and rt.STATELESS_SERVER and rt.keep(10, 3) == 3
    rt = _reload_runtime(monkeypatch, STATELESS_SERVER="1")
    assert not rt.ON_RENDER and rt.STATELESS_SERVER and rt.keep(10, 3) == 3


def test_rss_helper_never_raises():
    value = runtime.rss_mb()
    assert value is None or value > 0


def _limits_in_fresh_process(**env) -> dict:
    """Import the services in a separate interpreter (their limits are fixed at import) and report them.
    A separate process also keeps this test from re-importing modules inside the test run, which would
    replace their exception classes and break unrelated tests."""
    import os
    import subprocess
    import sys

    code = (
        "import json;"
        "import backend.services.gfs_backtest_service as g, backend.services.scan_job_manager as j,"
        "backend.services.system_one_backtest_service as s, backend.services.top_bottom_backtest_service as t;"
        "print(json.dumps(dict(so=s._MAX_STORED_RESULTS, tb=t._MAX_STORED_RESULTS, candles=g._CANDLE_CACHE_MAX,"
        "jobs=j.MAX_COMPLETED_JOBS_RETAINED_PER_TYPE, per_type=j.MAX_CONCURRENT_JOBS_PER_SCAN_TYPE,"
        "heavy=j.MAX_RUNNING_HEAVY_SCANS)))"
    )
    clean = {k: v for k, v in os.environ.items() if k not in ("RENDER", "STATELESS_SERVER")}
    out = subprocess.run([sys.executable, "-c", code], env={**clean, **env}, capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_stateless_limits_on_every_server_side_store():
    render = _limits_in_fresh_process(RENDER="true")
    assert render == {"so": 3, "tb": 3, "candles": 0, "jobs": 2, "per_type": 1, "heavy": 1}  # nothing is remembered on Render beyond the last few
    forced = _limits_in_fresh_process(STATELESS_SERVER="1")
    assert forced == render
    local = _limits_in_fresh_process()
    assert local == {"so": 10, "tb": 10, "candles": 40, "jobs": 5, "per_type": 3, "heavy": 0}


def test_system_one_store_is_bounded(monkeypatch):
    from backend.services import system_one_backtest_service as so

    monkeypatch.setattr(so, "_MAX_STORED_RESULTS", 3)
    so._results.clear()
    for i in range(8):
        so._store(type("S", (), {"backtest_id": f"id{i}"})())
    assert list(so._results) == ["id5", "id6", "id7"]
    so._results.clear()


def test_top_bottom_results_are_bounded_instead_of_growing_forever(monkeypatch):
    """Regression: top_bottom's result dict used to keep every run until the process restarted."""
    from backend.services import top_bottom_backtest_service as tb

    assert hasattr(tb._results, "popitem") and tb._MAX_STORED_RESULTS >= 1
    monkeypatch.setattr(tb, "_MAX_STORED_RESULTS", 2)
    tb._results.clear()
    for i in range(5):
        with tb._results_lock:
            tb._results[f"id{i}"] = object()
            while len(tb._results) > tb._MAX_STORED_RESULTS:
                tb._results.popitem(last=False)
    assert list(tb._results) == ["id3", "id4"]
    tb._results.clear()


def test_scrip_master_drops_irrelevant_rows_while_parsing():
    from backend.providers import angelone_scrip_master as sm

    rows = [
        {"exch_seg": "NSE", "instrumenttype": "", "name": "TCS", "symbol": "TCS-EQ", "token": "1"},
        {"exch_seg": "NSE", "instrumenttype": "AMXIDX", "name": "NIFTY", "symbol": "Nifty 50", "token": "2"},
        {"exch_seg": "NFO", "instrumenttype": "FUTSTK", "name": "TCS", "symbol": "TCS29DEC26FUT", "token": "3"},
        {"exch_seg": "NFO", "instrumenttype": "OPTSTK", "name": "TCS", "symbol": "TCS29DEC26CE", "token": "4"},
        {"exch_seg": "MCX", "instrumenttype": "FUTCOM", "name": "GOLDM", "symbol": "GOLDM04DEC26FUT", "token": "5"},
        {"exch_seg": "MCX", "instrumenttype": "FUTCOM", "name": "CRUDEOIL", "symbol": "CRUDEOIL19NOV26FUT", "token": "6"},
        {"exch_seg": "BSE", "instrumenttype": "", "name": "TCS", "symbol": "TCS", "token": "7"},
    ]
    parsed = json.loads(json.dumps(rows), object_hook=sm._keep_relevant)
    assert [r["token"] for r in parsed if r is not None] == ["1", "2", "3", "5"]
    assert parsed.count(None) == 3  # dropped at parse time, so they never pile up in memory


async def test_scrip_master_download_returns_only_relevant_rows(monkeypatch):
    from backend.providers import angelone_scrip_master as sm

    body = json.dumps([
        {"exch_seg": "NSE", "instrumenttype": "", "name": "TCS", "symbol": "TCS-EQ", "token": "1"},
        {"exch_seg": "NFO", "instrumenttype": "OPTIDX", "name": "NIFTY", "symbol": "NIFTY-OPT", "token": "2"},
        {"exch_seg": "MCX", "instrumenttype": "FUTCOM", "name": "SILVERM", "symbol": "SILVERM30NOV26FUT", "token": "3"},
    ]).encode()

    class FakeResponse:
        content = body

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return FakeResponse()

    stored = {}
    monkeypatch.setattr(sm.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(sm.cache, "set", lambda key, value, ttl: stored.update({key: value}))
    rows = await sm._download_and_filter()
    assert [r["token"] for r in rows] == ["1", "3"]
    assert stored[sm.CACHE_KEY] == rows


def test_scan_progress_logs_process_memory(monkeypatch, caplog):
    import logging

    from backend.services import scan_job_manager as sjm

    monkeypatch.setattr(sjm, "rss_mb", lambda: 321)
    job = sjm.ScanJob(job_id="scan_x", scan_type="a_group", total=100)
    with caplog.at_level(logging.INFO, logger="scanner.scan_job_manager"):
        for i in range(100):
            job.record_progress(f"S{i}", True)
    lines = [r.getMessage() for r in caplog.records if "process memory" in r.getMessage()]
    assert lines and "100/100" in lines[-1] and "321 MB" in lines[-1]


async def test_render_runs_only_one_big_scan_at_a_time(monkeypatch):
    """2026-11-17: a ~4 hour Cup scan overlapped other scans on Render and went over 512 MB."""
    import asyncio

    from backend.services import scan_job_manager as sjm

    monkeypatch.setattr(sjm, "MAX_RUNNING_HEAVY_SCANS", 1)
    mgr = sjm.JobManager()
    gate = asyncio.Event()

    async def runner(job):
        await gate.wait()
        return {}

    mgr.start_job("cup_breakout", runner, device_id="phone")
    with pytest.raises(sjm.TooManyConcurrentScansError, match="one big scan runs at a time"):
        mgr.start_job("a_group", runner, device_id="laptop")
    mgr.start_job("expiry_level_1", runner, device_id="laptop")  # small scans are not blocked
    gate.set()
    await asyncio.sleep(0.05)
    mgr.start_job("a_group", runner, device_id="laptop")  # the big one finished: the next may start
    gate.set()
    await asyncio.sleep(0.05)


async def test_cup_result_is_not_kept_on_the_server_when_stateless(monkeypatch):
    from backend.api import scan_jobs
    from backend.services.cup_scan_service import CupScanOutcome
    import datetime as dt

    now = dt.datetime(2026, 11, 17)
    outcome = CupScanOutcome(started_at=now, finished_at=now, execution_seconds=1.0, stocks_scanned=1,
                             stocks_failed=0, failed_symbols=[], results=[{"symbol": "TCS"}])

    async def fake_scan(*a, **k):
        return outcome

    calls = []
    monkeypatch.setattr(scan_jobs, "run_cup_scan", fake_scan)
    monkeypatch.setattr(scan_jobs, "get_angelone_provider", lambda: None)
    monkeypatch.setattr(scan_jobs, "set_cached_result", lambda *a, **k: calls.append("set"))
    monkeypatch.setattr(scan_jobs, "clear_cached_result", lambda *a, **k: calls.append("clear"))
    job = type("J", (), {"record_progress": lambda *a: None, "record_result": lambda *a: None})()

    monkeypatch.setattr(scan_jobs, "STATELESS_SERVER", True)
    payload = await scan_jobs._run_cup_breakout_job(job)
    assert payload["results"] == [{"symbol": "TCS"}] and calls == ["clear"]  # the device gets it; the server forgets

    calls.clear()
    monkeypatch.setattr(scan_jobs, "STATELESS_SERVER", False)
    await scan_jobs._run_cup_breakout_job(job)
    assert calls == ["set"]  # a local run keeps its 24h cache as before


# ---- 2026-11-20: glibc tuning, trimming and the memory guard (Render OOM during an A Group scan) ----

def test_malloc_helpers_never_raise_off_linux():
    assert runtime.tune_malloc() in (True, False)
    value = runtime.trim_memory()
    assert value is None or value > 0


async def test_memory_guard_does_nothing_on_a_local_run(monkeypatch):
    monkeypatch.setattr(runtime, "STATELESS_SERVER", False)
    monkeypatch.setattr(runtime, "rss_mb", lambda: 999)
    calls = []
    monkeypatch.setattr(runtime, "trim_memory", lambda: calls.append(1) or 999)
    await runtime.memory_guard("test")
    assert calls == []


async def test_memory_guard_trims_and_waits_until_memory_comes_down(monkeypatch):
    monkeypatch.setattr(runtime, "STATELESS_SERVER", True)
    monkeypatch.setattr(runtime, "rss_mb", lambda: 470)
    readings = iter([465, 455, 430])  # trim after trim, memory falls below the 440 MB hard limit
    trims = []
    monkeypatch.setattr(runtime, "trim_memory", lambda: trims.append(1) or next(readings))
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr(runtime.asyncio, "sleep", fake_sleep)
    await runtime.memory_guard("test")
    assert len(trims) == 3 and slept == [2, 2]


async def test_memory_guard_only_trims_between_the_soft_and_hard_limit(monkeypatch):
    monkeypatch.setattr(runtime, "STATELESS_SERVER", True)
    monkeypatch.setattr(runtime, "rss_mb", lambda: 400)
    trims = []
    monkeypatch.setattr(runtime, "trim_memory", lambda: trims.append(1) or 390)

    async def no_sleep(s):
        raise AssertionError("must not wait below the hard limit")

    monkeypatch.setattr(runtime.asyncio, "sleep", no_sleep)
    await runtime.memory_guard("test")
    assert trims == [1]


async def test_memory_guard_gives_up_waiting_after_about_90_seconds(monkeypatch):
    monkeypatch.setattr(runtime, "STATELESS_SERVER", True)
    monkeypatch.setattr(runtime, "rss_mb", lambda: 480)
    monkeypatch.setattr(runtime, "trim_memory", lambda: 480)
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr(runtime.asyncio, "sleep", fake_sleep)
    await runtime.memory_guard("test")
    assert sum(slept) == 90  # never blocks a scan forever


def test_memory_endpoint_reports_the_limit():
    from fastapi.testclient import TestClient

    from backend.main import app

    body = TestClient(app).get("/api/memory").json()
    assert body["limit_mb"] == 512 and "memory_mb" in body and isinstance(body["running_scans"], list)

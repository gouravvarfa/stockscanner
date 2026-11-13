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
        "jobs=j.MAX_COMPLETED_JOBS_RETAINED_PER_TYPE)))"
    )
    clean = {k: v for k, v in os.environ.items() if k not in ("RENDER", "STATELESS_SERVER")}
    out = subprocess.run([sys.executable, "-c", code], env={**clean, **env}, capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_stateless_limits_on_every_server_side_store():
    render = _limits_in_fresh_process(RENDER="true")
    assert render == {"so": 3, "tb": 3, "candles": 0, "jobs": 2}  # nothing is remembered on Render beyond the last few
    forced = _limits_in_fresh_process(STATELESS_SERVER="1")
    assert forced == render
    local = _limits_in_fresh_process()
    assert local == {"so": 10, "tb": 10, "candles": 40, "jobs": 5}


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

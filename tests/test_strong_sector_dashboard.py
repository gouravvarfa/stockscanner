"""Dashboard = the stocks of today's STRONG sectors only; Value Buy = its own scan over the whole A Group (2026-11-22)."""
from __future__ import annotations

import datetime as dt
import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import backend.api.scan_jobs as scan_jobs_module
from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
from backend.main import app
from backend.services import angelone_credential_store, scan_service
from backend.services import sector_strength_service as svc
from backend.services.scan_job_manager import clear_cached_result, job_manager, set_cached_result
from backend.services.scan_service import run_full_scan
from tests.test_scan_service_value_buy_scope import FakeAngelOneProvider, _set_universe


def trend(n: int, first: float, daily_pct: float) -> pd.DataFrame:
    idx = pd.bdate_range("2021-01-01", periods=n)
    v = np.array([first * (1 + daily_pct / 100) ** i for i in range(n)])
    return pd.DataFrame({"open": v, "high": v * 1.01, "low": v * 0.99, "close": v, "volume": 0.0}, index=idx)


UP, DOWN = trend(1300, 100, 0.12), trend(1300, 500, -0.08)


class IndexProvider:
    def __init__(self):
        self.calls = 0

    async def get_daily_ohlc_range(self, exch, token, start, end):
        self.calls += 1
        return UP if token == "IDX_UP" else DOWN


@pytest.fixture()
def two_sectors(monkeypatch):
    async def resolve_index(name):
        return svc.scrip_master.ScripMatch(token={"UP": "IDX_UP", "DOWN": "IDX_DOWN"}[name], trading_symbol=name, exch_seg="NSE")

    async def constituents():
        return {"up": [{"symbol": "AAA"}, {"symbol": "AAB"}], "down": [{"symbol": "ZZZ"}]}, "test"

    monkeypatch.setattr(svc, "SECTORS", [{"key": "up", "label": "Up", "index": "UP"}, {"key": "down", "label": "Down", "index": "DOWN"},
                                         {"key": "ew", "label": "Equal", "index": None}])
    monkeypatch.setattr(svc, "load_constituents", constituents)
    monkeypatch.setattr(svc.scrip_master, "resolve_index", resolve_index)
    monkeypatch.setattr(svc, "REQUEST_PAUSE_S", 0)
    monkeypatch.setattr(svc, "_drop_unfinished_today", lambda df: df)
    svc._universe_cache.clear()
    svc._results.clear()
    yield
    svc._universe_cache.clear()
    svc._results.clear()


async def test_strong_sector_universe_is_the_strong_sectors_and_their_stocks(two_sectors):
    p = IndexProvider()
    as_of = UP.index[-1].date()
    out = await svc.strong_sector_universe(p, as_of)
    assert [s["label"] for s in out["sectors"]] == ["Up"] and out["symbols"] == ["AAA", "AAB"]
    assert all(v > 60 for v in out["sectors"][0]["rsi"].values())
    assert p.calls == 2  # only the sector indices; the equal-weight sector has none
    await svc.strong_sector_universe(p, as_of)
    assert p.calls == 2  # kept for 30 minutes


async def test_strong_sector_universe_reuses_a_weekly_report_of_the_same_day(two_sectors):
    as_of = dt.date(2026, 11, 20)
    svc._results[as_of.isoformat()] = (dt.datetime.now(), {"sectors": [
        {"key": "up", "rsi": {"d": 70, "w": 65, "m": 62}, "equal_weight": False},
        {"key": "down", "rsi": {"d": 70, "w": 65, "m": 55}, "equal_weight": False}]})
    p = IndexProvider()
    out = await svc.strong_sector_universe(p, as_of)
    assert p.calls == 0 and out["symbols"] == ["AAA", "AAB"]


async def test_dashboard_scan_runs_only_the_given_stocks_and_no_value_buy(monkeypatch):
    _set_universe(monkeypatch, ["AAA", "BBB", "CCC"])
    flags = []
    real = scan_service._evaluate_all_strategies
    monkeypatch.setattr(scan_service, "_evaluate_all_strategies", lambda r, o, m, vb: flags.append(vb) or real(r, o, m, vb))
    p = FakeAngelOneProvider()
    out = await run_full_scan(p, DEFAULT_STRATEGY_CONFIG, stock_history_days=70, symbols=["AAA", "CCC"], value_buy_symbols=[])
    assert set(p.fetch_calls) == {"AAA", "CCC"} and flags == [False, False]
    assert out.universe_requested == 2 and out.strategy_signals["Value Buy"] == []


async def test_value_buy_scan_checks_only_value_buy_once_per_stock_with_progress(monkeypatch):
    called = []
    monkeypatch.setattr(scan_service, "_evaluate_all_strategies", lambda *a: called.append(1) or [])
    progress = []
    p = FakeAngelOneProvider(fail_symbols={"BAD"})
    out = await run_full_scan(p, DEFAULT_STRATEGY_CONFIG, stock_history_days=70, symbols=[], value_buy_symbols=["AAA", "BAD", "CCC"],
                              on_progress=lambda s, ok, e: progress.append((s, ok)))
    assert called == []  # the other setups are not evaluated
    assert sorted(progress) == [("AAA", True), ("BAD", False), ("CCC", True)]
    assert p.fetch_calls == {"AAA": 1, "BAD": 1, "CCC": 1}
    assert out.stocks_scanned == 3 and out.stocks_failed == 1


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(angelone_credential_store, "CREDENTIAL_PATH", tmp_path / "angelone_credentials.json")
    for t in ("a_group", "value_buy"):
        clear_cached_result(t)
    job_manager._jobs.clear()
    with TestClient(app) as c:
        yield c
    for t in ("a_group", "value_buy"):
        clear_cached_result(t)
    job_manager._jobs.clear()


def _wait(client, job_id, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/scan/jobs/{job_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise TimeoutError(job_id)


def test_dashboard_job_scans_the_strong_sector_stocks_and_says_which_sectors(client, monkeypatch):
    async def universe(provider, as_of=None):
        return {"as_of": "2026-11-20", "symbols": ["AAA", "BBB"], "constituents_source": "test",
                "sectors": [{"key": "up", "label": "Up", "index": "UP", "rsi": {"d": 70, "w": 66, "m": 61}, "members": ["AAA", "BBB"]}]}

    monkeypatch.setattr(svc, "strong_sector_universe", universe)
    monkeypatch.setattr(scan_jobs_module, "get_angelone_provider", lambda: FakeAngelOneProvider())
    _set_universe(monkeypatch, ["AAA", "BBB", "CCC", "DDD"])
    started = client.post("/api/scan/fresh", json={"scan_type": "a_group"}).json()
    final = _wait(client, started["job"]["job_id"])
    assert final["status"] == "completed" and final["total"] == 2 and final["processed"] == 2
    result = client.get(f"/api/scan/jobs/{final['job_id']}/results").json()
    assert result["universe_requested"] == 2
    assert result["strong_sectors"] == [{"key": "up", "label": "Up", "index": "UP", "rsi": {"d": 70, "w": 66, "m": 61}, "stocks": 2}]


def test_an_old_whole_a_group_result_is_never_served_from_the_cache(client, monkeypatch):
    set_cached_result("a_group", {"universe_requested": 615})
    assert client.get("/api/scan/cache/a_group").status_code == 404
    set_cached_result("a_group", {"universe_requested": 2, "strong_sectors": []})
    assert client.get("/api/scan/cache/a_group").status_code == 200
    assert client.post("/api/scan/start", json={"scan_type": "a_group"}).json()["status"] == "cached"


def test_value_buy_job_runs_over_every_nse_stock_with_the_strong_sector_map(client, monkeypatch):
    seen = {}

    async def fake_scan(provider, config, **kw):
        seen.update(kw)
        return await run_full_scan(FakeAngelOneProvider(), config, stock_history_days=70, **{k: kw[k] for k in ("symbols", "value_buy_symbols", "on_progress", "on_result")})

    monkeypatch.setattr(scan_jobs_module, "run_full_scan", fake_scan)
    monkeypatch.setattr(scan_jobs_module, "get_angelone_provider", lambda: FakeAngelOneProvider())
    monkeypatch.setattr(scan_jobs_module, "load_a_group_universe", lambda: ["AAA", "BBB", "CCC"])
    # Value Buy now runs over every NSE equity and carries today's strong-sector map (2026-11-23)
    from backend.services import universe_loader
    monkeypatch.setattr(universe_loader, "load_all_nse_universe", lambda: ["AAA", "BBB", "CCC"])

    async def fake_strong(provider, as_of=None):
        return {"sectors": [{"key": "it", "label": "IT", "rsi": {}, "members": ["BBB"]}], "symbols": ["BBB"]}

    monkeypatch.setattr(scan_jobs_module.sector_strength_service, "strong_sector_universe", fake_strong)
    started = client.post("/api/scan/fresh", json={"scan_type": "value_buy"}).json()
    assert started["job"]["scan_type"] == "value_buy"
    final = _wait(client, started["job"]["job_id"])
    assert final["status"] == "completed" and final["total"] == 3 and final["processed"] == 3
    assert seen["symbols"] == [] and seen["value_buy_symbols"] == ["AAA", "BBB", "CCC"]
    cached = client.get("/api/scan/cache/value_buy")
    assert cached.status_code == 200
    assert cached.json()["result"]["strong_symbols"] == {"BBB": "IT"}


async def test_a_stock_refused_by_the_rate_limit_is_tried_again(monkeypatch):
    monkeypatch.setattr(scan_service, "RATE_LIMIT_RETRY_BASE_S", 0)

    class Limited(FakeAngelOneProvider):
        async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
            sym = symbol_token.replace("TOK-", "")
            if sym == "KOTAK" and self.fetch_calls.get(sym, 0) < 2:
                self.fetch_calls[sym] = self.fetch_calls.get(sym, 0) + 1
                raise RuntimeError("Angel One returned a non-JSON response (HTTP 403).")
            return await super().get_intraday_ohlc(exch_seg, symbol_token, interval, days_back)

    p = Limited(fail_symbols={"BAD"})
    out = await run_full_scan(p, DEFAULT_STRATEGY_CONFIG, stock_history_days=70, symbols=["KOTAK", "BAD"], value_buy_symbols=[])
    assert p.fetch_calls == {"KOTAK": 3, "BAD": 1}  # two 403s then data; any other failure is not retried
    assert out.failed_symbols == ["BAD"]

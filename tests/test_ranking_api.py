import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import angelone_credential_store
from backend.services.scan_job_manager import clear_cached_result, set_cached_result


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(angelone_credential_store, "CREDENTIAL_PATH", tmp_path / "angelone_credentials.json")
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_cache():
    clear_cached_result("a_group")
    yield
    clear_cached_result("a_group")


def _fake_scan_result():
    return {
        "strategies": {
            "Strategy One": [
                {
                    "strategy": "Strategy One", "symbol": "RELIANCE", "qualifies": True,
                    "signal_date": "2026-01-01T00:00:00", "daily_rsi": 55.0, "weekly_rsi": 60.0,
                    "monthly_rsi": 65.0, "conditions": {}, "explanation": "", "extra": {"score": 91.0},
                },
            ],
            "GFS": [
                {
                    "strategy": "GFS", "symbol": "TCS", "qualifies": True,
                    "signal_date": "2026-01-01T00:00:00", "daily_rsi": 41.5, "weekly_rsi": 80.0,
                    "monthly_rsi": 80.0, "conditions": {}, "explanation": "", "extra": {},
                },
            ],
            "PRD": [], "NRD": [], "Advanced GFS": [], "Value Buy": [],
        }
    }


def test_ranking_endpoints_404_without_a_cached_scan(client):
    assert client.get("/api/ranking/latest").status_code == 404
    assert client.get("/api/ranking/top").status_code == 404
    assert client.get("/api/ranking/strategy/Strategy One").status_code == 404


def test_ranking_latest_never_triggers_a_new_scan(client, monkeypatch):
    # If /latest tried to run a scan, it would need Angel One/universe
    # access that isn't set up in this test — so any such attempt would
    # raise, and the endpoint would fail instead of returning cleanly.
    set_cached_result("a_group", _fake_scan_result())

    resp = client.get("/api/ranking/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_candidates"] == 2
    symbols = {c["symbol"] for c in body["top_candidates"]}
    assert symbols == {"RELIANCE", "TCS"}


def test_ranking_top_respects_limit(client):
    set_cached_result("a_group", _fake_scan_result())
    resp = client.get("/api/ranking/top?limit=1")
    assert resp.status_code == 200
    assert len(resp.json()["candidates"]) == 1


def test_ranking_strategy_endpoint_returns_only_that_strategys_qualifiers(client):
    set_cached_result("a_group", _fake_scan_result())
    resp = client.get("/api/ranking/strategy/GFS")
    assert resp.status_code == 200
    body = resp.json()
    assert body["top_candidate"]["symbol"] == "TCS"
    assert all(c["symbol"] == "TCS" for c in body["candidates"])


def test_ranking_unknown_strategy_404s(client):
    set_cached_result("a_group", _fake_scan_result())
    resp = client.get("/api/ranking/strategy/NotAStrategy")
    assert resp.status_code == 404

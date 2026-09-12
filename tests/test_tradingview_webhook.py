from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.core.database import Base, get_db
from backend.core import config as core_config
from backend.main import app


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """
    Isolated in-memory DB per test (never touches the real scanner.db), and
    TradingView enabled with a known secret so most tests exercise the real
    auth/validation/dedupe path. Tests that need it disabled/unconfigured
    override these settings explicitly.
    """
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(core_config.settings, "tradingview_enabled", True)
    monkeypatch.setattr(core_config.settings, "tradingview_webhook_secret", "test-secret-123")

    # Deliberately NOT using `with TestClient(app) as c:` — that would run
    # the app's lifespan (backend/main.py) and attempt a real Tapetide
    # connection, which is slow/network-dependent and irrelevant to these
    # webhook-only tests. Without the context manager, lifespan never runs
    # and the TradingView routes (which don't depend on any provider) work
    # exactly the same.
    yield TestClient(app)

    app.dependency_overrides.clear()


def _gfs_payload(**overrides) -> dict:
    payload = {
        "source": "tradingview",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "strategy": "GFS",
        "timeframe": "1D",
        "signal_date": "2026-09-12T15:30:00Z",
        "daily_rsi": 42.31,
        "weekly_rsi": 67.82,
        "monthly_rsi": 71.15,
        "signal": True,
        "secret": "test-secret-123",
    }
    payload.update(overrides)
    return payload


def test_valid_gfs_webhook_is_accepted(client):
    res = client.post("/api/tradingview/webhook", json=_gfs_payload())
    body = res.json()
    assert res.status_code == 200
    assert body["success"] is True
    assert body["strategy"] == "GFS"
    assert body["symbol"] == "RELIANCE"
    assert body["signal_id"]


def test_valid_advanced_gfs_webhook_is_accepted(client):
    payload = _gfs_payload(strategy="Advanced GFS", daily_rsi=61.0, weekly_rsi=70.0, monthly_rsi=72.0)
    res = client.post("/api/tradingview/webhook", json=payload)
    assert res.json()["success"] is True


def test_valid_strategy_one_webhook_is_accepted(client):
    payload = _gfs_payload(strategy="Strategy One")
    res = client.post("/api/tradingview/webhook", json=payload)
    assert res.json()["success"] is True


def test_valid_prd_webhook_is_accepted(client):
    payload = _gfs_payload(
        strategy="PRD",
        divergence_type="PRD",
        divergence_timeframe="Weekly",
    )
    res = client.post("/api/tradingview/webhook", json=payload)
    body = res.json()
    assert body["success"] is True
    assert body["strategy"] == "PRD"


def test_valid_nrd_webhook_is_accepted(client):
    payload = _gfs_payload(
        strategy="NRD",
        divergence_type="NRD",
        divergence_timeframe="Daily",
        daily_rsi=30.0,
        weekly_rsi=35.0,
        monthly_rsi=40.0,
    )
    res = client.post("/api/tradingview/webhook", json=payload)
    body = res.json()
    assert body["success"] is True
    assert body["strategy"] == "NRD"


def test_valid_value_buy_webhook_is_accepted(client):
    payload = _gfs_payload(
        strategy="Value Buy",
        monthly_rsi=41.2,
        weekly_candle="GREEN",
        daily_trigger="KEY_REVERSAL",
    )
    res = client.post("/api/tradingview/webhook", json=payload)
    body = res.json()
    assert body["success"] is True
    assert body["strategy"] == "Value Buy"


def test_invalid_payload_missing_required_json_fields_is_rejected_gracefully(client):
    res = client.post("/api/tradingview/webhook", json={"source": "tradingview", "secret": "test-secret-123"})
    assert res.status_code == 200  # never crashes / never a raw 500
    body = res.json()
    assert body["success"] is False
    assert "Invalid TradingView webhook payload" in body["message"]


def test_missing_symbol_is_rejected(client):
    payload = _gfs_payload()
    payload.pop("symbol")
    res = client.post("/api/tradingview/webhook", json=payload)
    body = res.json()
    assert body["success"] is False


def test_missing_strategy_is_rejected(client):
    payload = _gfs_payload()
    payload.pop("strategy")
    res = client.post("/api/tradingview/webhook", json=payload)
    body = res.json()
    assert body["success"] is False


def test_invalid_strategy_name_is_rejected(client):
    payload = _gfs_payload(strategy="Not A Real Strategy")
    res = client.post("/api/tradingview/webhook", json=payload)
    body = res.json()
    assert body["success"] is False
    assert "Unknown strategy" in body["message"]


def test_unauthorized_webhook_without_secret_is_rejected(client):
    payload = _gfs_payload()
    payload.pop("secret")
    res = client.post("/api/tradingview/webhook", json=payload)
    body = res.json()
    assert res.status_code == 200
    assert body["success"] is False
    assert "secret" in body["message"].lower()


def test_unauthorized_webhook_with_wrong_secret_is_rejected(client):
    payload = _gfs_payload(secret="wrong-secret")
    res = client.post("/api/tradingview/webhook", json=payload)
    assert res.json()["success"] is False


def test_duplicate_webhook_delivery_does_not_create_a_second_row(client):
    payload = _gfs_payload()
    first = client.post("/api/tradingview/webhook", json=payload)
    second = client.post("/api/tradingview/webhook", json=payload)
    assert first.json()["success"] is True
    assert second.json()["success"] is True
    assert first.json()["signal_id"] == second.json()["signal_id"]

    listing = client.get("/api/tradingview/signals").json()
    matching = [s for s in listing if s["symbol"] == "RELIANCE" and s["strategy"] == "GFS"]
    assert len(matching) == 1


def test_prd_and_nrd_can_both_fire_for_the_same_stock_simultaneously(client):
    prd_payload = _gfs_payload(strategy="PRD", divergence_type="PRD", divergence_timeframe="Weekly", symbol="TCS")
    nrd_payload = _gfs_payload(
        strategy="NRD",
        divergence_type="NRD",
        divergence_timeframe="Daily",
        symbol="TCS",
        daily_rsi=30.0,
        weekly_rsi=35.0,
        monthly_rsi=40.0,
    )
    r1 = client.post("/api/tradingview/webhook", json=prd_payload)
    r2 = client.post("/api/tradingview/webhook", json=nrd_payload)
    assert r1.json()["success"] is True
    assert r2.json()["success"] is True

    listing = client.get("/api/tradingview/signals").json()
    tcs_strategies = {s["strategy"] for s in listing if s["symbol"] == "TCS"}
    assert tcs_strategies == {"PRD", "NRD"}


def test_prd_requires_divergence_timeframe(client):
    payload = _gfs_payload(strategy="PRD", divergence_type="PRD")
    res = client.post("/api/tradingview/webhook", json=payload)
    body = res.json()
    assert body["success"] is False
    assert "divergence_timeframe" in body["message"]


def test_value_buy_requires_green_confirmed_weekly_candle(client):
    payload = _gfs_payload(strategy="Value Buy", monthly_rsi=41.2, weekly_candle="RED", daily_trigger="KEY_REVERSAL")
    res = client.post("/api/tradingview/webhook", json=payload)
    body = res.json()
    assert body["success"] is False


def test_valid_sector_rsi_webhook_is_accepted(client):
    payload = {
        "source": "tradingview",
        "symbol": "Nifty Healthcare",
        "strategy": "SECTOR_RSI",
        "timeframe": "1W",
        "signal_date": "2026-09-08T00:00:00Z",
        "weekly_rsi": 63.4,
        "monthly_rsi": 71.0,
        "signal": True,
        "secret": "test-secret-123",
    }
    res = client.post("/api/tradingview/webhook", json=payload)
    body = res.json()
    assert body["success"] is True
    assert body["strategy"] == "SECTOR_RSI"


def test_sector_rsi_requires_at_least_one_rsi_value(client):
    payload = {
        "source": "tradingview",
        "symbol": "Nifty Healthcare",
        "strategy": "SECTOR_RSI",
        "timeframe": "1W",
        "signal_date": "2026-09-08T00:00:00Z",
        "signal": True,
        "secret": "test-secret-123",
    }
    res = client.post("/api/tradingview/webhook", json=payload)
    body = res.json()
    assert body["success"] is False
    assert "weekly_rsi or monthly_rsi" in body["message"]


def test_status_endpoint_reports_enabled_and_configured(client):
    res = client.get("/api/tradingview/status")
    body = res.json()
    assert body["enabled"] is True
    assert body["configured"] is True
    assert body["signal_count"] == 0


def test_backend_stable_and_webhook_inert_when_tradingview_disabled(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test_disabled.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(core_config.settings, "tradingview_enabled", False)
    monkeypatch.setattr(core_config.settings, "tradingview_webhook_secret", "")

    c = TestClient(app)

    # The rest of the app (health check) is completely unaffected.
    assert c.get("/api/health").json() == {"status": "ok"}

    res = c.post("/api/tradingview/webhook", json=_gfs_payload())
    body = res.json()
    assert res.status_code == 200
    assert body["success"] is False

    status = c.get("/api/tradingview/status").json()
    assert status["enabled"] is False
    assert status["configured"] is False

    app.dependency_overrides.clear()

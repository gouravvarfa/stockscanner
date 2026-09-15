import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.providers.angelone_client import AngelOneApiError, AngelOneSession
from backend.services import angelone_credential_store


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(angelone_credential_store, "CREDENTIAL_PATH", tmp_path / "angelone_credentials.json")
    # Safe to run the real lifespan here (unlike test_tradingview_webhook.py):
    # provider_factory.startup() now only constructs AngelOneProvider — no
    # network calls, no Tapetide — since Tapetide was removed from this
    # project. get_angelone_provider().reset_session() (used by /connect
    # and /disconnect) requires this to have run.
    with TestClient(app) as c:
        yield c


def _fake_session(client_code: str = "TESTCLIENT") -> AngelOneSession:
    return AngelOneSession(api_key="key", jwt_token="jwt", feed_token="feed", refresh_token="refresh", client_code=client_code)


def _payload() -> dict:
    return {"api_key": "k", "client_code": "TESTCLIENT", "pin": "1234", "totp_secret": "SECRET"}


def test_status_reports_not_configured_by_default(client):
    res = client.get("/api/expiry/angelone/status")
    body = res.json()
    assert body["configured"] is False
    assert body["connected_at"] is None


def test_test_connection_succeeds_without_persisting_anything(client, monkeypatch):
    import backend.api.angelone as angelone_api

    async def fake_login(api_key, client_code, pin, totp_secret):
        return _fake_session(client_code)

    monkeypatch.setattr(angelone_api, "login", fake_login)

    res = client.post("/api/expiry/angelone/test-connection", json=_payload())
    body = res.json()
    assert body["success"] is True
    assert "TESTCLIENT" in body["message"]

    # A pure test must never save credentials or affect /status.
    status = client.get("/api/expiry/angelone/status").json()
    assert status["configured"] is False


def test_test_connection_reports_failure_without_raising(client, monkeypatch):
    import backend.api.angelone as angelone_api

    async def fake_login(api_key, client_code, pin, totp_secret):
        raise AngelOneApiError("Invalid TOTP", kind="auth")

    monkeypatch.setattr(angelone_api, "login", fake_login)

    res = client.post("/api/expiry/angelone/test-connection", json=_payload())
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False
    assert "Invalid TOTP" in body["message"]


def test_connect_saves_credentials_and_records_connected_at(client, monkeypatch):
    import backend.api.angelone as angelone_api

    async def fake_login(api_key, client_code, pin, totp_secret):
        return _fake_session(client_code)

    monkeypatch.setattr(angelone_api, "login", fake_login)

    res = client.post("/api/expiry/angelone/connect", json=_payload())
    body = res.json()
    assert body["configured"] is True
    assert body["connected_at"] is not None

    status = client.get("/api/expiry/angelone/status").json()
    assert status["configured"] is True
    assert status["client_code"] == "TESTCLIENT"
    assert status["connected_at"] == body["connected_at"]


def test_connect_never_saves_on_failed_login(client, monkeypatch):
    import backend.api.angelone as angelone_api

    async def fake_login(api_key, client_code, pin, totp_secret):
        raise AngelOneApiError("Invalid credentials", kind="auth")

    monkeypatch.setattr(angelone_api, "login", fake_login)

    res = client.post("/api/expiry/angelone/connect", json=_payload())
    assert res.status_code == 400

    status = client.get("/api/expiry/angelone/status").json()
    assert status["configured"] is False


def test_disconnect_clears_saved_credentials(client, monkeypatch):
    import backend.api.angelone as angelone_api

    async def fake_login(api_key, client_code, pin, totp_secret):
        return _fake_session(client_code)

    monkeypatch.setattr(angelone_api, "login", fake_login)
    client.post("/api/expiry/angelone/connect", json=_payload())

    res = client.post("/api/expiry/angelone/disconnect")
    assert res.json()["configured"] is False

    status = client.get("/api/expiry/angelone/status").json()
    assert status["configured"] is False


def test_status_endpoint_never_returns_secret_fields(client, monkeypatch):
    import backend.api.angelone as angelone_api

    async def fake_login(api_key, client_code, pin, totp_secret):
        return _fake_session(client_code)

    monkeypatch.setattr(angelone_api, "login", fake_login)
    client.post("/api/expiry/angelone/connect", json=_payload())

    status = client.get("/api/expiry/angelone/status").json()
    assert "api_key" not in status
    assert "pin" not in status
    assert "totp_secret" not in status

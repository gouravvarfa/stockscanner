import pandas as pd
import pytest
from fastapi.testclient import TestClient

import backend.api.chart as chart_api
from backend.main import app
from backend.services import angelone_credential_store


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(angelone_credential_store, "CREDENTIAL_PATH", tmp_path / "angelone_credentials.json")
    with TestClient(app) as c:
        yield c


def _fake_get_candles(*a, **kw):
    idx = pd.date_range("2026-09-01", periods=3, freq="D")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)


async def _fake_get_candles_async(*a, **kw):
    return _fake_get_candles()


def test_candles_response_disables_all_caching(client, monkeypatch):
    """Regression (2026-09-28, ACC/ABFRL chart-frozen bug): without an
    explicit Cache-Control: no-store, the calling browser/webview's own
    HTTP disk cache could serve a stale response indefinitely — invisible
    to and unaffected by the frontend's own in-memory chart cache, and not
    cleared by a page refresh or even a full app restart. 1D/1W/1M now
    carry a live, continuously-changing current candle, so this response
    must never be cacheable at the HTTP layer."""
    monkeypatch.setattr(chart_api.chart_service, "get_candles", _fake_get_candles_async)

    resp = client.get("/api/chart/candles", params={"symbol": "ACC", "timeframe": "1D"})

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    assert len(resp.json()["candles"]) == 3

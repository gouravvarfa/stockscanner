import datetime as dt

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.providers.angelone_scrip_master import FutureContract
from backend.services import angelone_credential_store, futures_instrument_service
from backend.services.provider_factory import get_angelone_provider


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(angelone_credential_store, "CREDENTIAL_PATH", tmp_path / "angelone_credentials.json")
    with TestClient(app) as c:
        yield c


_RELIANCE_FUT = FutureContract(
    underlying="RELIANCE", trading_symbol="RELIANCE29SEP26FUT", token="68777",
    exch_seg="NFO", expiry="2026-09-29", is_index=False, lot_size=500,
)
_RELIANCE_CASH_LOOKALIKE = FutureContract(
    # A deliberately malformed row (not in the F&O allow-list) to prove the
    # service-layer allow-list actually filters it out even if it somehow
    # appeared in Angel One's raw scrip master response.
    underlying="SOMEDELISTEDNAME", trading_symbol="SOMEDELISTEDNAME29SEP26FUT", token="1",
    exch_seg="NFO", expiry="2026-09-29", is_index=False, lot_size=500,
)


def test_futures_search_never_returns_a_non_fno_symbol(client, monkeypatch):
    async def fake_search(query, limit=25):
        return [_RELIANCE_FUT, _RELIANCE_CASH_LOOKALIKE]

    import backend.providers.angelone_scrip_master as scrip_master
    monkeypatch.setattr(scrip_master, "search_futures", fake_search)

    resp = client.get("/api/top-bottom/futures/search?q=RELIANCE")
    assert resp.status_code == 200
    symbols = [c["trading_symbol"] for c in resp.json()]
    assert "RELIANCE29SEP26FUT" in symbols
    assert "SOMEDELISTEDNAME29SEP26FUT" not in symbols


def test_futures_search_results_are_labeled_fut_with_expiry_and_exchange(client, monkeypatch):
    async def fake_search(query, limit=25):
        return [_RELIANCE_FUT]

    import backend.providers.angelone_scrip_master as scrip_master
    monkeypatch.setattr(scrip_master, "search_futures", fake_search)

    resp = client.get("/api/top-bottom/futures/search?q=RELIANCE")
    body = resp.json()[0]
    assert body["trading_symbol"].endswith("FUT")
    assert body["expiry"] == "2026-09-29"
    assert body["exch_seg"] == "NFO"


def test_backtest_endpoint_rejects_unsupported_instrument_type_with_400(client, monkeypatch):
    async def fake_resolve(underlying, expiry):
        return _RELIANCE_FUT

    monkeypatch.setattr(futures_instrument_service, "resolve_contract", fake_resolve)

    resp = client.post(
        "/api/top-bottom/backtest",
        json={
            "symbol": "RELIANCE", "instrument_type": "OPTIDX", "timeframe": "1D",
            "from_date": "2025-01-01T00:00:00", "to_date": "2025-03-01T00:00:00",
        },
    )
    assert resp.status_code == 400
    assert "Unsupported instrument_type" in resp.json()["detail"]


def test_backtest_endpoint_returns_502_not_a_crash_on_provider_error(client, monkeypatch):
    async def fake_resolve(underlying, expiry):
        return _RELIANCE_FUT

    monkeypatch.setattr(futures_instrument_service, "resolve_contract", fake_resolve)

    provider = get_angelone_provider()

    async def broken_fetch(*a, **kw):
        raise RuntimeError("Angel One returned a non-JSON response (HTTP 403).")

    monkeypatch.setattr(provider, "get_intraday_ohlc", broken_fetch)

    resp = client.post(
        "/api/top-bottom/backtest",
        json={
            "symbol": "RELIANCE", "instrument_type": "FUTURES", "timeframe": "1D",
            "from_date": "2025-01-01T00:00:00", "to_date": "2025-03-01T00:00:00",
        },
    )
    assert resp.status_code == 502
    assert "Angel One error" in resp.json()["detail"]


def test_full_backtest_flow_and_excel_export(client, monkeypatch):
    async def fake_resolve(underlying, expiry):
        return _RELIANCE_FUT

    monkeypatch.setattr(futures_instrument_service, "resolve_contract", fake_resolve)

    idx = pd.bdate_range("2025-01-01", periods=60)
    closes = [100.0 + 0.5 * i for i in range(60)]
    df = pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000] * 60},
        index=idx,
    )

    async def fake_fetch(*a, **kw):
        return df

    monkeypatch.setattr(get_angelone_provider(), "get_intraday_ohlc", fake_fetch)

    resp = client.post(
        "/api/top-bottom/backtest",
        json={
            "symbol": "RELIANCE", "instrument_type": "FUTURES", "timeframe": "1D",
            "from_date": "2025-01-01T00:00:00", "to_date": "2025-04-01T00:00:00",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    backtest_id = body["backtest_id"]
    assert body["trading_symbol"] == "RELIANCE29SEP26FUT"

    get_resp = client.get(f"/api/top-bottom/backtest/{backtest_id}")
    assert get_resp.status_code == 200

    export_resp = client.get(f"/api/top-bottom/backtest/{backtest_id}/export")
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_unknown_backtest_id_returns_404(client):
    resp = client.get("/api/top-bottom/backtest/does-not-exist")
    assert resp.status_code == 404

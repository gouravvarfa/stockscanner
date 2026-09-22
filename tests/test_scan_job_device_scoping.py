"""
Device-specific active-scan visibility (2026-09-22 requirement): the scan
itself still runs once, server-side — only WHO CAN SEE/CANCEL a job is
scoped by a client-supplied device_id. Uses the same expiry_level_1 fake
outcome pattern as test_scan_jobs_api.py.
"""
import datetime as dt
import time

import pytest
from fastapi.testclient import TestClient

import backend.api.scan_jobs as scan_jobs_module
from backend.main import app
from backend.services import angelone_credential_store
from backend.services.scan_job_manager import clear_cached_result, job_manager

DEVICE_A = "device-aaaa-1111"
DEVICE_B = "device-bbbb-2222"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(angelone_credential_store, "CREDENTIAL_PATH", tmp_path / "angelone_credentials.json")
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_state():
    for t in ("a_group", "expiry_level_1", "expiry_level_5"):
        clear_cached_result(t)
    job_manager._jobs.clear()
    yield
    for t in ("a_group", "expiry_level_1", "expiry_level_5"):
        clear_cached_result(t)
    job_manager._jobs.clear()


def _fake_expiry_l1_outcome():
    from backend.services.expiry_scan_service import ExpiryLevel1Outcome

    now = dt.datetime.utcnow()
    return ExpiryLevel1Outcome(
        started_at=now, finished_at=now, execution_seconds=0.1, angelone_configured=True,
        index_signals=[], stock_signals=[], symbols_scanned=0, symbols_failed=0, failed_symbols=[],
    )


def _wait_for_completion(client, job_id, device_id=None, timeout=5.0):
    deadline = time.time() + timeout
    params = {"device_id": device_id} if device_id else {}
    while time.time() < deadline:
        body = client.get(f"/api/scan/jobs/{job_id}", params=params).json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise TimeoutError(f"job {job_id} did not finish in time")


def _slow_l1(monkeypatch, delay=0.3):
    async def fake_l1(*a, **kw):
        import asyncio

        await asyncio.sleep(delay)
        return _fake_expiry_l1_outcome()

    monkeypatch.setattr(scan_jobs_module, "run_expiry_level_1_scan", fake_l1)


def test_device_a_starts_scan_and_sees_it(client, monkeypatch):
    _slow_l1(monkeypatch)
    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    job_id = resp.json()["job"]["job_id"]

    jobs = client.get("/api/scan/jobs", params={"device_id": DEVICE_A}).json()
    assert any(j["job_id"] == job_id for j in jobs)


def test_device_b_does_not_see_device_a_job(client, monkeypatch):
    _slow_l1(monkeypatch)
    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    job_id = resp.json()["job"]["job_id"]

    jobs_b = client.get("/api/scan/jobs", params={"device_id": DEVICE_B}).json()
    assert not any(j["job_id"] == job_id for j in jobs_b)

    # Direct lookup by id is also denied — treated exactly like "not found".
    get_b = client.get(f"/api/scan/jobs/{job_id}", params={"device_id": DEVICE_B})
    assert get_b.status_code == 404


def test_device_a_still_sees_its_job_after_a_fresh_poll(client, monkeypatch):
    """Simulates 'refresh': a brand new /jobs listing call, same device_id."""
    _slow_l1(monkeypatch)
    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    job_id = resp.json()["job"]["job_id"]

    jobs = client.get("/api/scan/jobs", params={"device_id": DEVICE_A}).json()
    assert any(j["job_id"] == job_id and j["status"] == "running" for j in jobs)


def test_device_b_starting_its_own_job_only_device_b_sees_it(client, monkeypatch):
    _slow_l1(monkeypatch)
    resp_a = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    job_a = resp_a.json()["job"]["job_id"]
    _wait_for_completion(client, job_a, device_id=DEVICE_A)  # let A's job finish so B can start the same type

    _slow_l1(monkeypatch)
    # /start now serves A's just-completed job's cache (expected, unrelated
    # to device scoping) — use /fresh to force B to actually start its own job.
    resp_b = client.post("/api/scan/fresh", json={"scan_type": "expiry_level_1", "device_id": DEVICE_B})
    job_b = resp_b.json()["job"]["job_id"]

    jobs_a = client.get("/api/scan/jobs", params={"device_id": DEVICE_A}).json()
    jobs_b = client.get("/api/scan/jobs", params={"device_id": DEVICE_B}).json()
    assert not any(j["job_id"] == job_b for j in jobs_a)
    assert any(j["job_id"] == job_b for j in jobs_b)


def test_device_a_cannot_cancel_device_bs_scan(client, monkeypatch):
    _slow_l1(monkeypatch)
    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_B})
    job_id = resp.json()["job"]["job_id"]

    cancel = client.post(f"/api/scan/jobs/{job_id}/cancel", params={"device_id": DEVICE_A})
    assert cancel.status_code == 404

    still_running = client.get(f"/api/scan/jobs/{job_id}", params={"device_id": DEVICE_B}).json()
    assert still_running["status"] == "running"
    client.post(f"/api/scan/jobs/{job_id}/cancel", params={"device_id": DEVICE_B})  # cleanup


def test_device_b_cannot_cancel_device_as_scan(client, monkeypatch):
    _slow_l1(monkeypatch)
    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    job_id = resp.json()["job"]["job_id"]

    cancel = client.post(f"/api/scan/jobs/{job_id}/cancel", params={"device_id": DEVICE_B})
    assert cancel.status_code == 404
    client.post(f"/api/scan/jobs/{job_id}/cancel", params={"device_id": DEVICE_A})  # cleanup


def test_device_a_owns_and_can_cancel_its_own_scan(client, monkeypatch):
    _slow_l1(monkeypatch, delay=2.0)
    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    job_id = resp.json()["job"]["job_id"]

    cancel = client.post(f"/api/scan/jobs/{job_id}/cancel", params={"device_id": DEVICE_A})
    assert cancel.status_code == 200
    final = _wait_for_completion(client, job_id, device_id=DEVICE_A)
    assert final["status"] == "cancelled"


def test_legacy_job_without_device_id_is_not_exposed_to_a_device_scoped_listing(client, monkeypatch):
    _slow_l1(monkeypatch)
    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1"})  # no device_id — legacy client
    job_id = resp.json()["job"]["job_id"]
    assert resp.json()["job"]["device_id"] is None

    jobs_a = client.get("/api/scan/jobs", params={"device_id": DEVICE_A}).json()
    assert not any(j["job_id"] == job_id for j in jobs_a)

    # But an unscoped listing (no device_id — old caller behavior) still sees it.
    jobs_unscoped = client.get("/api/scan/jobs").json()
    assert any(j["job_id"] == job_id for j in jobs_unscoped)
    client.post(f"/api/scan/jobs/{job_id}/cancel")  # cleanup, unscoped (legacy) cancel still works


def test_completed_history_remains_available_regardless_of_device(client, monkeypatch):
    """Scan History (backend/api/history.py's persisted DB rows) is a
    separate concern from live job visibility and is unaffected."""
    _slow_l1(monkeypatch, delay=0.05)
    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    job_id = resp.json()["job"]["job_id"]
    _wait_for_completion(client, job_id, device_id=DEVICE_A)

    results = client.get(f"/api/scan/jobs/{job_id}/results")
    assert results.status_code == 200


def test_existing_unscoped_behavior_is_unchanged(client, monkeypatch):
    """job_manager.get/list_jobs/cancel called with no device_id (every
    existing direct caller/test) behave exactly as before this change."""
    _slow_l1(monkeypatch)
    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1"})
    job_id = resp.json()["job"]["job_id"]
    assert job_manager.get(job_id) is not None
    assert any(j.job_id == job_id for j in job_manager.list_jobs())
    assert job_manager.cancel(job_id) is True


def test_device_a_and_device_b_can_start_the_same_scan_type_simultaneously(client, monkeypatch):
    """This is the core multi-device requirement (2026-09-22): the global
    per-scan-type lock is gone — only a same-device duplicate is rejected."""
    _slow_l1(monkeypatch, delay=0.3)
    resp_a = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    assert resp_a.status_code == 200 and resp_a.json()["status"] == "started"

    resp_b = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_B})
    assert resp_b.status_code == 200 and resp_b.json()["status"] == "started"

    job_a, job_b = resp_a.json()["job"]["job_id"], resp_b.json()["job"]["job_id"]
    assert job_a != job_b

    jobs_a = client.get("/api/scan/jobs", params={"device_id": DEVICE_A}).json()
    jobs_b = client.get("/api/scan/jobs", params={"device_id": DEVICE_B}).json()
    assert any(j["job_id"] == job_a for j in jobs_a) and not any(j["job_id"] == job_a for j in jobs_b)
    assert any(j["job_id"] == job_b for j in jobs_b) and not any(j["job_id"] == job_b for j in jobs_a)

    _wait_for_completion(client, job_a, device_id=DEVICE_A)
    _wait_for_completion(client, job_b, device_id=DEVICE_B)


def test_same_device_cannot_double_start_the_same_scan_type(client, monkeypatch):
    _slow_l1(monkeypatch, delay=0.3)
    resp1 = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    assert resp1.status_code == 200

    resp2 = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    assert resp2.status_code == 409
    _wait_for_completion(client, resp1.json()["job"]["job_id"], device_id=DEVICE_A)


def test_third_device_is_rejected_once_the_concurrency_cap_is_reached(client, monkeypatch):
    from backend.services.scan_job_manager import MAX_CONCURRENT_JOBS_PER_SCAN_TYPE

    _slow_l1(monkeypatch, delay=2.0)
    devices = [f"device-cap-{i}" for i in range(MAX_CONCURRENT_JOBS_PER_SCAN_TYPE + 1)]
    started = []
    for i, device in enumerate(devices):
        resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": device})
        if i < MAX_CONCURRENT_JOBS_PER_SCAN_TYPE:
            assert resp.status_code == 200, resp.json()
            started.append(resp.json()["job"]["job_id"])
        else:
            assert resp.status_code == 429
            assert "Too many" in resp.json()["detail"]
    for job_id, device in zip(started, devices):
        client.post(f"/api/scan/jobs/{job_id}/cancel", params={"device_id": device})


def test_409_body_includes_the_existing_jobs_id_for_direct_adoption(client, monkeypatch):
    _slow_l1(monkeypatch, delay=2.0)
    resp1 = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    job_id = resp1.json()["job"]["job_id"]

    resp2 = client.post("/api/scan/start", json={"scan_type": "expiry_level_1", "device_id": DEVICE_A})
    assert resp2.status_code == 409
    detail = resp2.json()["detail"]
    assert isinstance(detail, dict) and detail["job_id"] == job_id
    client.post(f"/api/scan/jobs/{job_id}/cancel", params={"device_id": DEVICE_A})  # cleanup

import asyncio
import datetime as dt

import pytest
from fastapi.testclient import TestClient

import backend.api.scan_jobs as scan_jobs_module
from backend.main import app
from backend.services import angelone_credential_store
from backend.services.scan_job_manager import clear_cached_result, job_manager


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
    job_manager._running_by_type.clear()
    yield
    for t in ("a_group", "expiry_level_1", "expiry_level_5"):
        clear_cached_result(t)
    job_manager._jobs.clear()
    job_manager._running_by_type.clear()


def _wait_for_completion(client, job_id, timeout=5.0):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/scan/jobs/{job_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise TimeoutError(f"job {job_id} did not finish in time")


def _fake_expiry_l1_outcome():
    from backend.services.expiry_scan_service import ExpiryLevel1Outcome

    now = dt.datetime.utcnow()
    return ExpiryLevel1Outcome(
        started_at=now, finished_at=now, execution_seconds=0.1, angelone_configured=True,
        index_signals=[], stock_signals=[], symbols_scanned=0, symbols_failed=0, failed_symbols=[],
    )


def _fake_expiry_l5_outcome():
    from backend.services.expiry_level_5_scan_service import ExpiryLevel5Outcome

    now = dt.datetime.utcnow()
    return ExpiryLevel5Outcome(
        started_at=now, finished_at=now, execution_seconds=0.1, angelone_configured=True,
        signals=[], symbols_scanned=0, symbols_failed=0, failed_symbols=[],
    )


def test_start_with_no_cache_starts_a_background_job(client, monkeypatch):
    async def fake_l1(*a, **kw):
        return _fake_expiry_l1_outcome()

    monkeypatch.setattr(scan_jobs_module, "run_expiry_level_1_scan", fake_l1)

    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "started"
    assert body["job"]["scan_type"] == "expiry_level_1"
    assert body["job"]["status"] == "running"

    final = _wait_for_completion(client, body["job"]["job_id"])
    assert final["status"] == "completed"


def test_start_serves_valid_cache_without_starting_a_job(client, monkeypatch):
    from backend.services.scan_job_manager import set_cached_result

    set_cached_result("expiry_level_5", {"symbols_scanned": 3})

    async def fail_if_called(*a, **kw):
        raise AssertionError("should not have started a real scan — a cache was available")

    monkeypatch.setattr(scan_jobs_module, "run_expiry_level_5_scan", fail_if_called)

    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_5"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cached"
    assert body["cache"]["result"] == {"symbols_scanned": 3}


def test_fresh_scan_ignores_cache_and_starts_a_new_job(client, monkeypatch):
    from backend.services.scan_job_manager import set_cached_result

    set_cached_result("expiry_level_1", {"stale": True})

    called = {"n": 0}

    async def fake_l1(*a, **kw):
        called["n"] += 1
        return _fake_expiry_l1_outcome()

    monkeypatch.setattr(scan_jobs_module, "run_expiry_level_1_scan", fake_l1)

    resp = client.post("/api/scan/fresh", json={"scan_type": "expiry_level_1"})
    body = resp.json()
    assert body["status"] == "started"
    _wait_for_completion(client, body["job"]["job_id"])
    assert called["n"] == 1


def test_fresh_scan_replaces_cache_only_on_success(client, monkeypatch):
    from backend.services.scan_job_manager import get_cached_result, set_cached_result

    set_cached_result("expiry_level_1", {"old": True})

    async def fake_fail(*a, **kw):
        raise RuntimeError("simulated Angel One outage")

    monkeypatch.setattr(scan_jobs_module, "run_expiry_level_1_scan", fake_fail)

    resp = client.post("/api/scan/fresh", json={"scan_type": "expiry_level_1"})
    job_id = resp.json()["job"]["job_id"]
    final = _wait_for_completion(client, job_id)
    assert final["status"] == "failed"

    # The old cache must survive an unsuccessful fresh scan.
    assert get_cached_result("expiry_level_1")["result"] == {"old": True}


def test_fresh_scan_for_one_type_does_not_touch_another_types_cache(client, monkeypatch):
    from backend.services.scan_job_manager import get_cached_result, set_cached_result

    set_cached_result("expiry_level_1", {"l1": True})
    set_cached_result("expiry_level_5", {"l5": True})

    async def fake_l5(*a, **kw):
        return _fake_expiry_l5_outcome()

    monkeypatch.setattr(scan_jobs_module, "run_expiry_level_5_scan", fake_l5)

    resp = client.post("/api/scan/fresh", json={"scan_type": "expiry_level_5"})
    _wait_for_completion(client, resp.json()["job"]["job_id"])

    assert get_cached_result("expiry_level_1")["result"] == {"l1": True}
    assert get_cached_result("expiry_level_5")["result"] != {"l5": True}  # replaced by the real (fake) scan


def test_starting_the_same_scan_type_twice_concurrently_is_rejected(client, monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_l1(*a, **kw):
        started.set()
        await release.wait()
        return _fake_expiry_l1_outcome()

    monkeypatch.setattr(scan_jobs_module, "run_expiry_level_1_scan", slow_l1)

    first = client.post("/api/scan/fresh", json={"scan_type": "expiry_level_1"})
    assert first.status_code == 200
    job_id = first.json()["job"]["job_id"]

    import time
    deadline = time.time() + 2
    while job_manager.get(job_id).processed == 0 and time.time() < deadline and job_manager.get(job_id).status == "running":
        # give the background task a chance to actually start
        time.sleep(0.01)
        if job_manager.get(job_id).status != "running":
            break

    second = client.post("/api/scan/fresh", json={"scan_type": "expiry_level_1"})
    assert second.status_code == 409

    # unblock and let it finish so it doesn't leak into other tests
    job = job_manager.get(job_id)
    if job._task is not None and not job._task.done():
        job._task.get_loop().call_soon_threadsafe(release.set)
    _wait_for_completion(client, job_id, timeout=5)


def test_jobs_list_and_cancel_endpoints(client, monkeypatch):
    release = asyncio.Event()

    async def slow_l5(*a, **kw):
        await release.wait()
        return _fake_expiry_l5_outcome()

    monkeypatch.setattr(scan_jobs_module, "run_expiry_level_5_scan", slow_l5)

    resp = client.post("/api/scan/fresh", json={"scan_type": "expiry_level_5"})
    job_id = resp.json()["job"]["job_id"]

    listed = client.get("/api/scan/jobs").json()
    assert any(j["job_id"] == job_id for j in listed)

    cancel_resp = client.post(f"/api/scan/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200

    final = _wait_for_completion(client, job_id)
    assert final["status"] == "cancelled"


def test_unknown_job_id_returns_404(client):
    assert client.get("/api/scan/jobs/does-not-exist").status_code == 404
    assert client.get("/api/scan/jobs/does-not-exist/results").status_code == 404
    assert client.post("/api/scan/jobs/does-not-exist/cancel").status_code == 404


def test_cache_endpoints(client):
    from backend.services.scan_job_manager import set_cached_result

    assert client.get("/api/scan/cache/expiry_level_1").status_code == 404

    set_cached_result("expiry_level_1", {"x": 1})
    resp = client.get("/api/scan/cache/expiry_level_1")
    assert resp.status_code == 200
    assert resp.json()["result"] == {"x": 1}

    assert client.delete("/api/scan/cache/expiry_level_1").status_code == 200
    assert client.get("/api/scan/cache/expiry_level_1").status_code == 404


def test_progress_endpoint_returns_every_processed_stock(client, monkeypatch):
    async def fake_l1(*a, **kw):
        return _fake_expiry_l1_outcome()

    monkeypatch.setattr(scan_jobs_module, "run_expiry_level_1_scan", fake_l1)
    resp = client.post("/api/scan/start", json={"scan_type": "expiry_level_1"})
    job_id = resp.json()["job"]["job_id"]
    _wait_for_completion(client, job_id)

    prog = client.get(f"/api/scan/jobs/{job_id}/progress")
    assert prog.status_code == 200
    assert prog.json()["status"] == "completed"


def test_progress_endpoint_404_for_unknown_job(client):
    resp = client.get("/api/scan/jobs/does-not-exist/progress")
    assert resp.status_code == 404

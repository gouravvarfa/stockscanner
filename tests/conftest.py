import pytest

from backend.providers import call_metrics


@pytest.fixture(autouse=True)
def _isolate_call_metrics(tmp_path, monkeypatch):
    """
    Keeps test runs out of the real provider-call counter.

    Several tests drive run_full_scan end to end, which records fallbacks and
    provider calls. Without this, a test run inflates the live
    .provider_call_metrics.json and makes the reported Tapetide quota usage
    wrong — the one number that has to stay trustworthy, since the 50/day cap
    it tracks is enforced server-side.
    """
    monkeypatch.setattr(call_metrics, "METRICS_PATH", tmp_path / "call_metrics.json")
    call_metrics.reset_for_tests()
    yield
    call_metrics.reset_for_tests()

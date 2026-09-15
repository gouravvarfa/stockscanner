import json

import pytest

from backend.providers import call_metrics


@pytest.fixture(autouse=True)
def isolated_metrics_file(tmp_path, monkeypatch):
    monkeypatch.setattr(call_metrics, "METRICS_PATH", tmp_path / "metrics.json")
    call_metrics.reset_for_tests()
    yield
    call_metrics.reset_for_tests()


def test_counts_start_at_zero_for_the_day():
    m = call_metrics.snapshot()
    assert m.angelone_calls == 0


def test_records_angelone_calls():
    call_metrics.record_angelone_call()
    call_metrics.record_angelone_call()
    call_metrics.record_angelone_call()

    assert call_metrics.snapshot().angelone_calls == 3


def test_counts_survive_a_restart(monkeypatch):
    call_metrics.record_angelone_call()
    call_metrics.record_angelone_call()

    monkeypatch.setattr(call_metrics, "_metrics", None)  # simulate a fresh process
    assert call_metrics.snapshot().angelone_calls == 2


def test_a_corrupt_metrics_file_does_not_break_recording(monkeypatch):
    call_metrics.METRICS_PATH.write_text("{not valid json")
    monkeypatch.setattr(call_metrics, "_metrics", None)

    call_metrics.record_angelone_call()
    assert call_metrics.snapshot().angelone_calls == 1


def test_a_stale_day_resets_the_counter(monkeypatch):
    call_metrics.record_angelone_call()
    stale = json.loads(call_metrics.METRICS_PATH.read_text())
    stale["day"] = "2020-01-01"
    call_metrics.METRICS_PATH.write_text(json.dumps(stale))
    monkeypatch.setattr(call_metrics, "_metrics", None)

    assert call_metrics.snapshot().angelone_calls == 0

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
    assert m.tapetide_calls == 0
    assert m.angelone_calls == 0
    assert m.tapetide_quota_remaining == call_metrics.TAPETIDE_DAILY_QUOTA


def test_records_each_call_type_independently():
    call_metrics.record_tapetide_call()
    call_metrics.record_tapetide_call()
    call_metrics.record_tapetide_cache_hit()
    call_metrics.record_tapetide_cache_miss()
    call_metrics.record_angelone_call()
    call_metrics.record_fallback()

    m = call_metrics.snapshot()
    assert m.tapetide_calls == 2
    assert m.tapetide_cache_hits == 1
    assert m.tapetide_cache_misses == 1
    assert m.angelone_calls == 1
    assert m.fallbacks == 1


def test_quota_remaining_tracks_real_usage_and_never_goes_negative():
    for _ in range(call_metrics.TAPETIDE_DAILY_QUOTA + 5):
        call_metrics.record_tapetide_call()

    m = call_metrics.snapshot()
    assert m.tapetide_calls == call_metrics.TAPETIDE_DAILY_QUOTA + 5
    assert m.tapetide_quota_remaining == 0  # clamped, never negative


def test_cache_hit_rate_reflects_real_ratio():
    for _ in range(3):
        call_metrics.record_tapetide_cache_hit()
    call_metrics.record_tapetide_cache_miss()

    assert call_metrics.snapshot().cache_hit_rate_pct == 75.0


def test_counts_survive_a_restart_because_the_quota_does(tmp_path, monkeypatch):
    # The 50/day cap is enforced on Tapetide's side and does not reset when
    # our process does, so today's count must be reloaded, not zeroed.
    call_metrics.record_tapetide_call()
    call_metrics.record_tapetide_call()

    monkeypatch.setattr(call_metrics, "_metrics", None)  # simulate a fresh process
    assert call_metrics.snapshot().tapetide_calls == 2


def test_a_corrupt_metrics_file_does_not_break_recording(monkeypatch):
    call_metrics.METRICS_PATH.write_text("{not valid json")
    monkeypatch.setattr(call_metrics, "_metrics", None)

    call_metrics.record_tapetide_call()
    assert call_metrics.snapshot().tapetide_calls == 1


def test_a_stale_day_resets_the_counter(monkeypatch):
    call_metrics.record_tapetide_call()
    stale = json.loads(call_metrics.METRICS_PATH.read_text())
    stale["day"] = "2020-01-01"
    call_metrics.METRICS_PATH.write_text(json.dumps(stale))
    monkeypatch.setattr(call_metrics, "_metrics", None)

    assert call_metrics.snapshot().tapetide_calls == 0

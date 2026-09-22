import asyncio

import pytest

from backend.services.scan_job_manager import (
    JobManager,
    ScanAlreadyRunningError,
    ScanJob,
    clear_cached_result,
    get_cached_result,
    set_cached_result,
)


@pytest.fixture(autouse=True)
def clean_cache():
    for t in ("a_group", "expiry_level_1", "expiry_level_5"):
        clear_cached_result(t)
    yield
    for t in ("a_group", "expiry_level_1", "expiry_level_5"):
        clear_cached_result(t)


async def test_job_starts_running_and_completes():
    manager = JobManager()

    async def runner(job):
        job.total = 3
        for s in ["A", "B", "C"]:
            await asyncio.sleep(0)
            job.record_progress(s, True)
        return {"ok": True}

    job = manager.start_job("a_group", runner)
    assert job.status == "running"
    await job._task
    assert job.status == "completed"
    assert job.processed == 3
    assert job.total == 3
    assert job.percentage == 100.0
    assert job.result == {"ok": True}


async def test_job_records_failures_without_stopping():
    manager = JobManager()

    async def runner(job):
        job.total = 2
        job.record_progress("GOOD", True)
        job.record_progress("BAD", False, error="boom")
        return None

    job = manager.start_job("a_group", runner)
    await job._task
    assert job.successful == 1
    assert job.failed == 1
    assert job.failed_symbols[0].symbol == "BAD"
    assert job.failed_symbols[0].error == "boom"


async def test_a_failing_runner_marks_the_job_failed_not_a_crash():
    manager = JobManager()

    async def runner(job):
        raise RuntimeError("provider exploded")

    job = manager.start_job("a_group", runner)
    await job._task
    assert job.status == "failed"
    assert "provider exploded" in job.error


async def test_two_different_scan_types_run_concurrently_independently():
    manager = JobManager()
    started = []

    async def slow_runner(job):
        started.append(job.scan_type)
        await asyncio.sleep(0.05)
        return "done"

    job1 = manager.start_job("a_group", slow_runner)
    job2 = manager.start_job("expiry_level_1", slow_runner)
    assert job1.status == "running"
    assert job2.status == "running"
    await asyncio.gather(job1._task, job2._task)
    assert job1.status == "completed"
    assert job2.status == "completed"
    assert set(started) == {"a_group", "expiry_level_1"}


async def test_starting_the_same_scan_type_twice_is_rejected_by_default():
    manager = JobManager()

    async def slow_runner(job):
        await asyncio.sleep(0.05)
        return "done"

    job1 = manager.start_job("a_group", slow_runner)
    with pytest.raises(ScanAlreadyRunningError):
        manager.start_job("a_group", slow_runner)
    await job1._task


async def test_eta_is_none_until_enough_samples_and_never_fake():
    manager = JobManager()
    hold = asyncio.Event()

    async def runner(job):
        job.total = 10
        job.record_progress("A", True)
        assert job.eta_seconds is None  # only 1 sample — not enough yet
        job.record_progress("B", True)
        job.record_progress("C", True)
        # 3 samples now — ETA should be a real (non-negative) number.
        assert job.eta_seconds is not None
        assert job.eta_seconds >= 0
        await hold.wait()
        return None

    job = manager.start_job("a_group", runner)
    await asyncio.sleep(0.01)
    hold.set()
    await job._task


async def test_cancel_stops_a_running_job():
    manager = JobManager()

    async def runner(job):
        await asyncio.sleep(10)
        return None

    job = manager.start_job("a_group", runner)
    await asyncio.sleep(0)  # let the task actually start running before cancelling it
    assert manager.cancel(job.job_id) is True
    with pytest.raises(asyncio.CancelledError):
        await job._task
    assert job.status == "cancelled"


async def test_list_jobs_returns_newest_first():
    manager = JobManager()

    async def runner(job):
        return None

    j1 = manager.start_job("a_group", runner)
    await j1._task
    j2 = manager.start_job("expiry_level_1", runner)
    await j2._task

    listed = manager.list_jobs()
    assert listed[0].job_id == j2.job_id
    assert listed[1].job_id == j1.job_id


def test_cached_result_round_trips_and_respects_scan_type_isolation():
    assert get_cached_result("a_group") is None
    set_cached_result("a_group", {"trades": 5})
    cached = get_cached_result("a_group")
    assert cached is not None
    assert cached["result"] == {"trades": 5}
    assert cached["scan_type"] == "a_group"
    assert "data_timestamp" in cached and "completed_at" in cached

    # A different scan type's cache is completely independent.
    assert get_cached_result("expiry_level_1") is None


def test_clearing_one_scan_types_cache_does_not_touch_another():
    set_cached_result("a_group", {"a": 1})
    set_cached_result("expiry_level_1", {"b": 2})
    clear_cached_result("a_group")
    assert get_cached_result("a_group") is None
    assert get_cached_result("expiry_level_1") is not None


# ---- device-local persistence feed: progress log + full partial detail ----

def _fake_signal(strategy, symbol, extra=None):
    from backend.strategies.types import StrategySignal
    return StrategySignal(
        strategy=strategy, symbol=symbol, qualifies=True, signal_date=None,
        daily_rsi=55.0, weekly_rsi=62.0, monthly_rsi=58.0, conditions={},
        explanation="qualified", extra=extra or {"current_price": 100.0},
    )


def test_progress_log_records_every_stock_success_or_fail():
    job = ScanJob(job_id="j", scan_type="a_group")
    job.record_progress("GOOD", True)
    job.record_progress("BAD", False, error="timeout")
    log = job.progress_after(0)
    assert [i["symbol"] for i in log["items"]] == ["GOOD", "BAD"]
    assert log["items"][0]["success"] is True
    assert log["items"][1]["success"] is False and log["items"][1]["error"] == "timeout"
    assert log["items"][0]["instrument_type"] in ("FUTURE", "EQUITY")


def test_progress_log_cursor_only_returns_new_entries():
    job = ScanJob(job_id="j", scan_type="a_group")
    job.record_progress("A", True)
    first = job.progress_after(0)
    job.record_progress("B", True)
    second = job.progress_after(first["next"])
    assert [i["symbol"] for i in second["items"]] == ["B"]


def test_partial_result_includes_full_signal_detail_not_just_names():
    job = ScanJob(job_id="j", scan_type="a_group")
    forming_signal = _fake_signal("PRD Forming", "NILKAMAL", extra={
        "current_price": 1887.5,
        "forming": [{"timeframe": "weekly", "a_date": "2026-08-07", "a_low": 1640.0, "a_rsi": 73.02,
                     "b_date": "2026-09-18", "b_low": 1844.2, "b_rsi": 64.04, "ab_distance": 6}],
    })
    job.record_result("NILKAMAL", [("PRD Forming", forming_signal)])
    item = job.partial_after(0)["items"][0]
    assert item["signals"][0]["strategy"] == "PRD Forming"
    assert item["signals"][0]["extra"]["forming"][0]["a_rsi"] == 73.02
    assert item["signals"][0]["weekly_rsi"] == 62.0

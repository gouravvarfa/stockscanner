import pytest

from backend.providers.angelone_client import AngelOneApiError, _retry_async


async def test_retries_transient_failure_then_succeeds():
    calls = {"count": 0}

    async def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise AngelOneApiError("transient", "data", retryable=True)
        return "ok"

    result = await _retry_async(flaky, max_attempts=5, base_delay_seconds=0.001)
    assert result == "ok"
    assert calls["count"] == 3


async def test_does_not_retry_non_retryable_error():
    calls = {"count": 0}

    async def always_fails():
        calls["count"] += 1
        raise AngelOneApiError("permanent", "auth", retryable=False)

    with pytest.raises(AngelOneApiError):
        await _retry_async(always_fails, max_attempts=5, base_delay_seconds=0.001)
    assert calls["count"] == 1  # no retry attempted


async def test_gives_up_after_max_attempts():
    calls = {"count": 0}

    async def always_transient():
        calls["count"] += 1
        raise AngelOneApiError("transient", "data", retryable=True)

    with pytest.raises(AngelOneApiError):
        await _retry_async(always_transient, max_attempts=3, base_delay_seconds=0.001)
    assert calls["count"] == 3

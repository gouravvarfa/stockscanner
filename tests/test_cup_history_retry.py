import asyncio
import datetime as dt

import pandas as pd

from backend.providers import cup_history


class _Flaky:
    def __init__(self, fails: int, message: str):
        self.fails, self.message, self.calls = fails, message, 0

    async def get_daily_ohlc_range(self, exch_seg, token, start, end):
        self.calls += 1
        if self.calls <= self.fails:
            raise RuntimeError(self.message)
        return pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]})


def _run(provider, monkeypatch):
    async def no_sleep(_s):
        return None
    monkeypatch.setattr(cup_history.asyncio, "sleep", no_sleep)
    return asyncio.run(cup_history._fetch_with_retry(provider, "NSE", "1", dt.datetime(2020, 1, 1), dt.datetime(2021, 1, 1)))


def test_rate_limit_is_retried(monkeypatch):
    p = _Flaky(2, "Angel One returned a non-JSON response (HTTP 403).")
    assert len(_run(p, monkeypatch)) == 1 and p.calls == 3


def test_other_errors_are_not_retried(monkeypatch):
    p = _Flaky(1, "symbol not found")
    try:
        _run(p, monkeypatch)
        raise AssertionError("expected an error")
    except RuntimeError as exc:
        assert "not found" in str(exc)
    assert p.calls == 1

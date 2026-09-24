import datetime as dt

import pandas as pd
import pytest

from backend.config.cup_config import CupConfig
from backend.providers import cup_disk_cache, cup_history
from backend.providers.cup_history import CupDataUnavailableError, fetch_cup_history


class FakeMatch:
    exch_seg = "NSE"
    token = "1234"


class FakeProvider:
    """Records every get_daily_ohlc_range call and returns one synthetic
    daily bar per call (date = the requested `start`), so tests can assert
    exactly how many chunk requests were made and with what ranges —
    without touching the real Angel One client/session at all."""

    def __init__(self, has_equity: bool = True):
        self.has_equity = has_equity
        self.calls: list[tuple[dt.datetime, dt.datetime]] = []

    async def resolve_equity(self, symbol: str):
        return FakeMatch() if self.has_equity else None

    async def get_daily_ohlc_range(self, exch_seg, token, from_dt, to_dt):
        self.calls.append((from_dt, to_dt))
        return pd.DataFrame(
            {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1000.0]},
            index=[pd.Timestamp(from_dt)],
        )


CONFIG = CupConfig(history_years=6, chunk_years=2, chunk_delay_seconds=0)


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    """Every test gets its own throwaway on-disk cache — never touches the
    real .cache/cup_history/ the running app uses, and never leaks state
    between tests (unlike the old shared FileCache, which persisted across
    separate test runs and needed explicit per-symbol clearing)."""
    monkeypatch.setattr(cup_disk_cache, "CACHE_DIR", tmp_path / "cup_history")


async def test_cold_cache_splits_full_history_into_chunk_years_windows():
    provider = FakeProvider()
    await fetch_cup_history(provider, "COLDCACHE1", CONFIG)
    # 6 years history / 2-year chunks -> 3 full chunks + a small remainder.
    assert len(provider.calls) in (3, 4)
    for start, end in provider.calls:
        assert (end - start).days <= int(CONFIG.chunk_years * 365.25) + 1
    # The chunks together must cover the full requested span, oldest-first.
    assert provider.calls[0][0] < provider.calls[-1][1]
    assert provider.calls == sorted(provider.calls)


async def test_chunks_are_merged_chronologically_and_deduplicated():
    provider = FakeProvider()
    result = await fetch_cup_history(provider, "MERGEDEDUPE1", CONFIG)
    assert result.index.is_monotonic_increasing
    assert not result.index.duplicated().any()


async def test_warm_cache_is_reused_without_a_network_call():
    provider = FakeProvider()
    await fetch_cup_history(provider, "WARMCACHE1", CONFIG)
    calls_after_first = len(provider.calls)
    await fetch_cup_history(provider, "WARMCACHE1", CONFIG)  # same day -> served from cache
    assert len(provider.calls) == calls_after_first


async def test_stale_cache_only_fetches_the_missing_tail():
    # Cached depth already covers the full 6-year requirement (oldest date
    # well before "now - 6y") — only fresh (newer-than-cached) days are
    # actually missing, so only the tail should be fetched.
    old_data = pd.DataFrame(
        {"open": [50.0, 51.0], "high": [51.0, 52.0], "low": [49.0, 50.0], "close": [50.5, 51.5], "volume": [500.0, 500.0]},
        index=[pd.Timestamp.now() - pd.Timedelta(days=int(6.5 * 365.25)), pd.Timestamp.now() - pd.Timedelta(days=10)],
    )
    cup_disk_cache.save("STALECACHE1", old_data)

    provider = FakeProvider()
    result = await fetch_cup_history(provider, "STALECACHE1", CONFIG)
    # Only ONE tail-fetch call (10-day gap fits in a single chunk), not the
    # full multi-chunk history re-fetch.
    assert len(provider.calls) == 1
    # The tail fetch starts AT the cache's last known date (so a partially-
    # captured boundary day is re-fetched, not skipped) — deduped back to
    # one row for that shared date, with the old, earlier data still intact.
    assert provider.calls[0][0] == old_data.index.max()
    assert result.index.min() == old_data.index.min()


async def test_insufficient_cached_depth_triggers_a_full_refetch():
    """Safe invalidation (per spec): a cache that only covers a SHORT
    recent window (e.g. history_years was widened since it was written, or
    a prior partial fetch) must NOT be treated as sufficient just because
    it's fresh — the full multi-chunk history is refetched instead of
    silently serving too-short a window."""
    shallow_recent_data = pd.DataFrame(
        {"open": [50.0], "high": [51.0], "low": [49.0], "close": [50.5], "volume": [500.0]},
        index=[pd.Timestamp.now() - pd.Timedelta(days=10)],  # nowhere near 6 years back
    )
    cup_disk_cache.save("SHALLOWCACHE1", shallow_recent_data)

    provider = FakeProvider()
    await fetch_cup_history(provider, "SHALLOWCACHE1", CONFIG)
    assert len(provider.calls) >= 3  # a full chunked refetch, not a 1-call tail fetch


async def test_disk_cache_disabled_never_reads_or_writes_the_cache_file():
    """2026-09-24, Render OOM: on Render (enable_disk_cache=False, the
    default whenever the RENDER env var is set), nothing may ever be
    persisted to this instance's disk, and a full chunked fetch must run
    every single call even for the same symbol back-to-back."""
    no_cache_config = CONFIG.model_copy(update={"enable_disk_cache": False})
    provider = FakeProvider()
    await fetch_cup_history(provider, "NOCACHE1", no_cache_config)
    calls_after_first = len(provider.calls)
    assert calls_after_first >= 3  # a full chunked fetch, same as a cold cache
    assert cup_disk_cache.load("NOCACHE1") is None  # never written to disk

    await fetch_cup_history(provider, "NOCACHE1", no_cache_config)
    # A second call for the SAME symbol still does a full fetch again — no
    # cache hit is possible since nothing was ever persisted.
    assert len(provider.calls) == calls_after_first * 2


def test_default_enable_disk_cache_reflects_the_render_env_var(monkeypatch):
    import importlib

    from backend.config import cup_config as cup_config_module

    monkeypatch.setenv("RENDER", "true")
    importlib.reload(cup_config_module)
    assert cup_config_module.CupConfig().enable_disk_cache is False

    monkeypatch.delenv("RENDER", raising=False)
    importlib.reload(cup_config_module)
    assert cup_config_module.CupConfig().enable_disk_cache is True


async def test_missing_equity_listing_raises_cup_specific_error():
    provider = FakeProvider(has_equity=False)
    with pytest.raises(CupDataUnavailableError):
        await fetch_cup_history(provider, "NOLISTING1", CONFIG)


async def test_duplicate_candle_removal_keeps_latest():
    from backend.providers.cup_history import _dedupe_and_sort

    idx = pd.Timestamp("2020-01-01")
    old = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]}, index=[idx])
    new = pd.DataFrame({"open": [2.0], "high": [2.0], "low": [2.0], "close": [2.0], "volume": [2.0]}, index=[idx])
    merged = _dedupe_and_sort([old, new])
    assert len(merged) == 1
    assert merged["close"].iloc[0] == 2.0  # "keep=last" — the more-recently-fetched chunk wins


async def test_fetch_writes_to_the_isolated_per_symbol_cache_not_the_shared_one():
    provider = FakeProvider()
    await fetch_cup_history(provider, "ISOLATEDCACHE1", CONFIG)
    assert cup_disk_cache.load("ISOLATEDCACHE1") is not None
    # The shared, cross-strategy FileCache must never see Cup's data.
    from backend.core.cache import cache

    assert cache.get("cup_history_daily:ISOLATEDCACHE1") is None

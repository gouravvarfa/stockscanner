import pytest

from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
from backend.services.scan_service import run_full_scan


class FakeTapetideProvider:
    """If Angel One mode is correctly enforced, none of these should ever be called."""

    async def get_universe(self, *a, **kw):
        raise AssertionError("Tapetide must not be called when data source mode is explicitly angel_one")

    async def get_index_ohlc(self, *a, **kw): raise NotImplementedError
    async def get_stock_ohlcv(self, *a, **kw): raise NotImplementedError
    async def get_sector_performance(self, *a, **kw): raise NotImplementedError
    async def screen_technical(self, *a, **kw): raise NotImplementedError
    async def get_batch_quotes(self, *a, **kw): raise NotImplementedError


async def test_explicit_angel_one_mode_gives_clear_error_not_tapetide_fallback():
    tapetide = FakeTapetideProvider()

    with pytest.raises(RuntimeError, match="Angel One selected"):
        await run_full_scan(tapetide, DEFAULT_STRATEGY_CONFIG, data_source_mode="angel_one")

import pytest

from backend.providers import angelone_scrip_master as sm


def _row(name: str, series: str, token: str) -> dict:
    return {"exch_seg": "NSE", "instrumenttype": "", "name": name, "symbol": f"{name}-{series}", "token": token}


@pytest.fixture
def fake_master(monkeypatch):
    def install(rows: list[dict]):
        async def fake_fetch():
            return rows

        monkeypatch.setattr(sm, "_fetch_scrip_master", fake_fetch)

    return install


async def test_resolves_a_normal_eq_listing(fake_master):
    fake_master([_row("RELIANCE", "EQ", "2885")])

    match = await sm.resolve_equity("RELIANCE")

    assert match is not None
    assert match.trading_symbol == "RELIANCE-EQ"
    assert match.token == "2885"
    assert match.exch_seg == "NSE"


@pytest.mark.parametrize("series", ["BE", "BZ"])
async def test_resolves_trade_to_trade_and_surveillance_series(fake_master, series):
    """
    Real bug this guards against: stocks whose ONLY NSE cash listing is in
    the BE (trade-to-trade) or BZ series — HEG, HFCL, STLTECH, INDIAGLYCO,
    BLISSGVS, RAJESHEXPO among them — were unresolvable because the matcher
    required a '-EQ' suffix, so the scanner reported them as data-unavailable
    even though Angel One serves their candles perfectly well.
    """
    fake_master([_row("HEG", series, "7368")])

    match = await sm.resolve_equity("HEG")

    assert match is not None
    assert match.trading_symbol == f"HEG-{series}"
    assert match.token == "7368"


async def test_eq_wins_when_a_symbol_is_listed_in_more_than_one_series(fake_master):
    # Order in the master file must not decide which listing is picked: the
    # normal rolling-settlement EQ line is always the right one to scan.
    fake_master([_row("SOMECO", "BE", "111"), _row("SOMECO", "EQ", "222")])

    match = await sm.resolve_equity("SOMECO")

    assert match is not None
    assert match.trading_symbol == "SOMECO-EQ"
    assert match.token == "222"


async def test_non_cash_series_is_never_resolved_as_equity(fake_master):
    # -SM (SME), -GS (govt sec) etc. are different instruments; resolving one
    # of them as the equity would scan the wrong security entirely.
    fake_master([_row("SOMESME", "SM", "999")])

    assert await sm.resolve_equity("SOMESME") is None


async def test_unknown_symbol_returns_none_rather_than_guessing(fake_master):
    fake_master([_row("RELIANCE", "EQ", "2885")])

    assert await sm.resolve_equity("NOSUCHSTOCK") is None


async def test_concurrent_first_calls_share_one_scrip_master_download(monkeypatch):
    import asyncio

    calls = {"n": 0}

    async def slow_download():
        calls["n"] += 1
        await asyncio.sleep(0.1)
        return [{"exch_seg": "NSE", "instrumenttype": "", "symbol": "X-EQ", "name": "X", "token": "1"}]

    monkeypatch.setattr(sm, "_download_and_filter", slow_download)
    monkeypatch.setattr(sm.cache, "get", lambda key: None)
    sm._inflight.clear()
    results = await asyncio.gather(*(sm._fetch_scrip_master() for _ in range(6)))
    assert calls["n"] == 1  # six concurrent callers -> ONE download/parse
    assert all(r == results[0] for r in results)

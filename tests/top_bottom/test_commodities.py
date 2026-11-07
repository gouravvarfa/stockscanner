"""Top-Bottom on MCX gold/silver futures: contract search/resolution, point-value P&L, daily-bar completeness."""
import datetime as dt

import pandas as pd
import pytest

from backend.providers import angelone_scrip_master as scrip_master
from backend.providers.angelone_scrip_master import COMMODITY_POINT_VALUE, FutureContract
from backend.schemas.top_bottom import FutureContractOut
from backend.services import futures_instrument_service as futures_service
from backend.services import top_bottom_backtest_service as tb_service
from backend.services.top_bottom_serializers import serialize_contract


def _row(name, expiry, token, lot, seg="MCX", typ="FUTCOM"):
    return {"exch_seg": seg, "instrumenttype": typ, "name": name, "symbol": f"{name}{expiry}FUT", "token": token,
            "expiry": expiry, "lotsize": str(lot)}


ROWS = [
    _row("GOLD", "04DEC2026", "1", 1), _row("GOLD", "05FEB2027", "2", 1),
    _row("GOLDM", "04DEC2026", "3", 100), _row("GOLDM", "05FEB2027", "4", 100),
    _row("GOLDGUINEA", "29JAN2027", "5", 8), _row("GOLDPETAL", "29JAN2027", "6", 1),
    _row("SILVER", "04DEC2026", "7", 30), _row("SILVERM", "26FEB2027", "8", 5), _row("SILVERMIC", "26FEB2027", "9", 1),
    _row("CRUDEOIL", "19NOV2026", "10", 100),  # another commodity: must never be offered
    _row("GOLD", "04DEC2026", "11", 1, typ="OPTFUT"),  # a gold OPTION on MCX: never offered
    _row("RELIANCE", "29DEC2026", "12", 500, seg="NFO", typ="FUTSTK"),
]


@pytest.fixture()
def master(monkeypatch):
    async def fake():
        return [r for r in ROWS if (r["exch_seg"], r["instrumenttype"]) in (("MCX", "FUTCOM"), ("NFO", "FUTSTK"))]

    monkeypatch.setattr(scrip_master, "_fetch_scrip_master", fake)


async def test_gold_search_returns_the_whole_gold_family_with_point_values(master):
    found = await futures_service.search_futures("GOLD")
    names = {c.underlying for c in found}
    assert names == {"GOLD", "GOLDM", "GOLDGUINEA", "GOLDPETAL"}
    assert all(c.exch_seg == "MCX" and c.commodity and not c.is_index for c in found)
    by_name = {c.underlying: c for c in found}
    assert by_name["GOLD"].point_value == 100 and by_name["GOLDM"].point_value == 10
    assert by_name["GOLDM"].lot_size == 100  # Angel One's own lot is still kept as-is
    assert by_name["GOLDPETAL"].point_value == 1 and by_name["GOLDGUINEA"].point_value == 1


async def test_silver_mini_and_micro_are_found_and_other_commodities_are_not(master):
    names = {c.underlying for c in await futures_service.search_futures("SILVER")}
    assert names == {"SILVER", "SILVERM", "SILVERMIC"}
    assert await futures_service.search_futures("CRUDE") == []
    assert COMMODITY_POINT_VALUE["SILVER"] == 30 and COMMODITY_POINT_VALUE["SILVERM"] == 5 and COMMODITY_POINT_VALUE["SILVERMIC"] == 1


async def test_gold_options_never_leak_in(master):
    assert all(c.token != "11" for c in await futures_service.search_futures("GOLD"))


async def test_equity_futures_search_is_unchanged(master):
    found = await futures_service.search_futures("RELIANCE")
    assert [c.underlying for c in found] == ["RELIANCE"] and not found[0].commodity and found[0].point_value == 0


async def test_list_contracts_keeps_exactly_the_asked_underlying_nearest_first(master):
    gold = await futures_service.list_contracts("GOLD")  # a prefix search would also return GOLDM etc.
    assert [c.underlying for c in gold] == ["GOLD", "GOLD"] and [c.expiry for c in gold] == ["2026-12-04", "2027-02-05"]
    assert [c.expiry for c in await futures_service.list_contracts("goldm")] == ["2026-12-04", "2027-02-05"]


async def test_resolve_picks_the_nearest_expiry_or_the_exact_one(master):
    assert (await futures_service.resolve_contract("GOLDM", None)).token == "3"
    assert (await futures_service.resolve_contract("GOLDM", "2027-02-05")).token == "4"
    with pytest.raises(futures_service.NotAFutureError):
        await futures_service.resolve_contract("GOLDM", "2030-01-01")
    with pytest.raises(futures_service.NotAFutureError, match="NSE/MCX"):
        await futures_service.resolve_contract("CRUDEOIL", None)


async def test_resolved_instrument_is_a_commodity_with_the_point_value_as_multiplier(master):
    inst = await tb_service._resolve_instrument("GOLDM", "FUTURES", None)
    assert inst.instrument_class == "COMMODITY" and inst.exch_seg == "MCX" and inst.lot_size == 10
    micro = await tb_service._resolve_instrument("SILVERMIC", "FUTURES", None)
    assert micro.lot_size == 1 and micro.trading_symbol.startswith("SILVERMIC")
    stock = await tb_service._resolve_instrument("RELIANCE", "FUTURES", None)
    assert stock.instrument_class == "STOCK" and stock.lot_size == 500  # unchanged


def test_contract_api_model_carries_the_commodity_fields():
    out = serialize_contract(FutureContract("GOLDM", "GOLDM04DEC26FUT", "3", "MCX", "2026-12-04", False, 100, True, 10))
    assert isinstance(out, FutureContractOut) and out.commodity is True and out.point_value == 10 and out.exch_seg == "MCX"
    plain = serialize_contract(FutureContract("RELIANCE", "RELIANCE29SEP26FUT", "1", "NFO", "2026-09-29", False, 500))
    assert plain.commodity is False and plain.point_value == 0


class _Provider:
    def __init__(self, df):
        self.df, self.calls = df, []

    async def get_intraday_ohlc(self, exch_seg, symbol_token, interval, days_back):
        self.calls.append((exch_seg, interval))
        return self.df.iloc[0:0] if interval == "FIFTEEN_MINUTE" else self.df

    async def get_daily_ohlc_range(self, exch_seg, symbol_token, from_dt, to_dt):
        return self.df


async def test_daily_backtest_on_gold_mini_uses_mcx_and_prices_pnl_by_point_value(master):
    closes, price = [], 100.0
    for _ in range(5):  # choppy up-leg then down-leg, so the always-reversing stop flips several times
        for step in range(12):
            price += 3 if step % 2 == 0 else -1
            closes.append(price)
        for step in range(12):
            price += -3 if step % 2 == 0 else 1
            closes.append(price)
    idx = pd.bdate_range("2026-06-01", periods=len(closes))
    df = pd.DataFrame({"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
                       "close": closes, "volume": 1000}, index=idx)
    provider = _Provider(df)
    result = await tb_service.run_futures_backtest(
        provider, "GOLDM", "FUTURES", "1D", dt.datetime(2026, 6, 1), dt.datetime(2026, 12, 1),
    )
    assert result.instrument_class == "COMMODITY" and result.exch_seg == "MCX"
    assert ("MCX", "ONE_DAY") in provider.calls
    closed = [t for t in result.trades if t.pnl_points is not None]
    assert len(closed) >= 3
    for t in closed:
        assert t.lot_size == 10
        assert t.pnl_amount == pytest.approx(t.pnl_points * 10)


async def test_mcx_daily_bar_is_complete_only_after_the_late_evening_session():
    from backend.indicators.confirmed_bars import drop_incomplete_trailing_daily_bar

    df = pd.DataFrame({"close": [1.0, 2.0]}, index=pd.to_datetime(["2026-11-05", "2026-11-06"]))
    evening = dt.datetime(2026, 11, 6, 18, 0)  # NSE has closed; MCX is still trading
    assert len(drop_incomplete_trailing_daily_bar(df, evening)) == 2  # NSE rule would call today's bar complete
    assert len(drop_incomplete_trailing_daily_bar(df, evening, dt.time(23, 55))) == 1  # MCX rule drops it
    assert len(drop_incomplete_trailing_daily_bar(df, dt.datetime(2026, 11, 7, 0, 10), dt.time(23, 55))) == 2

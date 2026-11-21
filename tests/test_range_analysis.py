"""Range Analysis: the % range move sheet (formula reverse-engineered from the user's CGPOWER sheet, 163/166 months)."""
from __future__ import annotations

import datetime as dt
import io

import openpyxl
import pandas as pd
import pytest

from backend.strategies import range_move as rm


def month_days(year: int, month: int, o: float, h: float, lo: float, c: float, low_first: bool = True) -> list:
    """Three trading days per month: open, the two extremes (in either order), close."""
    d1, d2, d3 = (dt.datetime(year, month, d) for d in (2, 10, 20))
    first, second = ((lo, h) if low_first else (h, lo))
    return [
        (d1, o, max(o, first), min(o, first), first),
        (d2, first, max(first, second), min(first, second), second),
        (d3, second, max(second, c), min(second, c), c),
    ]


def frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"]).set_index("date")
    df["volume"] = 0.0
    return df


def test_up_month_is_measured_from_the_low_and_down_month_from_the_high():
    assert rm.move_pct(high=120, low=100, close=118, prev_close=105, open_=101) == (20.0, "up")
    assert rm.move_pct(high=120, low=100, close=102, prev_close=110, open_=119) == (16.67, "down")
    # no previous month (first month of the history): its own open decides
    assert rm.move_pct(high=120, low=100, close=110, prev_close=None, open_=105)[1] == "up"
    assert rm.move_pct(high=120, low=100, close=104, prev_close=None, open_=115)[1] == "down"


def test_levels_follow_the_sheet_colours():
    assert [rm.level(v) for v in (35, 30, 29.99, 20, 19.99, None)] == ["green", "green", "orange", "orange", "plain", "none"]


def test_build_table_rows_averages_boxes_and_month_in_progress():
    rows = (
        month_days(2024, 12, 100, 105, 95, 100)
        + month_days(2025, 1, 100, 140, 100, 135)   # up vs Dec close 100: (140-100)/100 = 40% -> green, boxed
        + month_days(2025, 2, 135, 135, 108, 110)   # down: (135-108)/135 = 20% -> orange
        + month_days(2025, 3, 110, 115, 100, 112)   # up vs 110: (115-100)/100 = 15% -> plain
        + month_days(2025, 4, 112, 150, 100, 140)   # in progress (today = April) -> not averaged
    )
    t = rm.build_table(frame(rows), "TEST", today=dt.date(2025, 4, 25))
    by_year = {r["year"]: r for r in t["rows"]}
    jan, feb, mar, apr = by_year[2025]["months"][:4]
    assert (jan["pct"], jan["level"], jan["boxed"]) == (40.0, "green", True)
    assert (feb["pct"], feb["direction"], feb["level"], feb["boxed"]) == (20.0, "down", "orange", False)
    assert (mar["pct"], mar["level"]) == (15.0, "plain")
    assert apr["in_progress"] and not apr["boxed"]
    assert by_year[2025]["avg"] == 25.0 and by_year[2025]["complete_months"] == 3  # (40+20+15)/3, April left out
    assert by_year[2025]["months"][5] is None
    assert t["jan_mar"] == {"ge30": {"JAN": 1, "FEB": 0, "MAR": 0}, "best": ["JAN"]}
    stats = {s["month"]: s for s in t["month_stats"]}
    assert stats["APR"]["years"] == 0 and stats["JAN"]["ge30"] == 1 and stats["FEB"]["ge20"] == 1
    assert t["overall"]["months"] == 4 and t["data_from"] == "2024-12-02" and t["data_to"] == "2025-04-20"
    assert [m["label"] for m in t["monthly"]][:2] == ["DEC 2024", "JAN 2025"]


def test_date_filter_keeps_the_correct_direction_for_its_first_month():
    rows = month_days(2024, 12, 100, 105, 95, 100) + month_days(2025, 1, 100, 140, 100, 135) + month_days(2025, 2, 135, 135, 108, 110)
    t = rm.build_table(frame(rows), "TEST", today=dt.date(2026, 1, 1), start=dt.date(2025, 1, 1), end=dt.date(2025, 1, 31))
    assert [r["year"] for r in t["rows"]] == [2025]
    jan = t["rows"][0]["months"][0]
    assert jan["pct"] == 40.0 and jan["direction"] == "up"  # direction still from December's close
    assert t["rows"][0]["months"][1] is None and t["filter_from"] == "2025-01" and t["filter_to"] == "2025-01"
    with pytest.raises(ValueError):
        rm.build_table(frame(rows), "TEST", start=dt.date(2030, 1, 1))


def test_export_matches_the_sheet_layout():
    from backend.strategies.range_move_export import build_xlsx

    rows = month_days(2024, 12, 100, 105, 95, 100) + month_days(2025, 1, 100, 140, 100, 135) + month_days(2025, 2, 135, 135, 108, 110)
    t = rm.build_table(frame(rows), "TEST", today=dt.date(2026, 1, 1))
    wb = openpyxl.load_workbook(io.BytesIO(build_xlsx(t)))
    ws = wb["RANGE MOVE"]
    assert ws["A1"].value.startswith("TEST - % RANGE MOVE")
    assert [c.value for c in ws[2]][:14] == ["YEAR/MONTH", *rm.MONTHS, "AVG MONTHLY RANGE MOVE"]
    jan = ws.cell(4, 2)  # row 3 = 2024, row 4 = 2025
    assert ws.cell(4, 1).value == 2025 and round(jan.value, 4) == 0.4 and jan.number_format == "0.00%"
    assert jan.fill.fgColor.rgb.endswith("D8F0DA") and jan.border.left.style == "medium"  # green + Jan-Mar box
    assert ws.cell(4, 3).fill.fgColor.rgb.endswith("FBE7C6")  # February 20% -> orange
    assert ws["B2"].fill.fgColor.rgb.endswith("C9EBCB")  # JAN is the Jan-Mar best month
    assert any(str(ws.cell(r, 16).value).startswith("JAN-MAR BEST: JAN") for r in range(1, 12))
    legend_row = next(r for r in range(1, 40) if ws.cell(r, 16).value == "COLOUR LEGEND")
    assert ws.cell(legend_row + 1, 16).fill.fgColor.rgb.endswith("D8F0DA")  # green sample cell
    assert ws.cell(legend_row + 2, 16).fill.fgColor.rgb.endswith("FBE7C6")  # orange sample cell
    assert ws.cell(legend_row + 4, 16).border.left.style == "medium"  # boxed sample
    md = wb["MONTHLY DATA"]
    assert md["A2"].value == "DEC 2024" and md["I3"].value == "(H-L)/L"


async def test_daily_history_fetches_once_then_only_the_tail(monkeypatch, tmp_path):
    from backend.services import range_analysis_service as svc

    calls = []

    class FakeProvider:
        async def get_daily_ohlc_range(self, exch, token, start, end):
            calls.append((start, end))
            days = pd.bdate_range(max(start, dt.datetime(2020, 1, 1)), min(end, dt.datetime(2025, 6, 30)))
            return pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 0.0}, index=days)

    async def fake_resolve(symbol):
        return svc.scrip_master.ScripMatch(token="1", trading_symbol="X-EQ", exch_seg="NSE"), "EQUITY"

    monkeypatch.setattr(svc, "resolve", fake_resolve)
    monkeypatch.setattr(svc, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(svc, "STATELESS_SERVER", False)
    monkeypatch.setattr(svc, "CHUNK_PAUSE_S", 0)
    svc._memory.clear()
    df, kind = await svc.daily_history(FakeProvider(), "X")
    first = len(calls)
    assert kind == "EQUITY" and first >= 6 and calls[0][0] == svc.EARLIEST  # 1990 onwards in ~5-year chunks
    assert df.index.min() == pd.Timestamp("2020-01-01")
    await svc.daily_history(FakeProvider(), "X")
    assert len(calls) == first  # same day: memory, no request
    svc._memory.clear()
    await svc.daily_history(FakeProvider(), "X")
    assert len(calls) == first  # same day on disk, no request
    # next day: only the missing tail
    monkeypatch.setattr(svc, "_load_disk", lambda key: (dt.date(2000, 1, 1), df))
    svc._memory.clear()
    await svc.daily_history(FakeProvider(), "X")
    assert len(calls) == first + 1 and calls[-1][0] > dt.datetime(2025, 6, 1)


async def test_search_finds_stocks_and_indices(monkeypatch):
    from backend.services import range_analysis_service as svc

    rows = [
        {"exch_seg": "NSE", "instrumenttype": "", "name": "CGPOWER", "symbol": "CGPOWER-EQ", "token": "1"},
        {"exch_seg": "NSE", "instrumenttype": "", "name": "CGCL", "symbol": "CGCL-EQ", "token": "2"},
        {"exch_seg": "NSE", "instrumenttype": "", "name": "XYZ", "symbol": "XYZ-SM", "token": "3"},
        {"exch_seg": "NSE", "instrumenttype": "AMXIDX", "name": "NIFTY", "symbol": "Nifty 50", "token": "4"},
    ]

    async def master():
        return rows

    monkeypatch.setattr(svc.scrip_master, "_fetch_scrip_master", master)
    assert [h["symbol"] for h in await svc.search("cg")] == ["CGCL", "CGPOWER"]
    monkeypatch.setattr(svc.universe_loader, "company_name_for", lambda s: "Known Ltd" if s == "CGPOWER" else None)
    assert [h["symbol"] for h in await svc.search("cg")] == ["CGPOWER", "CGCL"]  # well-known names first
    assert await svc.search("xyz") == []  # SME series is not an NSE cash listing here
    nifty = await svc.search("nifty")
    assert nifty[0] == {"symbol": "NIFTY", "name": "Nifty 50", "kind": "INDEX"}


def test_api_stock_export_and_validation(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.api import range_analysis as api
    from backend.main import app

    rows = month_days(2024, 12, 100, 105, 95, 100) + month_days(2025, 1, 100, 140, 100, 135)

    async def fake_analyse(provider, symbol, start, end):
        if symbol == "NOPE":
            raise api.svc.InstrumentNotFound("'NOPE' is not an NSE stock or index Angel One knows.")
        t = rm.build_table(frame(rows), symbol.upper(), today=dt.date(2026, 1, 1), start=start, end=end)
        t["kind"], t["name"] = "EQUITY", None
        return t

    monkeypatch.setattr(api.svc, "analyse", fake_analyse)
    monkeypatch.setattr(api, "get_angelone_provider", lambda: None)
    c = TestClient(app)
    body = c.get("/api/range-analysis/stock/test?from_date=2025-01").json()
    assert body["symbol"] == "TEST" and body["rows"][0]["year"] == 2025
    assert c.get("/api/range-analysis/stock/NOPE").status_code == 404
    assert c.get("/api/range-analysis/stock/TEST?from_date=2025-13").status_code == 400
    assert c.get("/api/range-analysis/stock/TEST?from_date=2025-06&to_date=2025-01").status_code == 400
    x = c.post("/api/range-analysis/export", json=body)
    assert x.status_code == 200 and x.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "TEST_range_move_2025-01_to_2025-01.xlsx" in x.headers["content-disposition"]
    assert c.post("/api/range-analysis/export", json={"symbol": "X"}).status_code == 400

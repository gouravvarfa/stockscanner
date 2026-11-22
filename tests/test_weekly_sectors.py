"""Weekly Sectors: which sector and which stocks are moving (1W / 1M vs their sector; RSI 60+ = STRONG)."""
from __future__ import annotations

import datetime as dt
import io

import numpy as np
import openpyxl
import pandas as pd
import pytest

from backend.strategies import sector_strength as ss


def closes_frame(start: str, values: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(values))
    v = np.array(values, dtype=float)
    return pd.DataFrame({"open": v, "high": v * 1.01, "low": v * 0.99, "close": v, "volume": 0.0}, index=idx)


def trend(start: str, n: int, first: float, daily_pct: float) -> pd.DataFrame:
    return closes_frame(start, [first * (1 + daily_pct / 100) ** i for i in range(n)])


def test_returns_use_the_last_close_on_or_before_each_date():
    df = closes_frame("2026-10-01", list(range(100, 136)))  # business days 1 Oct .. 19 Nov 2026
    r = ss.period_returns(df["close"], pd.Timestamp("2026-11-21"))  # after the last candle: the last close is used
    assert r["end_date"] == df.index[-1].date().isoformat()
    end = df.index[-1]
    w_base = df["close"][df.index <= end - pd.Timedelta(days=7)].iloc[-1]
    m_base = df["close"][df.index <= end - pd.DateOffset(months=1)].iloc[-1]
    assert r["r1w"] == round((df["close"].iloc[-1] / w_base - 1) * 100, 2)
    assert r["r1m"] == round((df["close"].iloc[-1] / m_base - 1) * 100, 2)
    assert ss.period_returns(df["close"], pd.Timestamp("2020-01-01")) is None


def test_signals_and_groups():
    assert ss.signal(1, 1) == "Leader" and ss.signal(1, -1) == "Turning up"
    assert ss.signal(-1, 1) == "Fading" and ss.signal(-1, -1) == "Laggard" and ss.signal(None, 1) == "N/A"
    assert ss.group(-0.7, 4.8) == "Near-leader"  # HDFCBANK in the user's report
    assert ss.group(1.14, -6.8) == "Bounce-only"  # CUB
    assert ss.group(-2.36, 2.19) is None  # ICICIBANK: beats the month but trails the week by more than 1.5 pp
    assert ss.group(2, 3) is None


def test_verdict_needs_daily_weekly_and_monthly_rsi_above_60():
    assert ss.verdict({"d": 84, "w": 73, "m": 66}) == "STRONG"
    assert ss.verdict({"d": 84, "w": 73, "m": 59.9}) == "MIXED"  # one below 60 is enough to miss
    assert ss.verdict({"d": 30, "w": 35, "m": 39}) == "WEAK"
    assert ss.verdict({"d": None, "w": 70, "m": 70}) == "N/A"


def test_rsi_levels_of_a_steady_uptrend_are_strong():
    df = trend("2021-01-01", 1300, 100, 0.12)
    lv = ss.rsi_levels(df, df.index[-1])
    assert all(v is not None and v > 60 for v in lv.values())
    assert ss.verdict(lv) == "STRONG"


def _report():
    up = trend("2021-01-01", 1300, 100, 0.12)       # strong sector index
    down = trend("2021-01-01", 1300, 500, -0.08)    # weak sector index
    as_of = up.index[-1]
    stocks = {
        "AAA": trend("2021-01-01", 1300, 100, 0.20),  # beats the strong sector
        "BBB": trend("2021-01-01", 1300, 100, 0.02),  # trails it
        "M&M": trend("2021-01-01", 1300, 100, -0.02),  # beats the weak sector
        "CCC": trend("2021-01-01", 1300, 100, 0.10),
        "DDD": trend("2021-01-01", 1300, 100, 0.30),
    }
    sectors = [{"key": "up", "label": "Up Sector", "index_label": "NIFTY UP", "equal_weight": False},
               {"key": "down", "label": "Down Sector", "index_label": "NIFTY DOWN", "equal_weight": False},
               {"key": "ew", "label": "Equal Sector", "index_label": None, "equal_weight": True}]
    cons = {"up": [{"symbol": "AAA", "name": "A Ltd"}, {"symbol": "BBB", "name": "B Ltd"}, {"symbol": "ZZZ", "name": "No data"}],
            "down": [{"symbol": "M&M", "name": "Mahindra"}],
            "ew": [{"symbol": "CCC", "name": "C"}, {"symbol": "DDD", "name": "D"}]}
    return ss.build_report(as_of, sectors, {"up": up, "down": down}, stocks, cons, benchmark=up)


def test_build_report_ranks_verdicts_buckets_and_equal_weight():
    r = _report()
    by = {s["key"]: s for s in r["sectors"]}
    assert by["up"]["verdict"] == "STRONG" and by["down"]["verdict"] == "WEAK" and by["ew"]["verdict"] == "N/A"
    assert r["sectors"][0]["key"] == "up"  # STRONG first
    assert by["up"]["rank_1w"] <= 2 and by["down"]["rank_1m"] == 3
    assert {s["symbol"]: s["signal"] for s in by["up"]["stocks"]} == {"AAA": "Leader", "BBB": "Laggard"}
    ew = by["ew"]
    cr = {s["symbol"]: s for s in ew["stocks"]}
    assert ew["r1w"] == round((cr["CCC"]["r1w"] + cr["DDD"]["r1w"]) / 2, 2)  # equal-weight line of its stocks
    assert r["missing"] == ["ZZZ"]
    assert r["buckets"]["strength_leaders"] == {"Up Sector": ["AAA"]}
    assert r["buckets"]["relative_weakness"] == {"Up Sector": ["BBB"]}
    assert "Down Sector" in r["buckets"]["stock_specific"]
    assert r["summary"]["strong_sectors"] == ["Up Sector"] and r["top_movers"][0]["signal"] == "Leader"


def test_pdf_and_excel_are_built_and_escape_ampersands():
    from backend.strategies.sector_strength_export import build_xlsx
    from backend.strategies.sector_strength_pdf import build_pdf, insights

    r = _report()
    pdf = build_pdf(r)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 5000
    assert all("&M;" not in t + x for t, x in insights(r))  # "M&M" must not turn into "M&M;"
    wb = openpyxl.load_workbook(io.BytesIO(build_xlsx(r)))
    assert wb.sheetnames[:5] == ["SUMMARY", "ROTATION", "TOP MOVERS", "LAGGARDS", "STUDY BUCKETS"]
    assert "UP SECTOR" in wb.sheetnames
    ws = wb["SUMMARY"]
    assert [c.value for c in ws[8]][:10] == ["Sector", "Index", "1W %", "# 1W", "1M %", "# 1M", "RSI D", "RSI W", "RSI M", "Verdict"]
    assert ws.cell(9, 10).value == "STRONG"


async def test_constituents_fall_back_to_the_bundled_snapshot(monkeypatch):
    from backend.services import sector_strength_service as svc

    class Refusing:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            raise svc.httpx.ConnectError("refused")

    monkeypatch.setattr(svc.httpx, "AsyncClient", Refusing)
    svc._constituents_cache.clear()
    data, source = await svc.load_constituents()
    assert source.startswith("snapshot ")
    assert {s["key"] for s in svc.SECTORS} <= set(data)
    assert any(m["symbol"] == "PNB" for m in data["psu_bank"])
    svc._constituents_cache.clear()


async def test_history_retries_rate_limit_errors(monkeypatch):
    from backend.services import sector_strength_service as svc

    calls = []

    class Flaky:
        async def get_daily_ohlc_range(self, *a):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("Angel One returned a non-JSON response (HTTP 403)")
            return closes_frame("2026-10-01", [1, 2, 3])

    monkeypatch.setattr(svc, "RETRY_BASE_S", 0)
    monkeypatch.setattr(svc, "REQUEST_PAUSE_S", 0)
    m = svc.scrip_master.ScripMatch(token="1", trading_symbol="X-EQ", exch_seg="NSE")
    df = await svc._history(Flaky(), m, dt.datetime(2026, 10, 1), dt.datetime(2026, 11, 1))
    assert len(calls) == 3 and len(df) == 3


def test_api_run_status_and_downloads(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.api import sector_strength as api
    from backend.main import app

    r = _report()
    job = api.svc.SectorJob(job_id="wk_test", as_of="2026-11-20", status="done", result=r)

    monkeypatch.setattr(api, "get_angelone_provider", lambda: None)
    monkeypatch.setattr(api.svc, "start_job", lambda provider, as_of: job)
    monkeypatch.setitem(api.svc._jobs, "wk_test", job)
    c = TestClient(app)
    body = c.post("/api/weekly-sectors/run", json={"as_of": "2026-11-20"}).json()
    assert body["status"] == "done" and body["result"]["summary"]["strong_sectors"] == ["Up Sector"]
    assert c.get("/api/weekly-sectors/run/wk_test").json()["job_id"] == "wk_test"
    assert c.get("/api/weekly-sectors/run/nope").status_code == 404
    assert c.post("/api/weekly-sectors/run", json={"as_of": "20-11-2026"}).status_code == 400
    assert c.post("/api/weekly-sectors/run", json={"as_of": "2999-01-01"}).status_code == 400
    p = c.post("/api/weekly-sectors/pdf", json=r)
    assert p.status_code == 200 and p.headers["content-type"] == "application/pdf" and p.content[:5] == b"%PDF-"
    x = c.post("/api/weekly-sectors/export", json=r)
    assert x.status_code == 200 and "weekly_sectors_" in x.headers["content-disposition"]
    assert len(c.get("/api/weekly-sectors/sectors").json()) == 21


# ---- last week, rotation and breadth (2026-11-22) ----

def test_quadrant_against_the_nifty():
    assert ss.quadrant(1, 2) == "Leading" and ss.quadrant(1, -2) == "Improving"
    assert ss.quadrant(-1, 2) == "Weakening" and ss.quadrant(-1, -2) == "Lagging" and ss.quadrant(None, 1) is None


def test_stock_breadth_and_sector_label():
    up = trend("2025-01-01", 300, 100, 0.2)
    down = trend("2025-01-01", 300, 100, -0.2)
    a, b = ss.stock_breadth(up, up.index[-1]), ss.stock_breadth(down, down.index[-1])
    assert a["above_50dma"] and a["above_200dma"] and a["high_52w"] and a["rsi_d"] > 60
    assert not b["above_50dma"] and not b["above_200dma"] and not b["high_52w"]
    young = ss.stock_breadth(trend("2025-01-01", 120, 100, 0.2), pd.Timestamp("2026-01-01"))
    assert young["above_200dma"] is None and young["high_52w"] is None  # too little history: not counted
    br = ss.sector_breadth([a, a, a, b])
    assert br == {"above_50dma": 75, "above_200dma": 75, "rsi_above_60": 75, "new_52w_highs": 3, "stocks": 4, "label": "Broad"}
    assert ss.sector_breadth([a, b, b])["label"] == "Narrow" and ss.sector_breadth([a, b])["label"] == "Moderate"


def test_report_carries_last_week_rotation_and_breadth():
    r = _report()
    by = {s["key"]: s for s in r["sectors"]}
    up = by["up"]
    assert len(up["trail"]) == ss.WEEKS_BACK + 1 and up["trail"][-1]["date"] == up["end_date"]
    assert up["quadrant"] == "Lagging"  # the benchmark here IS the up line: exactly level with it is not "ahead"
    assert by["down"]["quadrant"] == "Lagging"  # falls while the benchmark (the up line) rises
    assert up["prev"]["verdict"] == "STRONG" and up["rank_change_1w"] == up["prev"]["rank_1w"] - up["rank_1w"]
    assert up["breadth"]["stocks"] == 2 and up["breadth"]["above_50dma"] == 100  # AAA and BBB both rise
    assert by["ew"]["trail"] and by["ew"]["prev"]["verdict"] == "N/A"
    assert set(r["changes"]) == {"prev_date", "new_strong", "dropped_strong", "risers", "fallers", "quadrant_moves"}
    assert r["benchmark"]["r1d"] is not None and up["stocks"][0]["r1d"] is not None


def test_changes_name_new_and_dropped_strong_sectors(monkeypatch):
    up = trend("2021-01-01", 1300, 100, 0.12)
    as_of = up.index[-1]
    strong, mixed = {"d": 70.0, "w": 70.0, "m": 70.0}, {"d": 50.0, "w": 70.0, "m": 70.0}
    monkeypatch.setattr(ss, "rsi_levels", lambda df, day: (strong if day == as_of else mixed) if df is up else (mixed if day == as_of else strong))
    other = trend("2021-01-01", 1300, 200, 0.05)
    sectors = [{"key": "a", "label": "A", "index_label": "IA", "equal_weight": False},
               {"key": "b", "label": "B", "index_label": "IB", "equal_weight": False}]
    r = ss.build_report(as_of, sectors, {"a": up, "b": other}, {}, {"a": [], "b": []}, benchmark=up)
    assert r["changes"]["new_strong"] == ["A"] and r["changes"]["dropped_strong"] == ["B"]


def test_rank_changes_follow_a_late_surge():
    flat_then_jump = closes_frame("2026-01-01", [100.0] * 200 + [100, 103, 106, 109, 112])
    steady = closes_frame("2026-01-01", [100 * 1.004 ** i for i in range(205)])
    slow = closes_frame("2026-01-01", [100 * 1.001 ** i for i in range(205)])
    as_of = flat_then_jump.index[-1]
    sectors = [{"key": k, "label": k.upper(), "index_label": k, "equal_weight": False} for k in ("jump", "steady", "slow")]
    r = ss.build_report(as_of, sectors, {"jump": flat_then_jump, "steady": steady, "slow": slow}, {}, {k: [] for k in ("jump", "steady", "slow")})
    by = {s["key"]: s for s in r["sectors"]}
    assert by["jump"]["rank_1w"] == 1 and by["jump"]["prev"]["rank_1w"] == 3 and by["jump"]["rank_change_1w"] == 2
    assert r["changes"]["risers"] == [{"label": "JUMP", "from": 3, "to": 1}]


def test_generated_at_carries_its_time_zone():
    gen = dt.datetime.fromisoformat(_report()["generated_at"])
    assert gen.tzinfo is not None and gen.utcoffset() == dt.timedelta(0)

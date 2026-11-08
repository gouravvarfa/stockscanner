from backend.config.multi_strategy_config import Gfs50Config
from backend.strategies.gfs50 import evaluate_gfs50
from tests.strategy_helpers import make_result


def test_gfs50_qualifies_when_daily_above_50():
    signal = evaluate_gfs50(make_result(daily_rsi=50.5, weekly_rsi=65.0, monthly_rsi=70.0), Gfs50Config())
    assert signal.qualifies
    assert signal.strategy == "50 GFS"


def test_gfs50_has_no_daily_upper_limit():
    assert evaluate_gfs50(make_result(daily_rsi=80.0, weekly_rsi=65.0, monthly_rsi=70.0), Gfs50Config()).qualifies


def test_gfs50_rejects_daily_at_exactly_50():
    signal = evaluate_gfs50(make_result(daily_rsi=50.0, weekly_rsi=65.0, monthly_rsi=70.0), Gfs50Config())
    assert not signal.qualifies
    assert not signal.conditions["daily_rsi_above_min"]


def test_gfs50_rejects_weak_weekly_or_monthly():
    assert not evaluate_gfs50(make_result(daily_rsi=55.0, weekly_rsi=60.0, monthly_rsi=70.0), Gfs50Config()).qualifies
    assert not evaluate_gfs50(make_result(daily_rsi=55.0, weekly_rsi=65.0, monthly_rsi=59.0), Gfs50Config()).qualifies


def test_gfs_family_excel_export_endpoints():
    import datetime as dt
    import io

    import openpyxl
    from fastapi.testclient import TestClient

    from backend.config.strategy_config import DEFAULT_GFS50_BACKTEST_CONFIG
    from backend.main import app
    from backend.services import system_one_backtest_service as so
    from backend.strategies.system_one_backtest import SystemOneBacktestResult

    stored = so.StoredSystemOneBacktest(
        backtest_id="x50", symbol="TCS", trading_symbol="TCS-EQ", timeframe="1D",
        from_date=dt.datetime(2024, 1, 1), to_date=dt.datetime(2024, 12, 31),
        data_available_from=dt.datetime(2020, 1, 1), data_available_to=dt.datetime(2024, 12, 31),
        config=DEFAULT_GFS50_BACKTEST_CONFIG, created_at=dt.datetime(2025, 1, 1), result=SystemOneBacktestResult(),
    )
    so._store(stored)
    client = TestClient(app)
    for path, prefix, name in (("gfs50", "gfs50", "50 GFS"), ("gfs", "gfs", "GFS"), ("advanced-gfs", "advanced_gfs", "Advanced GFS")):
        resp = client.get(f"/api/{path}/backtest/x50/export")
        assert resp.status_code == 200
        assert f"{prefix}_TCS_1D_20240101_20241231.xlsx" in resp.headers["content-disposition"]
        wb = openpyxl.load_workbook(io.BytesIO(resp.content))
        assert wb.sheetnames == ["Trades", "Summary", "Year-wise", "Equity Curve"]
        assert "Holding Days" in [c.value for c in wb["Trades"][1]]
        summary = {r[0].value: r[1].value for r in wb["Summary"].iter_rows(min_row=2)}
        assert summary["Strategy"] == name
        assert summary["Setup: Daily RSI"] == "50 - 55"
    assert client.get("/api/gfs50/backtest/nope/export").status_code == 404

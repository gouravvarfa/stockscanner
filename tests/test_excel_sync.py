import asyncio
import datetime as dt

import httpx
import pytest

from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
from backend.core.config import settings
from backend.services.excel_sync import scan_sync
from backend.services.excel_sync.graph_backend import GraphWorkbookBackend, encode_share_url
from backend.services.excel_sync.naming import worksheet_name
from backend.services.excel_sync.rows import HEADERS
from backend.services.excel_sync.scan_sync import ScanSheetSync
from backend.services.scan_service import run_full_scan
from backend.strategies.types import StrategySignal
from tests.test_scan_service_value_buy_scope import FakeAngelOneProvider, _set_universe

START = dt.datetime(2026, 9, 20, 11, 0, tzinfo=dt.timezone.utc)  # 16:30 IST
SHEET = "20-Sep-2026_16-30"


class FakeWorkbook:
    def __init__(self, write_delay=0.0, fail_first_writes=0, always_fail=False):
        self.sheets: dict[str, dict[int, list]] = {}
        self.write_calls = 0
        self.write_delay, self.fail_first, self.always_fail = write_delay, fail_first_writes, always_fail

    async def create_sheet(self, name):
        if self.always_fail:
            raise RuntimeError("graph down")
        if name in self.sheets:
            return False
        self.sheets[name] = {1: list(HEADERS)}
        return True

    async def write_rows(self, name, start_row, rows):
        self.write_calls += 1
        if self.always_fail or self.fail_first > 0:
            self.fail_first -= 1
            raise RuntimeError("write failed")
        if self.write_delay:
            await asyncio.sleep(self.write_delay)
        for i, r in enumerate(rows):
            self.sheets[name][start_row + i] = r


@pytest.fixture(autouse=True)
def _clean_registry():
    scan_sync._sheet_by_scan.clear()
    yield
    scan_sync._sheet_by_scan.clear()


def _sync(wb, scan_id="scan_a", started=START, interval=0.02):
    s = ScanSheetSync(wb, scan_id, "a_group", started, flush_interval=interval)
    s.start()
    return s


def _data_rows(wb, sheet=SHEET):
    return {k: r for k, r in wb.sheets[sheet].items() if k > 1}


def test_worksheet_naming_ist_and_suffix():
    assert worksheet_name(START) == SHEET
    assert worksheet_name(START, 1) == SHEET + "_2"
    assert len(worksheet_name(START, 49)) <= 31


async def test_scan_start_creates_dated_worksheet():
    wb = FakeWorkbook()
    s = _sync(wb)
    await asyncio.sleep(0.1)
    assert list(wb.sheets) == [SHEET]
    assert wb.sheets[SHEET][1] == HEADERS
    await s.finish()


async def test_two_scans_same_minute_get_different_sheets_and_old_one_untouched():
    wb = FakeWorkbook()
    wb.sheets[SHEET] = {1: ["OLD HISTORY"], 2: ["keep me"]}  # a historical sheet from an earlier scan
    s = _sync(wb, "scan_new")
    s.on_progress("RELIANCE", True, None)
    await asyncio.sleep(0.2)
    await s.finish()
    assert wb.sheets[SHEET] == {1: ["OLD HISTORY"], 2: ["keep me"]}
    assert SHEET + "_2" in wb.sheets
    assert wb.sheets[SHEET + "_2"][2][4] == "RELIANCE"


async def test_same_scan_id_reuses_worksheet():
    wb = FakeWorkbook()
    a = _sync(wb, "scan_x")
    await asyncio.sleep(0.1)
    b = _sync(wb, "scan_x")
    await asyncio.sleep(0.1)
    assert len(wb.sheets) == 1
    await a.finish()
    await b.finish()


async def test_rows_appear_progressively_before_scan_ends():
    wb = FakeWorkbook()
    s = _sync(wb)
    for sym in ("AAA", "BBB", "CCC"):
        s.on_progress(sym, True, None)
        await asyncio.sleep(0.15)
        assert sym in [r[4] for r in _data_rows(wb).values()]  # visible NOW, scan not finished
    await s.finish()


async def test_failed_stock_instrument_type_and_no_signal_rows():
    wb = FakeWorkbook()
    s = _sync(wb)
    s.on_progress("RELIANCE", True, None)
    s.on_progress("NILKAMAL", False, "timeout")
    await s.finish()
    rows = {r[4]: r for r in _data_rows(wb).values()}
    assert rows["RELIANCE"][5] == "FUTURE" and rows["RELIANCE"][8] == "SCANNED_NO_SIGNAL"
    assert rows["NILKAMAL"][5] == "EQUITY" and rows["NILKAMAL"][8] == "DATA_UNAVAILABLE"
    assert rows["NILKAMAL"][19] == "timeout"


async def test_prd_forming_status_and_ab_fields_preserved():
    forming = {
        "timeframe": "weekly", "a_date": "2026-08-07 00:00:00", "a_low": 1640.0, "a_rsi": 73.02,
        "b_date": "2026-09-18 00:00:00", "b_low": 1844.2, "b_rsi": 64.04, "ab_distance": 6,
    }
    sig = StrategySignal(strategy="PRD", symbol="NILKAMAL", qualifies=False, signal_date=None, daily_rsi=43.2,
                         weekly_rsi=64.04, monthly_rsi=61.2, conditions={}, explanation="developing",
                         extra={"current_price": 1887.5, "forming": [forming]})
    wb = FakeWorkbook()
    s = _sync(wb)
    s.on_result("NILKAMAL", [("PRD Forming", sig)])
    s.on_progress("NILKAMAL", True, None)
    await s.finish()
    row = next(iter(_data_rows(wb).values()))
    assert row[6] == "PRD" and row[7] == "WEEKLY" and row[8] == "PRD_FORMING"
    assert tuple(row[12:19]) == ("2026-08-07", "2026-09-18", 1640.0, 1844.2, 73.02, 64.04, 6)
    assert row[5] == "EQUITY"


async def test_retry_after_failed_write_does_not_duplicate_rows():
    wb = FakeWorkbook(fail_first_writes=2)
    s = _sync(wb)
    for sym in ("AAA", "BBB", "CCC"):
        s.on_progress(sym, True, None)
    await s.finish()
    syms = [r[4] for r in _data_rows(wb).values()]
    assert sorted(syms) == ["AAA", "BBB", "CCC"]
    assert s.failures >= 1


async def test_rows_are_batched_not_one_request_per_stock():
    wb = FakeWorkbook()
    s = _sync(wb, interval=0.2)
    for i in range(30):
        s.on_progress("S" + str(i), True, None)
    await s.finish()
    assert len(_data_rows(wb)) == 30
    assert wb.write_calls <= 3


async def test_excel_failure_does_not_stop_scanner(monkeypatch):
    _set_universe(monkeypatch, ["AAA", "BBB", "CCC"])
    s = _sync(FakeWorkbook(always_fail=True))
    out = await run_full_scan(FakeAngelOneProvider(), DEFAULT_STRATEGY_CONFIG, stock_history_days=70,
                              on_progress=s.on_progress, on_result=s.on_result)
    assert out.stocks_scanned == 3 and out.stocks_failed == 0
    await s.finish(timeout=0.5)


async def test_scan_does_not_wait_for_slow_excel(monkeypatch):
    _set_universe(monkeypatch, ["S" + str(i) for i in range(40)])
    wb = FakeWorkbook(write_delay=60.0)  # every Excel write is extremely slow
    s = _sync(wb)
    t0 = asyncio.get_running_loop().time()
    out = await run_full_scan(FakeAngelOneProvider(), DEFAULT_STRATEGY_CONFIG, stock_history_days=70,
                              on_progress=s.on_progress, on_result=s.on_result)
    assert asyncio.get_running_loop().time() - t0 < 30  # never waits for the 60s Excel writes
    assert out.stocks_scanned == 40
    s._task.cancel()


async def test_graph_backend_creates_sheet_headers_and_rows(monkeypatch):
    monkeypatch.setattr(settings, "onedrive_workbook_url", "https://1drv.ms/x/c/abc/xyz")
    monkeypatch.setattr(settings, "ms_graph_client_id", "cid")
    monkeypatch.setattr(settings, "ms_graph_refresh_token", "rt")
    paths = []

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        paths.append(p)
        if "oauth2" in p:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if "/shares/" in p:
            return httpx.Response(200, json={"id": "ITEM", "parentReference": {"driveId": "DRV"}})
        if p.endswith("/createSession"):
            return httpx.Response(200, json={"id": "SESSION"})
        if req.method == "GET" and "/worksheets/" in p:
            return httpx.Response(404, json={})
        return httpx.Response(200, json={})

    b = GraphWorkbookBackend(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await b.create_sheet(SHEET) is True
    await b.write_rows(SHEET, 2, [["x"] * len(HEADERS)])
    assert any("/worksheets/add" in p for p in paths)
    assert sum("range(address=" in p for p in paths) == 2  # header row + data row
    assert encode_share_url("https://1drv.ms/x/c/abc/xyz").startswith("u!")

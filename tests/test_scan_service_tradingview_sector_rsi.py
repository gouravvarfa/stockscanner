import datetime as dt

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
from backend.core.database import Base
from backend.models.tradingview_signal import TradingViewSignal
from backend.services.scan_service import run_full_scan


def _ohlc(n, base=100.0, step=0.0, start="2023-01-02"):
    idx = pd.bdate_range(start, periods=n)
    closes = [base + step * i for i in range(n)]
    return pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000] * n},
        index=idx,
    )


class _ShortHistoryProvider:
    """
    Universe of one Banks stock. The sector index history returned by
    Tapetide is deliberately short (~127 bars, Tapetide's real ~6-month
    truncation cap) so weekly RSI is computable but monthly RSI is NOT —
    exactly the gap a TradingView SECTOR_RSI fallback is meant to fill. No
    Angel One provider is passed to run_full_scan in this test, so the
    Angel One override path can never supply it either.
    """

    async def get_universe(self, index_slug="nifty-200"):
        stocks = [{"symbol": "STRONGBANKSTOCK", "sector": "Banks"}]
        return {"stocks": stocks, "requested": 1, "returned": 1, "complete": True, "sources": [], "note": None}

    async def get_index_ohlc(self, index_name, interval="3m"):
        if index_name == "Nifty Bank":
            return _ohlc(127, base=100.0, step=1.5)  # strong uptrend, high RSI, ~6mo (no monthly RSI)
        return _ohlc(127, base=100.0, step=0.05)  # NIFTY 50 benchmark: mild rise

    async def get_stock_ohlcv(self, symbol, days=800):
        return _ohlc(70, base=100.0, step=0.1)

    async def get_sector_performance(self, *a, **kw): raise NotImplementedError
    async def screen_technical(self, *a, **kw): raise NotImplementedError
    async def get_batch_quotes(self, *a, **kw): raise NotImplementedError


def _make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


async def test_tradingview_sector_rsi_fallback_fills_gap_when_db_provided():
    db = _make_session()
    db.add(
        TradingViewSignal(
            dedupe_key="test-key-1",
            source="tradingview",
            symbol="NIFTY BANK",
            strategy="SECTOR_RSI",
            signal_timeframe="1M",
            signal_date=dt.datetime(2026, 9, 1),
            weekly_rsi=None,
            monthly_rsi=74.0,
            raw_payload={},
        )
    )
    db.commit()

    outcome = await run_full_scan(_ShortHistoryProvider(), DEFAULT_STRATEGY_CONFIG, stock_history_days=70, db=db)

    banks = outcome.sector_analyses["Banks"]
    assert banks.monthly.rsi == 74.0
    assert banks.monthly_data_source == "TRADINGVIEW"


async def test_tradingview_sector_rsi_fallback_skipped_when_no_db_provided():
    # Without a db session (e.g. every existing test in this suite that
    # calls run_full_scan directly), the TradingView lookup is skipped
    # entirely and behavior is byte-for-byte identical to before this
    # feature existed.
    outcome = await run_full_scan(_ShortHistoryProvider(), DEFAULT_STRATEGY_CONFIG, stock_history_days=70)

    banks = outcome.sector_analyses["Banks"]
    assert banks.monthly.rsi is None
    assert banks.monthly_data_source == "UNAVAILABLE"


async def test_tradingview_sector_rsi_ignored_when_no_matching_signal_stored():
    db = _make_session()  # empty — no TradingViewSignal rows at all

    outcome = await run_full_scan(_ShortHistoryProvider(), DEFAULT_STRATEGY_CONFIG, stock_history_days=70, db=db)

    banks = outcome.sector_analyses["Banks"]
    assert banks.monthly.rsi is None
    assert banks.monthly_data_source == "UNAVAILABLE"

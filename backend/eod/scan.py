"""Cup Breakout and Value Buy over every NSE stock from the bhavcopy history (2026-11-23) - no Angel One calls.

Uses the SAME rules as the live scans (backend/strategies/cup.py detect_cup, the Value Buy evaluation on
screeners.stock_analysis), so results match; only the data source differs (NSE end-of-day files, split/bonus
adjusted). Cup sees the whole history (up to 20 years), so cups longer than 10 years can be found.
Output: two small JSON files in the same shape as the live scan results.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
from pathlib import Path

import pandas as pd

from backend.config.cup_config import DEFAULT_CUP_CONFIG
from backend.screeners.stock_analysis import analyze_stock
from backend.services import universe_loader
from backend.services.cup_scan_service import _cup_result_to_signal
from backend.strategies.cup import QUALIFYING_STATUSES, detect_cup
from backend.strategies.value_buy import evaluate_value_buy

logger = logging.getLogger("scanner.eod")

MIN_DAILY_BARS = 60
VALUE_BUY_DAYS = 1500  # the live scan's MONTHLY_RSI_LOOKBACK_DAYS
STALE_DAYS = 10  # a stock with no trade in the last 10 days (suspended/delisted) is skipped


def _signal_json(sig) -> dict:
    from backend.services.serializers import strategy_signal_out

    return strategy_signal_out(sig).model_dump(mode="json")


def run(store: dict[str, pd.DataFrame], strong_map: dict[str, str] | None = None, strong_sectors: list | None = None) -> tuple[dict, dict]:
    from backend.services.config_store import get_current_config, get_current_multi_strategy_config

    config = get_current_config()
    vb_config = get_current_multi_strategy_config().value_buy
    cup_config = DEFAULT_CUP_CONFIG.model_copy(update={"history_years": 25}) if hasattr(DEFAULT_CUP_CONFIG, "model_copy") else DEFAULT_CUP_CONFIG
    last_day = max(df.index[-1] for df in store.values())
    started = dt.datetime.utcnow()
    cup_results, vb_signals, failed = [], [], []
    scanned = 0
    universe = set(universe_loader.load_all_nse_universe())  # the live Cup scan's list: NSE equities, no ETFs
    for sym, df in store.items():
        if sym not in universe:
            continue
        if len(df) < MIN_DAILY_BARS or (last_day - df.index[-1]).days > STALE_DAYS:
            continue
        scanned += 1
        if scanned % 250 == 0:
            logger.info("EOD scan: %d stocks done", scanned)
        try:
            cup = detect_cup(df, cup_config)
            if cup["status"] in QUALIFYING_STATUSES:
                cup["symbol"] = sym
                cup["company_name"] = universe_loader.company_name_for(sym) or sym
                cup["instrument_type"] = "EQUITY"
                cup["updated_at"] = started.isoformat()
                cup["data_source"] = "NSE_EOD"
                cup_results.append(cup)
        except Exception as exc:  # noqa: BLE001 - one bad stock never stops the scan
            failed.append({"symbol": sym, "error": f"cup: {exc}"})
        try:
            tail = df[df.index >= df.index[-1] - pd.Timedelta(days=VALUE_BUY_DAYS)]
            result = analyze_stock(sym, tail, config)
            if result is not None:
                sig = evaluate_value_buy(result, tail, vb_config)
                if sig.qualifies:
                    sig.extra["current_price"] = result.current_price
                    sig.extra["data_source"] = "NSE_EOD"
                    vb_signals.append(_signal_json(sig))
        except Exception as exc:  # noqa: BLE001
            failed.append({"symbol": sym, "error": f"value_buy: {exc}"})
    finished = dt.datetime.utcnow()
    common = {"data_as_of": last_day.date().isoformat(), "generated_at": finished.isoformat() + "Z", "source": "NSE bhavcopy (end of day)"}
    cup_payload = {**common, "started_at": started.isoformat(), "finished_at": finished.isoformat(),
                   "execution_seconds": (finished - started).total_seconds(), "stocks_scanned": scanned,
                   "stocks_failed": len(failed), "failed_symbols": [f["symbol"] for f in failed if f["error"].startswith("cup")],
                   "results": cup_results}
    vb_payload = {**common, "started_at": started.isoformat(), "finished_at": finished.isoformat(),
                  "stocks_scanned": scanned, "stocks_failed": len([f for f in failed if f["error"].startswith("value_buy")]),
                  "strategies": {"Value Buy": vb_signals}, "strong_symbols": strong_map or {}, "strong_sectors": strong_sectors or []}
    logger.info("EOD scan: %d stocks, %d cups, %d value buy, %d failed", scanned, len(cup_results), len(vb_signals), len(failed))
    return cup_payload, vb_payload


def write(out_dir: Path, cup_payload: dict, vb_payload: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cup.json").write_text(json.dumps(cup_payload, separators=(",", ":"), default=str), encoding="utf-8")
    (out_dir / "value_buy.json").write_text(json.dumps(vb_payload, separators=(",", ":"), default=str), encoding="utf-8")

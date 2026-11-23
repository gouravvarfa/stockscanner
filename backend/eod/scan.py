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


def monthly_rsi_now(df: pd.DataFrame, length: int = 14) -> float | None:
    """Monthly RSI(14) including the CURRENT month's candle as it stands today (2026-11-23, user: 'aaj ki candle' -
    is the stock near the 40 support today, not at last month's close). Wilder smoothing, like charting apps."""
    closes = df["close"].resample("ME").last().dropna()
    if len(closes) < length + 1:
        return None
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean().iloc[-1]
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    return float(100 - 100 / (1 + avg_gain / avg_loss))


def daily_retracement(df: pd.DataFrame) -> dict | None:
    """The daily pullback inside the last up-swing (2026-11-23, the user's PFC example: low 310.30 -> high 346.37,
    then a dip to ~319 = the 78.6% zone). Swings use 5 daily bars on each side, like a chart's Fibonacci tool. The
    swing high is the last 5-bar high; the swing low is the last 5-bar low before it. `deepest_pct` is the lowest low
    since the high as a share of the swing (0% = at the high, 100% = back at the low); `pct` is today's close.
    The 78% tag: the deepest pullback reached 74-82% (around 78.6%) without breaking the swing low."""
    from backend.strategies.gann_time import find_pivots

    tail = df.iloc[-300:]
    high, low = tail["high"].to_numpy(float), tail["low"].to_numpy(float)
    piv = find_pivots(high, low, k=5)
    highs = [i for i, k in piv if k == "H"]
    if not highs:
        return None
    hi = highs[-1]
    lows_before = [i for i, k in piv if k == "L" and i < hi]
    if not lows_before:
        return None
    lo = lows_before[-1]
    h, l = float(high[hi]), float(low[lo])
    if h <= l:
        return None
    rng = h - l
    close = float(tail["close"].iloc[-1])
    deepest = float(low[hi + 1:].min()) if hi + 1 < len(low) else close
    deep_pct = (h - deepest) / rng * 100.0
    return {"pct": round((h - close) / rng * 100.0, 1), "deepest_pct": round(deep_pct, 1),
            "swing_high": round(h, 2), "swing_high_date": tail.index[hi].date().isoformat(),
            "swing_low": round(l, 2), "swing_low_date": tail.index[lo].date().isoformat(),
            "level_786": round(h - 0.786 * rng, 2), "fib78": 74.0 <= deep_pct <= 82.0 and deepest > l}


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
    cup_results, vb_signals, failed, support = [], [], [], []
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
                rsi_now = monthly_rsi_now(df)
                if rsi_now is not None and vb_config.monthly_rsi_support_min <= rsi_now <= vb_config.monthly_rsi_support_max:
                    ret = daily_retracement(df)
                    support.append({
                        "symbol": sym, "company_name": universe_loader.company_name_for(sym) or sym,
                        "price": round(float(result.current_price), 2), "daily_rsi": result.daily.rsi,
                        "weekly_rsi": result.weekly.rsi, "monthly_rsi": round(rsi_now, 2),
                        "monthly_rsi_last_close": result.monthly.rsi,
                        "conditions": sig.conditions, "value_buy": bool(sig.qualifies), "retracement": ret,
                    })
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
                  "strategies": {"Value Buy": vb_signals}, "support_zone": support, "strong_symbols": strong_map or {}, "strong_sectors": strong_sectors or []}
    logger.info("EOD scan: %d stocks, %d cups, %d value buy, %d failed", scanned, len(cup_results), len(vb_signals), len(failed))
    return cup_payload, vb_payload


def write(out_dir: Path, cup_payload: dict, vb_payload: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cup.json").write_text(json.dumps(cup_payload, separators=(",", ":"), default=str), encoding="utf-8")
    (out_dir / "value_buy.json").write_text(json.dumps(vb_payload, separators=(",", ":"), default=str), encoding="utf-8")

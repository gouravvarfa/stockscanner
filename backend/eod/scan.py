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


def falling_drives(bars: pd.DataFrame, k: int, recent_bars: int, min_gap: int = 5) -> dict | None:
    """The 3-5 Drive setup (2026-11-23, the user's course: Bollinger Bands 20,2 on the chart). A drive is a swing low
    (k bars each side) that reaches the LOWER band (within BAND_TOUCH); the drives come one after another, each lower
    than the one before, with a bounce between. The last drive must be recent (within `recent_bars`) with price
    above it. `mid_reclaim`: since the last drive price has closed back above the middle band - the entry signal."""
    from backend.strategies.gann_time import find_pivots

    if len(bars) < 4 * k + 30:
        return None
    close = bars["close"]
    mid = close.rolling(20).mean()
    lower = (mid - 2 * close.rolling(20).std(ddof=0)).to_numpy()
    high, low = bars["high"].to_numpy(float), bars["low"].to_numpy(float)
    piv = find_pivots(high, low, k=k)
    lows = [(i, float(low[i])) for i, kind in piv if kind == "L" and lower[i] == lower[i] and low[i] <= lower[i] * (1 + BAND_TOUCH)]
    if len(lows) < 3:
        return None
    last_i, last_p = lows[-1]
    if len(bars) - 1 - last_i > recent_bars or float(close.iloc[-1]) <= last_p:
        return None
    mid_arr = mid.to_numpy()

    def proper_bounce(i: int, j: int) -> bool:
        # a real up-and-down between two drives (user): at least min_gap candles apart, and price climbed back to the
        # MIDDLE band somewhere in between before falling to the lower band again
        if j - i < min_gap:
            return False
        return any(high[t] >= mid_arr[t] for t in range(i + 1, j) if mid_arr[t] == mid_arr[t])

    run = [lows[-1]]
    for i, p in reversed(lows[:-1]):
        if p > run[-1][1] and proper_bounce(i, run[-1][0]):
            run.append((i, p))
        else:
            break
    if len(run) < 3:
        return None
    run.reverse()
    after = close.iloc[last_i + 1:]
    mids = mid.iloc[last_i + 1:]
    reclaim = bool(len(after) and (after > mids).any() and float(close.iloc[-1]) > float(mid.iloc[-1]))
    return {"count": min(len(run), 9), "mid_reclaim": reclaim,
            "lows": [{"date": bars.index[i].date().isoformat(), "price": round(p, 2)} for i, p in run[-6:]]}


BAND_TOUCH = 0.01  # a low within 1% of the lower Bollinger band counts as touching it


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


def run(store: dict[str, pd.DataFrame], strong_map: dict[str, str] | None = None, strong_sectors: list | None = None,
        sector_info: dict | None = None) -> tuple[dict, dict]:
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
                cup["sectors"] = [x for x in ((sector_info or {}).get("members", {}).get(sym) or []) if x["status"] == "strong"]
                cup_results.append(cup)
        except Exception as exc:  # noqa: BLE001 - one bad stock never stops the scan
            failed.append({"symbol": sym, "error": f"cup: {exc}"})
        try:
            tail = df[df.index >= df.index[-1] - pd.Timedelta(days=VALUE_BUY_DAYS)]
            result = analyze_stock(sym, tail, config)
            if result is not None:
                sig = evaluate_value_buy(result, tail, vb_config)
                rsi_now = monthly_rsi_now(df)
                last_month = df[df.index >= df.index[-1].to_period("M").to_timestamp()]
                month_open = float(last_month["open"].iloc[0])
                month_green = float(last_month["close"].iloc[-1]) > month_open  # this month's candle so far
                sector_tags = (sector_info or {}).get("members", {}).get(sym) if sector_info is not None else None
                if (rsi_now is not None and vb_config.monthly_rsi_support_min <= rsi_now <= vb_config.monthly_rsi_support_max
                        and month_green and (sector_info is None or sector_tags)):
                    ret = daily_retracement(df)
                    weekly_bars = df.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
                    drives = {"daily": falling_drives(df.iloc[-400:], 3, 30, 5), "weekly": falling_drives(weekly_bars.iloc[-200:], 2, 10, 3)}
                    support.append({
                        "sectors": sector_tags or [],
                        "drives": drives,
                        "symbol": sym, "company_name": universe_loader.company_name_for(sym) or sym,
                        "price": round(float(result.current_price), 2), "daily_rsi": result.daily.rsi,
                        "weekly_rsi": result.weekly.rsi, "monthly_rsi": round(rsi_now, 2),
                        "monthly_rsi_last_close": result.monthly.rsi,
                        "month_open": round(month_open, 2), "month_change_pct": round((float(last_month["close"].iloc[-1]) / month_open - 1) * 100, 2),
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
                   "results": cup_results, "sector_status": (sector_info or {}).get("sectors", [])}
    vb_payload = {**common, "started_at": started.isoformat(), "finished_at": finished.isoformat(),
                  "stocks_scanned": scanned, "stocks_failed": len([f for f in failed if f["error"].startswith("value_buy")]),
                  "strategies": {"Value Buy": vb_signals}, "support_zone": support, "strong_symbols": strong_map or {}, "strong_sectors": strong_sectors or [],
                  "sector_status": (sector_info or {}).get("sectors", [])}
    logger.info("EOD scan: %d stocks, %d cups, %d value buy, %d failed", scanned, len(cup_results), len(vb_signals), len(failed))
    return cup_payload, vb_payload



def run_setup(store: dict[str, pd.DataFrame], sector_info: dict) -> dict:
    """The Setup Scanner from end-of-day data (2026-11-23, user: its Run Scan was slow through Angel One): every stock
    of today's STRONG sectors (all of each sector's NSE stocks), every setup except Value Buy - the same strategy code
    as the live scan (scan_service._evaluate_all_strategies), so the result has the same shape."""
    from backend.services import serializers
    from backend.services.config_store import get_current_config, get_current_multi_strategy_config
    from backend.services.scan_service import ScanOutcome, _evaluate_all_strategies
    from backend.services.scan_service import ALL_SIGNAL_STRATEGY_NAMES as STRATEGY_NAMES

    config = get_current_config()
    multi = get_current_multi_strategy_config()
    strong = [x for x in sector_info.get("sectors", []) if x["status"] == "strong"]
    strong_keys = {x["key"] for x in strong}
    symbols = sorted(sym for sym, tags in sector_info.get("members", {}).items() if any(t["key"] in strong_keys for t in tags))
    started = dt.datetime.utcnow()
    signals: dict[str, list] = {name: [] for name in STRATEGY_NAMES}
    results, failed = [], []
    for sym in symbols:
        df = store.get(sym)
        if df is None or len(df) < MIN_DAILY_BARS:
            failed.append(sym)
            continue
        tail = df[df.index >= df.index[-1] - pd.Timedelta(days=VALUE_BUY_DAYS)]
        try:
            res = analyze_stock(sym, tail, config)
            if res is None:
                failed.append(sym)
                continue
            results.append(res)
            for name, sig in _evaluate_all_strategies(res, tail, multi, False):
                sig.extra.setdefault("current_price", res.current_price)
                sig.extra["data_source"] = "NSE_EOD"
                signals.setdefault(name, []).append(sig)
        except Exception:  # noqa: BLE001 - one bad stock never stops the scan
            failed.append(sym)
    qualifying = [r for r in results if r.meets_weekly_rsi_band and r.meets_monthly_rsi_min and not r.disqualified_by_divergence]
    qualifying.sort(key=lambda r: r.score.total_score, reverse=True)
    finished = dt.datetime.utcnow()
    outcome = ScanOutcome(
        started_at=started, finished_at=finished, execution_seconds=(finished - started).total_seconds(),
        universe_requested=len(symbols), universe_returned=len(symbols), universe_complete=True,
        value_buy_universe_requested=0, value_buy_universe_returned=0, stocks_scanned=len(results),
        stocks_failed=len(failed), failed_symbols=failed, all_results=results, qualifying_results=qualifying,
        top10=qualifying[:10], top3=qualifying[:3], best=qualifying[0] if qualifying else None,
        strategy_signals=signals, data_source_summary={"NSE_EOD": len(results)},
    )
    payload = serializers.scan_outcome_out(outcome).model_dump(mode="json")
    members = sector_info.get("members", {})
    payload["strong_sectors"] = [{"key": x["key"], "label": x["label"], "index": x.get("index") or x["label"], "rsi": x["rsi"],
                                  "stocks": sum(1 for tags in members.values() if any(t["key"] == x["key"] for t in tags))} for x in strong]
    last_day = max(df.index[-1] for df in store.values())
    payload.update({"strong_as_of": last_day.date().isoformat(), "data_as_of": last_day.date().isoformat(),
                    "generated_at": finished.isoformat() + "Z", "source": "NSE bhavcopy (end of day)"})
    logger.info("EOD setup scan: %d strong-sector stocks, %d signals", len(results), sum(len(v) for v in signals.values()))
    return payload


def write_candles(out_dir: Path, store: dict[str, pd.DataFrame], symbols: set[str]) -> int:
    """Chart data for the listed stocks (2026-11-23, user: charts opened slowly through Render/Angel): the last ~3
    years of daily candles plus the full monthly history, as small JSON files the site serves directly. Rows are
    [unix seconds, open, high, low, close, volume]."""
    d = out_dir / "candles"
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.json"):
        if old.stem not in symbols:
            old.unlink()

    def rows(frame: pd.DataFrame) -> list:
        return [[int(ts.timestamp()), round(float(o), 2), round(float(h), 2), round(float(l), 2), round(float(c), 2), int(v)]
                for ts, o, h, l, c, v in zip(frame.index, frame["open"], frame["high"], frame["low"], frame["close"], frame["volume"].fillna(0))]

    n = 0
    for sym in symbols:
        df = store.get(sym)
        if df is None or df.empty:
            continue
        daily = df[df.index >= df.index[-1] - pd.Timedelta(days=3 * 366)]
        monthly = df.resample("MS").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["close"])
        (d / f"{sym}.json").write_text(json.dumps({"symbol": sym, "as_of": df.index[-1].date().isoformat(),
                                                   "daily": rows(daily), "monthly": rows(monthly)}, separators=(",", ":")), encoding="utf-8")
        n += 1
    return n


def write(out_dir: Path, cup_payload: dict, vb_payload: dict, store: dict[str, pd.DataFrame] | None = None,
          setup_payload: dict | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if setup_payload is not None:
        (out_dir / "setup.json").write_text(json.dumps(setup_payload, separators=(",", ":"), default=str), encoding="utf-8")
    if store is not None:
        syms = {r["symbol"] for r in cup_payload.get("results", [])} | {r["symbol"] for r in vb_payload.get("support_zone", [])}
        if setup_payload is not None:
            syms |= {sig["symbol"] for sigs in setup_payload.get("strategies", {}).values() for sig in sigs}
        write_candles(out_dir, store, syms)
    (out_dir / "cup.json").write_text(json.dumps(cup_payload, separators=(",", ":"), default=str), encoding="utf-8")
    (out_dir / "value_buy.json").write_text(json.dumps(vb_payload, separators=(",", ":"), default=str), encoding="utf-8")

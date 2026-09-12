"""
One-off raw test: Healthcare sector stocks, data pulled from Yahoo Finance
(not Tapetide/Angel One), run through the REAL, unmodified strategy engine
(analyze_sector, analyze_stock, evaluate_all_strategies) to see whether
richer (non-truncated) historical data changes sector/stock qualification.

This is a standalone diagnostic script — it does NOT touch the running app,
its providers, or its config. Output: an Excel file on the Desktop.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))

from backend.config.multi_strategy_config import DEFAULT_MULTI_STRATEGY_CONFIG
from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
from backend.screeners.stock_analysis import analyze_stock
from backend.sector_analysis.engine import analyze_sector, compute_benchmark_stats
from backend.strategies.runner import evaluate_all_strategies

HEALTHCARE_STOCKS = [
    "ABBOTINDIA", "AJANTPHARM", "ALKEM", "AUROPHARMA", "BIOCON", "CIPLA",
    "DIVISLAB", "DRREDDY", "GLAND", "GLENMARK", "IPCALAB", "LAURUSLABS",
    "LUPIN", "MANKIND", "PPLPHARMA", "SAILIFE", "SUNPHARMA", "TORNTPHARM",
    "WOCKPHARMA", "ZYDUSLIFE",
]

# Yahoo has no exact "Nifty Healthcare" series with enough history; Nifty
# Pharma (^CNXPHARMA) is NSE's closest, long-established healthcare-sector
# index and is used here as an explicit proxy — labeled as such throughout.
SECTOR_INDEX_TICKER = "^CNXPHARMA"
SECTOR_LABEL = "Nifty Pharma (Yahoo proxy for Healthcare)"
BENCHMARK_TICKER = "^NSEI"


def fetch_ohlcv(ticker: str, period: str = "2y") -> pd.DataFrame:
    raw = yf.Ticker(ticker).history(period=period, interval="1d")
    if raw.empty:
        return raw
    raw = raw.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    raw.index = raw.index.tz_localize(None)
    raw = raw[["open", "high", "low", "close", "volume"]]
    # Yahoo sometimes includes today's row with a NaN close before that
    # stock's data is fully populated for the day — drop any incomplete
    # trailing rows rather than let RSI silently compute as None off a NaN tail.
    return raw.dropna(subset=["close"])


def main() -> None:
    print("Fetching NIFTY 50 benchmark from Yahoo...")
    nifty_ohlc = fetch_ohlcv(BENCHMARK_TICKER)
    print(f"  {len(nifty_ohlc)} daily bars, {nifty_ohlc.index[0].date()} -> {nifty_ohlc.index[-1].date()}")

    print(f"Fetching sector index ({SECTOR_LABEL}) from Yahoo...")
    sector_ohlc = fetch_ohlcv(SECTOR_INDEX_TICKER)
    print(f"  {len(sector_ohlc)} daily bars, {sector_ohlc.index[0].date()} -> {sector_ohlc.index[-1].date()}")

    benchmark = compute_benchmark_stats(nifty_ohlc)
    sector_config = DEFAULT_STRATEGY_CONFIG.sector_rsi

    # analyze_sector() normally resolves the NSE index name from the
    # Tapetide sector label via resolve_sector_index("Healthcare") ->
    # "Nifty Healthcare"; here we call the underlying stats directly since
    # we're deliberately feeding it a different (Yahoo) index series.
    from backend.sector_analysis.engine import _last_completed_return_pct, _rsi_last, _weekly_stats_from, _monthly_stats_from, TimeframeStats, SectorAnalysis

    daily_stats = TimeframeStats(_last_completed_return_pct(sector_ohlc["close"]), _rsi_last(sector_ohlc["close"]))
    weekly_stats = _weekly_stats_from(sector_ohlc)
    monthly_stats = _monthly_stats_from(sector_ohlc)

    daily_vs_nifty = daily_stats.return_pct - benchmark.daily.return_pct if daily_stats.return_pct is not None and benchmark.daily.return_pct is not None else None
    weekly_vs_nifty = weekly_stats.return_pct - benchmark.weekly.return_pct if weekly_stats.return_pct is not None and benchmark.weekly.return_pct is not None else None
    monthly_vs_nifty = monthly_stats.return_pct - benchmark.monthly.return_pct if monthly_stats.return_pct is not None and benchmark.monthly.return_pct is not None else None
    available_rs = [v for v in (daily_vs_nifty, weekly_vs_nifty, monthly_vs_nifty) if v is not None]
    outperforms = len(available_rs) >= 2 and all(v > 0 for v in available_rs)

    daily_ok = daily_stats.rsi is not None and daily_stats.rsi > sector_config.daily_min
    weekly_ok = weekly_stats.rsi is None or weekly_stats.rsi > sector_config.weekly_min
    monthly_ok = monthly_stats.rsi is None or monthly_stats.rsi > sector_config.monthly_min
    has_confirmation = weekly_stats.rsi is not None or monthly_stats.rsi is not None
    higher_strong = (weekly_stats.rsi is not None and weekly_stats.rsi > sector_config.weekly_min
                      and monthly_stats.rsi is not None and monthly_stats.rsi > sector_config.monthly_min)
    daily_threshold = sector_config.daily_min_relaxed if higher_strong else sector_config.daily_min
    daily_ok_relaxed = daily_stats.rsi is not None and daily_stats.rsi > daily_threshold
    meets_rsi = daily_ok_relaxed and weekly_ok and monthly_ok and has_confirmation

    sector_row = {
        "sector": SECTOR_LABEL,
        "daily_rsi": daily_stats.rsi, "weekly_rsi": weekly_stats.rsi, "monthly_rsi": monthly_stats.rsi,
        "daily_vs_nifty": daily_vs_nifty, "weekly_vs_nifty": weekly_vs_nifty, "monthly_vs_nifty": monthly_vs_nifty,
        "outperforms_nifty": outperforms, "meets_rsi_thresholds": meets_rsi,
        "qualifies": outperforms and meets_rsi,
        "data_points_used": len(sector_ohlc),
    }
    print("\nSector analysis:")
    for k, v in sector_row.items():
        print(f"  {k}: {v}")

    print(f"\nFetching {len(HEALTHCARE_STOCKS)} Healthcare stocks from Yahoo...")
    all_results = []
    strategy_rows: dict[str, list[dict]] = {name: [] for name in
        ["Strategy One", "GFS", "Advanced GFS", "PRD", "NRD", "Value Buy"]}
    failed = []

    for symbol in HEALTHCARE_STOCKS:
        ticker = f"{symbol}.NS"
        try:
            ohlcv = fetch_ohlcv(ticker)
            if ohlcv.empty or len(ohlcv) < 60:
                failed.append((symbol, "insufficient/no data from Yahoo"))
                continue
            result = analyze_stock(symbol, "Healthcare", ohlcv, None, DEFAULT_STRATEGY_CONFIG)
            if result is None:
                failed.append((symbol, "analyze_stock returned None"))
                continue
            all_results.append(result)
            signals = evaluate_all_strategies(result, ohlcv, DEFAULT_MULTI_STRATEGY_CONFIG)
            for name, signal in signals.items():
                strategy_rows[name].append({
                    "symbol": signal.symbol,
                    "qualifies": signal.qualifies,
                    "daily_rsi": signal.daily_rsi,
                    "weekly_rsi": signal.weekly_rsi,
                    "monthly_rsi": signal.monthly_rsi,
                    "signal_date": signal.signal_date,
                    "divergence_timeframes": ", ".join(signal.extra.get("divergence_timeframes", []) or []),
                    "score": signal.extra.get("score"),
                    "explanation": signal.explanation,
                    "data_points_used": len(ohlcv),
                })
            print(f"  {symbol}: OK ({len(ohlcv)} bars, D={result.daily.rsi}, W={result.weekly.rsi}, M={result.monthly.rsi})")
        except Exception as exc:  # noqa: BLE001
            failed.append((symbol, str(exc)))
            print(f"  {symbol}: FAILED - {exc}")

    print(f"\n{len(all_results)}/{len(HEALTHCARE_STOCKS)} stocks processed successfully.")
    if failed:
        print("Failed:", failed)

    # ---- Write Excel ----
    desktop = Path.home() / "Desktop"
    out_path = desktop / "healthcare_yahoo_test.xlsx"

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pd.DataFrame([sector_row]).to_excel(writer, sheet_name="Sector Overview", index=False)

        overview_rows = [{
            "symbol": r.symbol, "sector": r.sector, "current_price": r.current_price,
            "daily_rsi": r.daily.rsi, "weekly_rsi": r.weekly.rsi, "monthly_rsi": r.monthly.rsi,
            "score": r.score.total_score, "classification": r.score.classification, "bias": r.score.bias,
            "meets_weekly_rsi_band": r.meets_weekly_rsi_band, "meets_monthly_rsi_min": r.meets_monthly_rsi_min,
            "disqualified_by_divergence": r.disqualified_by_divergence,
        } for r in all_results]
        pd.DataFrame(overview_rows).to_excel(writer, sheet_name="All Stocks Overview", index=False)

        for name, rows in strategy_rows.items():
            df = pd.DataFrame(rows)
            sheet_name = name[:31]  # Excel sheet name limit
            df.to_excel(writer, sheet_name=sheet_name, index=False)

        if failed:
            pd.DataFrame(failed, columns=["symbol", "reason"]).to_excel(writer, sheet_name="Failed", index=False)

    print(f"\nExcel written to: {out_path}")


if __name__ == "__main__":
    main()

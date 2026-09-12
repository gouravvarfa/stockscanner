import pandas as pd

from backend.config.strategy_config import SectorRSIConfig
from backend.sector_analysis.engine import analyze_sector, compute_benchmark_stats


def _ohlc(closes, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
         "close": closes, "volume": [1000] * len(closes)},
        index=idx,
    )


def _strong_uptrend(n, start="2024-01-01", base=100.0, step=1.0):
    return _ohlc([base + step * i for i in range(n)], start=start)


def _flat_benchmark(n, start="2024-01-01"):
    # Roughly flat/mildly positive so sector return comfortably beats it.
    return _ohlc([100 + 0.05 * i for i in range(n)], start=start)


def test_sector_qualifies_on_daily_weekly_when_monthly_genuinely_unavailable():
    # ~127 bars ≈ Tapetide's real ~6-month cap — not enough for monthly RSI(14).
    sector_ohlc = _strong_uptrend(127, base=100.0, step=1.5)
    benchmark_ohlc = _flat_benchmark(127)
    benchmark = compute_benchmark_stats(benchmark_ohlc)

    analysis = analyze_sector("Banks", sector_ohlc, benchmark, SectorRSIConfig(), angelone_ohlc_override=None)

    assert analysis.monthly.rsi is None
    assert analysis.monthly_data_source == "UNAVAILABLE"
    # Daily/weekly strongly outperforming + high RSI -> should still qualify.
    assert analysis.daily.rsi is not None and analysis.daily.rsi > 60
    assert analysis.weekly.rsi is not None and analysis.weekly.rsi > 60
    assert analysis.outperforms_nifty
    assert analysis.meets_rsi_thresholds


def test_tradingview_sector_rsi_fills_monthly_only_when_tapetide_and_angelone_both_lack_it():
    # Same short (~6-month) history as the UNAVAILABLE case above — no
    # Angel One override this time either — but a TradingView SECTOR_RSI
    # webhook value IS supplied, so it should be used as the last resort.
    sector_ohlc = _strong_uptrend(127, base=100.0, step=1.5)
    benchmark_ohlc = _flat_benchmark(127)
    benchmark = compute_benchmark_stats(benchmark_ohlc)

    analysis = analyze_sector(
        "Banks", sector_ohlc, benchmark, SectorRSIConfig(),
        angelone_ohlc_override=None,
        tradingview_weekly_rsi=None,
        tradingview_monthly_rsi=72.5,
    )

    assert analysis.monthly.rsi == 72.5
    assert analysis.monthly_data_source == "TRADINGVIEW"
    # A TradingView-sourced timeframe carries no return_pct, so it can never
    # contribute to the outperformance check (unlike a real computed value).
    assert analysis.monthly_vs_nifty is None
    assert analysis.meets_rsi_thresholds


def test_tradingview_sector_rsi_never_overrides_a_real_angelone_value():
    # Angel One override already supplies a real, computed monthly RSI here
    # -> the TradingView value must be ignored entirely, never blended in.
    sector_ohlc = _strong_uptrend(127, base=100.0, step=1.5)
    long_ohlc = _strong_uptrend(600, base=100.0, step=0.3)
    benchmark_ohlc = _flat_benchmark(127)
    benchmark = compute_benchmark_stats(benchmark_ohlc)

    analysis = analyze_sector(
        "Banks", sector_ohlc, benchmark, SectorRSIConfig(),
        angelone_ohlc_override=long_ohlc,
        tradingview_monthly_rsi=1.0,  # deliberately implausible, must be ignored
    )

    assert analysis.monthly_data_source == "ANGEL_ONE"
    assert analysis.monthly.rsi != 1.0


def test_angel_one_override_supplies_real_monthly_rsi():
    sector_ohlc = _strong_uptrend(127, base=100.0, step=1.5)
    benchmark_ohlc = _flat_benchmark(127)
    benchmark = compute_benchmark_stats(benchmark_ohlc)

    # A long (600-day), independently-fetched Angel One series covering
    # enough history for a real monthly RSI(14).
    monthly_source = _strong_uptrend(600, start="2022-06-01", base=50.0, step=0.3)

    analysis = analyze_sector("Banks", sector_ohlc, benchmark, SectorRSIConfig(), angelone_ohlc_override=monthly_source)

    assert analysis.monthly_data_source == "ANGEL_ONE"
    assert analysis.monthly.rsi is not None
    # Steady uptrend in the override series -> high monthly RSI.
    assert analysis.monthly.rsi > 60


def test_monthly_rsi_below_threshold_when_available_still_blocks_qualification():
    sector_ohlc = _strong_uptrend(127, base=100.0, step=1.5)
    benchmark_ohlc = _flat_benchmark(127)
    benchmark = compute_benchmark_stats(benchmark_ohlc)

    # Choppy/declining override -> low monthly RSI once actually computed.
    declining = _ohlc([100 - 0.2 * i for i in range(600)], start="2022-06-01")

    analysis = analyze_sector("Banks", sector_ohlc, benchmark, SectorRSIConfig(), angelone_ohlc_override=declining)

    assert analysis.monthly_data_source == "ANGEL_ONE"
    assert analysis.monthly.rsi is not None
    assert analysis.monthly.rsi < 60
    # Monthly WAS available and failed -> must NOT be silently ignored.
    assert not analysis.meets_rsi_thresholds


def test_outperformance_relaxed_to_available_timeframes_only():
    sector_ohlc = _strong_uptrend(127, base=100.0, step=2.0)
    benchmark_ohlc = _flat_benchmark(127)
    benchmark = compute_benchmark_stats(benchmark_ohlc)

    analysis = analyze_sector("Banks", sector_ohlc, benchmark, SectorRSIConfig())

    # No monthly data at all (Tapetide-only, no override) -> outperformance
    # decided from daily+weekly alone, not blocked by a missing monthly figure.
    assert analysis.monthly_vs_nifty is None
    assert analysis.daily_vs_nifty is not None and analysis.daily_vs_nifty > 0
    assert analysis.weekly_vs_nifty is not None and analysis.weekly_vs_nifty > 0
    assert analysis.outperforms_nifty


def test_unavailable_sector_index_reports_clearly():
    benchmark_ohlc = _flat_benchmark(50)
    benchmark = compute_benchmark_stats(benchmark_ohlc)

    analysis = analyze_sector("Aerospace & Defense", None, benchmark, SectorRSIConfig())

    assert not analysis.available
    assert "DATA UNAVAILABLE" in analysis.unavailable_reason


def test_weekly_sourced_from_angelone_when_tapetide_window_too_short():
    # A "3m"-sized Tapetide fetch (~63 bars, ~13 weekly closes) is too short
    # for a valid weekly RSI(14) — this is the real fix: daily is still
    # computed from the short (but current/un-truncated) Tapetide window,
    # while weekly comes from the longer Angel One series instead.
    sector_ohlc = _strong_uptrend(63, base=100.0, step=1.5)
    benchmark_ohlc = _flat_benchmark(63)
    benchmark = compute_benchmark_stats(benchmark_ohlc)

    angelone_source = _strong_uptrend(600, start="2022-06-01", base=50.0, step=0.3)

    analysis = analyze_sector("Banks", sector_ohlc, benchmark, SectorRSIConfig(), angelone_ohlc_override=angelone_source)

    assert analysis.daily.rsi is not None  # from the short Tapetide window
    assert analysis.weekly_data_source == "ANGEL_ONE"
    assert analysis.weekly.rsi is not None and analysis.weekly.rsi > 60


def _daily_closes_landing_rsi_near(value_hint: float, base_len: int = 20) -> list[float]:
    base = [100 + (1 if i % 2 == 0 else -0.5) for i in range(base_len)]
    # Calibrated last closes -> resulting daily RSI(14), verified directly.
    table = {
        20: {48.2: 100, 52.91: 102, 56.83: 104, 60.15: 106},
        90: {49.44: 100, 54.03: 102, 57.86: 104, 61.11: 106},
    }
    return base + [table[base_len][value_hint]]


def test_sector_qualifies_via_relaxed_daily_when_weekly_and_monthly_both_strong():
    # Daily RSI ~56.8 (above daily_min_relaxed=55, but below the normal
    # daily_min=60) -> must still qualify because weekly AND monthly are
    # both confirmed and above their own mins.
    sector_ohlc = _ohlc(_daily_closes_landing_rsi_near(56.83))
    benchmark_ohlc = _flat_benchmark(len(sector_ohlc))
    benchmark = compute_benchmark_stats(benchmark_ohlc)
    strong_override = _strong_uptrend(600, start="2022-06-01", base=50.0, step=0.3)

    analysis = analyze_sector("Banks", sector_ohlc, benchmark, SectorRSIConfig(), angelone_ohlc_override=strong_override)

    assert 55 < analysis.daily.rsi <= 60
    assert analysis.weekly.rsi is not None and analysis.weekly.rsi > 60
    assert analysis.monthly.rsi is not None and analysis.monthly.rsi > 60
    assert analysis.meets_rsi_thresholds


def test_relaxed_path_still_rejects_daily_below_the_lower_bar():
    # Daily RSI ~52.9 — below even daily_min_relaxed=55 — must not qualify
    # no matter how strong weekly/monthly are.
    sector_ohlc = _ohlc(_daily_closes_landing_rsi_near(52.91))
    benchmark_ohlc = _flat_benchmark(len(sector_ohlc))
    benchmark = compute_benchmark_stats(benchmark_ohlc)
    strong_override = _strong_uptrend(600, start="2022-06-01", base=50.0, step=0.3)

    analysis = analyze_sector("Banks", sector_ohlc, benchmark, SectorRSIConfig(), angelone_ohlc_override=strong_override)

    assert analysis.daily.rsi <= 55
    assert analysis.weekly.rsi is not None and analysis.weekly.rsi > 60
    assert analysis.monthly.rsi is not None and analysis.monthly.rsi > 60
    assert not analysis.meets_rsi_thresholds


def test_relaxed_daily_path_does_not_apply_when_monthly_is_unavailable():
    # Weekly alone being strong isn't enough to unlock the relaxed daily bar
    # — BOTH weekly and monthly must be confirmed strong. Here weekly is
    # computed directly from this (Tapetide-only, no override) series and
    # comes out strong, but monthly stays unavailable (not enough bars to
    # resample), so daily must still clear the full daily_min (60), not
    # just daily_min_relaxed (55).
    sector_ohlc = _ohlc(_daily_closes_landing_rsi_near(57.86, base_len=90))
    benchmark_ohlc = _flat_benchmark(len(sector_ohlc))
    benchmark = compute_benchmark_stats(benchmark_ohlc)

    analysis = analyze_sector("Banks", sector_ohlc, benchmark, SectorRSIConfig())

    assert 55 < analysis.daily.rsi <= 60
    assert analysis.weekly.rsi is not None
    assert analysis.monthly.rsi is None
    assert not analysis.meets_rsi_thresholds


def test_daily_alone_without_weekly_or_monthly_confirmation_does_not_qualify():
    # Only 63 bars, no Angel One override -> weekly can't be computed either
    # (too few bars resample to too few weekly closes for RSI(14)) and
    # monthly is unavailable too. A single timeframe (daily) is never enough
    # evidence on its own, even if its RSI is very high.
    sector_ohlc = _strong_uptrend(63, base=100.0, step=1.5)
    benchmark_ohlc = _flat_benchmark(63)
    benchmark = compute_benchmark_stats(benchmark_ohlc)

    analysis = analyze_sector("Banks", sector_ohlc, benchmark, SectorRSIConfig())

    assert analysis.daily.rsi is not None and analysis.daily.rsi > 60
    assert analysis.weekly.rsi is None
    assert analysis.monthly.rsi is None
    assert not analysis.meets_rsi_thresholds

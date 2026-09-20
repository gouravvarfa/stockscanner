"""
Tests for the common Stock Ranking Engine (backend/ranking/engine.py).

Central rule under test throughout: qualification and ranking are
completely separate. A stock with excellent RSI/momentum that does NOT
satisfy a strategy's boolean conditions must never become a ranked
candidate for that strategy.
"""
from backend.config.multi_strategy_config import DEFAULT_MULTI_STRATEGY_CONFIG as CFG
from backend.ranking.engine import build_ranking, compute_strategy_strength, rank_symbol
from backend.strategies.types import StrategySignal


def _signal(strategy, symbol, qualifies, **kw) -> StrategySignal:
    defaults = dict(
        strategy=strategy, symbol=symbol, qualifies=qualifies, signal_date=None,
        daily_rsi=None, weekly_rsi=None, monthly_rsi=None, conditions={}, explanation="", extra={},
    )
    defaults.update(kw)
    return StrategySignal(**defaults)


# ---- core safety rule: qualification gates ranking --------------------

def test_a_non_qualifying_signal_never_produces_a_ranked_candidate():
    sig = _signal("GFS", "RELIANCE", qualifies=False, daily_rsi=41, weekly_rsi=70, monthly_rsi=70)
    result = rank_symbol("RELIANCE", {"GFS": sig}, CFG)
    assert result is None


def test_a_symbol_with_zero_qualifying_strategies_is_excluded_from_build_ranking():
    strategy_signals = {"GFS": [_signal("GFS", "X", qualifies=False)]}
    ranking = build_ranking(strategy_signals, CFG)
    assert ranking.candidates == []
    assert ranking.best is None


def test_only_qualifying_strategies_contribute_to_qualifying_strategies_list():
    gfs = _signal("GFS", "RELIANCE", qualifies=True, daily_rsi=41.5, weekly_rsi=65, monthly_rsi=65)
    result = rank_symbol("RELIANCE", {"GFS": gfs}, CFG)
    assert result is not None
    assert result.qualifying_strategies == ["GFS"]


# ---- System One: direct reuse of the existing score --------------------

def test_system_one_strength_is_the_existing_score_verbatim():
    sig = _signal("Strategy One", "X", qualifies=True, extra={"score": 87.4, "classification": "STRONG SETUP"})
    breakdown = compute_strategy_strength("Strategy One", sig, CFG)
    assert breakdown.strength == 87.4
    assert breakdown.components["signal_strength"] == 87.4


def test_system_one_strength_is_none_without_fabricating_when_score_missing():
    sig = _signal("Strategy One", "X", qualifies=True, extra={})
    breakdown = compute_strategy_strength("Strategy One", sig, CFG)
    assert breakdown.strength is None


# ---- GFS / Advanced GFS: band-centered + above-min formulas -----------

def test_gfs_strength_is_100_when_rsi_values_are_ideal():
    # daily band [38,45] -> exact midpoint 41.5; weekly/monthly 20+ points
    # above their minimums -> full credit on every component.
    sig = _signal("GFS", "X", qualifies=True, daily_rsi=41.5, weekly_rsi=CFG.gfs.weekly_min + 20, monthly_rsi=CFG.gfs.monthly_min + 20)
    breakdown = compute_strategy_strength("GFS", sig, CFG)
    assert breakdown.strength == 100.0
    assert breakdown.components["daily_band_centered"] == 100.0
    assert breakdown.components["weekly_above_min"] == 100.0
    assert breakdown.components["monthly_above_min"] == 100.0


def test_gfs_strength_is_low_when_rsi_sits_right_at_the_edge_of_qualifying():
    # daily right at daily_min edge -> band-centered strength 0.
    # weekly/monthly right at their minimums -> above-min strength 0.
    sig = _signal("GFS", "X", qualifies=True, daily_rsi=CFG.gfs.daily_min, weekly_rsi=CFG.gfs.weekly_min, monthly_rsi=CFG.gfs.monthly_min)
    breakdown = compute_strategy_strength("GFS", sig, CFG)
    assert breakdown.components["daily_band_centered"] == 0.0
    assert breakdown.components["weekly_above_min"] == 0.0
    assert breakdown.components["monthly_above_min"] == 0.0
    assert breakdown.strength == 0.0


def test_gfs_strength_is_between_a_strong_and_a_weak_case_for_a_middling_reading():
    strong = _signal("GFS", "STRONG", qualifies=True, daily_rsi=41.5, weekly_rsi=CFG.gfs.weekly_min + 20, monthly_rsi=CFG.gfs.monthly_min + 20)
    weak = _signal("GFS", "WEAK", qualifies=True, daily_rsi=CFG.gfs.daily_min, weekly_rsi=CFG.gfs.weekly_min, monthly_rsi=CFG.gfs.monthly_min)
    middling = _signal("GFS", "MID", qualifies=True, daily_rsi=40.0, weekly_rsi=CFG.gfs.weekly_min + 10, monthly_rsi=CFG.gfs.monthly_min + 10)

    s = compute_strategy_strength("GFS", strong, CFG).strength
    w = compute_strategy_strength("GFS", weak, CFG).strength
    m = compute_strategy_strength("GFS", middling, CFG).strength
    assert w < m < s


def test_advanced_gfs_uses_its_own_config_thresholds_not_gfs():
    # Advanced GFS's thresholds are materially different from GFS's — using
    # the wrong config would silently miscalculate strength.
    sig = _signal("Advanced GFS", "X", qualifies=True,
                   daily_rsi=(CFG.advanced_gfs.daily_min + CFG.advanced_gfs.daily_max) / 2,
                   weekly_rsi=CFG.advanced_gfs.weekly_min + 20, monthly_rsi=CFG.advanced_gfs.monthly_min + 20)
    breakdown = compute_strategy_strength("Advanced GFS", sig, CFG)
    assert breakdown.strength == 100.0


# ---- PRD / NRD: divergence-leg strength ---------------------------------

def _prd_signal(rsi1, rsi2, bars_ago, price_change_pct):
    return _signal(
        "PRD", "X", qualifies=True,
        extra={"divergences": [{"rsi1": rsi1, "rsi2": rsi2, "bars_ago": bars_ago, "price_change_pct": price_change_pct}]},
    )


def test_prd_strength_rewards_fresher_setups():
    fresh = compute_strategy_strength("PRD", _prd_signal(65, 70, bars_ago=0, price_change_pct=3.0), CFG).strength
    stale = compute_strategy_strength("PRD", _prd_signal(65, 70, bars_ago=7, price_change_pct=3.0), CFG).strength
    assert fresh > stale


def test_prd_strength_rewards_stronger_leg_rsi_above_the_minimum():
    strong_legs = compute_strategy_strength("PRD", _prd_signal(80, 85, bars_ago=0, price_change_pct=3.0), CFG).strength
    weak_legs = compute_strategy_strength("PRD", _prd_signal(61, 61, bars_ago=0, price_change_pct=3.0), CFG).strength
    assert strong_legs > weak_legs


def test_prd_strength_without_any_divergence_data_is_none_not_fabricated():
    sig = _signal("PRD", "X", qualifies=True, extra={})
    breakdown = compute_strategy_strength("PRD", sig, CFG)
    assert breakdown.strength is None


def test_nrd_strength_rewards_leg_rsi_further_below_the_maximum():
    strong = compute_strategy_strength(
        "NRD", _signal("NRD", "X", qualifies=True, extra={"divergences": [{"rsi1": 10, "rsi2": 5, "bars_ago": 0, "price_change_pct": -3.0}]}), CFG
    ).strength
    weak = compute_strategy_strength(
        "NRD", _signal("NRD", "X", qualifies=True, extra={"divergences": [{"rsi1": 29, "rsi2": 29, "bars_ago": 0, "price_change_pct": -3.0}]}), CFG
    ).strength
    assert strong > weak


# ---- Value Buy -----------------------------------------------------------

def test_value_buy_strength_rewards_centered_monthly_support_and_confirmations():
    mid = (CFG.value_buy.monthly_rsi_support_min + CFG.value_buy.monthly_rsi_support_max) / 2
    sig = _signal(
        "Value Buy", "X", qualifies=True, monthly_rsi=mid,
        conditions={"latest_confirmed_weekly_candle_green": True},
        extra={"key_reversal_detected": True, "trendline_breakout_detected": False},
    )
    breakdown = compute_strategy_strength("Value Buy", sig, CFG)
    assert breakdown.components["monthly_support_centered"] == 100.0
    assert breakdown.components["weekly_confirmation"] == 100.0
    assert breakdown.components["daily_trigger_strength"] == 100.0
    assert breakdown.strength == 100.0


def test_value_buy_trendline_breakout_strength_scales_with_breakout_magnitude():
    big = _signal(
        "Value Buy", "X", qualifies=True, monthly_rsi=40,
        conditions={"latest_confirmed_weekly_candle_green": True},
        extra={"trendline_breakout_detected": True, "trendline_breakout_price": 110.0, "trendline_price_at_breakout": 100.0},
    )
    small = _signal(
        "Value Buy", "X", qualifies=True, monthly_rsi=40,
        conditions={"latest_confirmed_weekly_candle_green": True},
        extra={"trendline_breakout_detected": True, "trendline_breakout_price": 100.5, "trendline_price_at_breakout": 100.0},
    )
    big_strength = compute_strategy_strength("Value Buy", big, CFG).components["daily_trigger_strength"]
    small_strength = compute_strategy_strength("Value Buy", small, CFG).components["daily_trigger_strength"]
    assert big_strength > small_strength


# ---- multi-strategy confirmation bonus (capped, never dominant) --------

def test_multi_strategy_bonus_is_added_but_capped():
    strong_single = _signal("Strategy One", "SOLO", qualifies=True, extra={"score": 95.0})
    solo = rank_symbol("SOLO", {"Strategy One": strong_single}, CFG)

    weak_multi = {
        "Strategy One": _signal("Strategy One", "MULTI", qualifies=True, extra={"score": 50.0}),
        "GFS": _signal("GFS", "MULTI", qualifies=True, daily_rsi=CFG.gfs.daily_min, weekly_rsi=CFG.gfs.weekly_min, monthly_rsi=CFG.gfs.monthly_min),
    }
    multi = rank_symbol("MULTI", weak_multi, CFG)

    # Two qualifying strategies -> +3 bonus over the single best (50 GFS=0,
    # System One=50 -> base 50, bonus +3 = 53), still nowhere near the
    # strong solo signal (95) — multi-strategy count must not dominate.
    assert multi.score == 53.0
    assert multi.score < solo.score


def test_multi_strategy_bonus_caps_at_three_extra_strategies():
    # Every strategy pinned to its weakest possible qualifying reading (edge
    # of threshold -> strength 0 for all of them, including NRD, which -
    # unlike PRD - has no fixed/binary component), so the base score is
    # exactly 0 and only the multi-strategy bonus is under test.
    signals = {
        "Strategy One": _signal("Strategy One", "X", qualifies=True, extra={"score": 0.0}),
        "GFS": _signal("GFS", "X", qualifies=True, daily_rsi=CFG.gfs.daily_min, weekly_rsi=CFG.gfs.weekly_min, monthly_rsi=CFG.gfs.monthly_min),
        "Advanced GFS": _signal("Advanced GFS", "X", qualifies=True, daily_rsi=CFG.advanced_gfs.daily_min, weekly_rsi=CFG.advanced_gfs.weekly_min, monthly_rsi=CFG.advanced_gfs.monthly_min),
        "Value Buy": _signal("Value Buy", "X", qualifies=True, monthly_rsi=CFG.value_buy.monthly_rsi_support_min, conditions={"latest_confirmed_weekly_candle_green": False}, extra={}),
        "NRD": _signal("NRD", "X", qualifies=True, extra={"divergences": [{"rsi1": CFG.nrd.leg_rsi_max, "rsi2": CFG.nrd.leg_rsi_max, "bars_ago": CFG.nrd.lookback_bars, "price_change_pct": 0.0}]}),
    }
    result = rank_symbol("X", signals, CFG)
    # 5 qualifying strategies -> 4 "extra" beyond the first, capped at 3 -> +9 max on a 0 base.
    assert result.score == 9.0


def test_a_single_strong_signal_can_outrank_several_weak_ones():
    one_strong = rank_symbol("STRONG", {"Strategy One": _signal("Strategy One", "STRONG", qualifies=True, extra={"score": 92.0})}, CFG)
    three_weak = rank_symbol("WEAK", {
        "GFS": _signal("GFS", "WEAK", qualifies=True, daily_rsi=CFG.gfs.daily_min, weekly_rsi=CFG.gfs.weekly_min, monthly_rsi=CFG.gfs.monthly_min),
        "Advanced GFS": _signal("Advanced GFS", "WEAK", qualifies=True, daily_rsi=CFG.advanced_gfs.daily_min, weekly_rsi=CFG.advanced_gfs.weekly_min, monthly_rsi=CFG.advanced_gfs.monthly_min),
        "NRD": _signal("NRD", "WEAK", qualifies=True, extra={"divergences": [{"rsi1": 29.9, "rsi2": 29.9, "bars_ago": 7, "price_change_pct": -0.1}]}),
    }, CFG)
    assert one_strong.score > three_weak.score


# ---- build_ranking: sorting + per-strategy best -------------------------

def test_build_ranking_sorts_best_first():
    strategy_signals = {
        "Strategy One": [
            _signal("Strategy One", "LOW", qualifies=True, extra={"score": 40.0}),
            _signal("Strategy One", "HIGH", qualifies=True, extra={"score": 90.0}),
        ],
    }
    ranking = build_ranking(strategy_signals, CFG)
    assert [c.symbol for c in ranking.candidates] == ["HIGH", "LOW"]
    assert ranking.best.symbol == "HIGH"
    assert [c.symbol for c in ranking.top_candidates] == ["HIGH", "LOW"]


def test_build_ranking_strategy_best_uses_that_strategys_own_score_not_overall():
    # RELIANCE's overall/best score comes from a strong System One signal,
    # but under GFS specifically it's a WEAK reading — GFS's own "top
    # candidate" must not be RELIANCE just because its overall score is high.
    strategy_signals = {
        "Strategy One": [_signal("Strategy One", "RELIANCE", qualifies=True, extra={"score": 95.0})],
        "GFS": [
            _signal("GFS", "RELIANCE", qualifies=True, daily_rsi=CFG.gfs.daily_min, weekly_rsi=CFG.gfs.weekly_min, monthly_rsi=CFG.gfs.monthly_min),
            _signal("GFS", "TCS", qualifies=True, daily_rsi=41.5, weekly_rsi=CFG.gfs.weekly_min + 20, monthly_rsi=CFG.gfs.monthly_min + 20),
        ],
    }
    ranking = build_ranking(strategy_signals, CFG)
    assert ranking.strategy_best["Strategy One"].symbol == "RELIANCE"
    assert ranking.strategy_best["GFS"].symbol == "TCS"


def test_build_ranking_strategy_best_is_none_when_no_symbol_qualifies_for_it():
    strategy_signals = {"PRD": []}
    ranking = build_ranking(strategy_signals, CFG)
    assert ranking.strategy_best["PRD"] is None


def test_build_ranking_is_a_pure_function_of_its_inputs():
    # Same inputs -> identical output, every time — no hidden state, no
    # network calls, nothing that could vary run to run (Part 23).
    strategy_signals = {"Strategy One": [_signal("Strategy One", "X", qualifies=True, extra={"score": 77.0})]}
    r1 = build_ranking(strategy_signals, CFG)
    r2 = build_ranking(strategy_signals, CFG)
    assert r1.best.score == r2.best.score == 77.0

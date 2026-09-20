"""
Common Stock Ranking Engine — a SEPARATE layer from strategy qualification.

Hard rule this file exists to enforce: qualification and ranking never mix.
`evaluate_strategy_one` / `evaluate_gfs` / `evaluate_advanced_gfs` /
`evaluate_prd` / `evaluate_nrd` / `evaluate_value_buy` (untouched by this
module) decide WHETHER a stock qualifies. This module only ever looks at
signals that already have `qualifies=True` and asks HOW STRONG that
already-qualifying setup is, on a normalized 0-100 scale, so the six very
differently-shaped strategies can be compared and combined into one
"Top Ranked Candidates" list without pretending they're the same thing.

Reuse over duplication (spec Part 15): System One's strength score is
computed ONCE — the existing backend/ranking/scorer.py::compute_score()
call inside stock_analysis.py::analyze_stock(), which
strategy_one.py already exposes as signal.extra["score"]. This module reads
that value directly rather than recomputing anything for System One.

GFS/Advanced GFS/PRD/NRD/Value Buy currently carry only boolean conditions
plus their own raw RSI/divergence/trendline data (no existing 0-100
"strength" of their own) — nothing in backend/strategies/*.py was modified
to build this: every per-strategy score below reads ONLY fields that were
already on the StrategySignal (daily/weekly/monthly RSI, .extra) plus the
SAME threshold config object each evaluate_* function was already given,
so a strategy file changing its own qualification thresholds automatically
changes what "strong" means here too, with zero duplication of those
threshold values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.config.multi_strategy_config import MultiStrategyConfig
from backend.strategies.types import StrategySignal

# Multi-strategy confirmation bonus (Part 17): a small, CAPPED addition —
# it must nudge the ranking, never dominate it. +3 per confirming strategy
# beyond the first, capped at 3 extra strategies (+9 max), added to the
# single strongest per-strategy score and re-clipped to 100.
MULTI_STRATEGY_BONUS_PER_STRATEGY = 3.0
MULTI_STRATEGY_BONUS_MAX_STRATEGIES = 3


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _band_centered_strength(value: float | None, lo: float, hi: float) -> float | None:
    """100 at the exact midpoint of [lo, hi], falling linearly to 0 at
    either edge — used for conditions of the shape "RSI must sit inside a
    band" (GFS/Advanced GFS's daily RSI band)."""
    if value is None or hi <= lo:
        return None
    mid = (lo + hi) / 2.0
    half_width = (hi - lo) / 2.0
    distance = abs(value - mid)
    return _clip(100.0 * (1.0 - distance / half_width))


def _above_min_strength(value: float | None, minimum: float, full_credit_margin: float = 20.0) -> float | None:
    """0 right at the threshold, 100 once `full_credit_margin` points above
    it — used for conditions of the shape "RSI must be above a floor"
    (GFS/Advanced GFS's weekly/monthly minimums). The margin is a documented,
    fixed normalization constant (not per-strategy tuned), chosen because a
    20-point RSI cushion above a floor is already a comfortably strong
    reading on Wilder's 0-100 scale."""
    if value is None:
        return None
    return _clip(100.0 * (value - minimum) / full_credit_margin)


def _below_max_strength(value: float | None, maximum: float, full_credit_margin: float = 20.0) -> float | None:
    """Mirror of _above_min_strength for "must be below a ceiling" conditions."""
    if value is None:
        return None
    return _clip(100.0 * (maximum - value) / full_credit_margin)


def _mean(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


@dataclass
class StrengthBreakdown:
    """Every component that fed a strategy's strength score, each 0-100 or
    None when the underlying data genuinely wasn't available (never a
    substituted default — Part 20)."""
    components: dict[str, float | None]
    strength: float | None  # the combined 0-100 score, or None if no component was computable


def _system_one_strength(signal: StrategySignal) -> StrengthBreakdown:
    # Direct reuse of the existing System One score — see module docstring.
    score = signal.extra.get("score")
    components = {"signal_strength": float(score) if score is not None else None}
    return StrengthBreakdown(components=components, strength=components["signal_strength"])


def _gfs_strength(signal: StrategySignal, cfg) -> StrengthBreakdown:
    components = {
        "daily_band_centered": _band_centered_strength(signal.daily_rsi, cfg.daily_min, cfg.daily_max),
        "weekly_above_min": _above_min_strength(signal.weekly_rsi, cfg.weekly_min),
        "monthly_above_min": _above_min_strength(signal.monthly_rsi, cfg.monthly_min),
    }
    return StrengthBreakdown(components=components, strength=_mean(list(components.values())))


def _advanced_gfs_strength(signal: StrategySignal, cfg) -> StrengthBreakdown:
    components = {
        "daily_band_centered": _band_centered_strength(signal.daily_rsi, cfg.daily_min, cfg.daily_max),
        "weekly_above_min": _above_min_strength(signal.weekly_rsi, cfg.weekly_min),
        "monthly_above_min": _above_min_strength(signal.monthly_rsi, cfg.monthly_min),
    }
    return StrengthBreakdown(components=components, strength=_mean(list(components.values())))


def _best_divergence(signal: StrategySignal) -> dict[str, Any] | None:
    divergences = signal.extra.get("divergences")
    if isinstance(divergences, list) and divergences:
        return divergences[0]
    return None


def _prd_strength(signal: StrategySignal, cfg) -> StrengthBreakdown:
    leg = _best_divergence(signal)
    if leg is None:
        return StrengthBreakdown(components={}, strength=None)

    rsi1, rsi2 = leg.get("rsi1"), leg.get("rsi2")
    bars_ago = leg.get("bars_ago")
    price_change_pct = leg.get("price_change_pct")

    leg_strength = _mean([
        _above_min_strength(rsi1, cfg.leg_rsi_min) if rsi1 is not None else None,
        _above_min_strength(rsi2, cfg.leg_rsi_min) if rsi2 is not None else None,
    ])
    freshness = (
        _clip(100.0 * (1.0 - bars_ago / cfg.lookback_bars)) if bars_ago is not None and cfg.lookback_bars else None
    )
    # A higher-low that is only barely higher is a weaker structure than one
    # with real separation; 5% price separation is treated as a strong,
    # fully-credited move (a fixed, documented normalization constant).
    price_structure = _clip(100.0 * abs(price_change_pct) / 5.0) if price_change_pct is not None else None

    components = {
        "leg_rsi_strength": leg_strength,
        "freshness": freshness,
        "price_structure": price_structure,
        "candle_confirmation": 100.0,  # binary gate already required to qualify — full credit once qualifying
    }
    return StrengthBreakdown(components=components, strength=_mean(list(components.values())))


def _nrd_strength(signal: StrategySignal, cfg) -> StrengthBreakdown:
    leg = _best_divergence(signal)
    if leg is None:
        return StrengthBreakdown(components={}, strength=None)

    rsi1, rsi2 = leg.get("rsi1"), leg.get("rsi2")
    bars_ago = leg.get("bars_ago")
    price_change_pct = leg.get("price_change_pct")

    leg_strength = _mean([
        _below_max_strength(rsi1, cfg.leg_rsi_max) if rsi1 is not None else None,
        _below_max_strength(rsi2, cfg.leg_rsi_max) if rsi2 is not None else None,
    ])
    freshness = (
        _clip(100.0 * (1.0 - bars_ago / cfg.lookback_bars)) if bars_ago is not None and cfg.lookback_bars else None
    )
    price_structure = _clip(100.0 * abs(price_change_pct) / 5.0) if price_change_pct is not None else None

    components = {
        "leg_rsi_strength": leg_strength,
        "freshness": freshness,
        "price_structure": price_structure,
    }
    return StrengthBreakdown(components=components, strength=_mean(list(components.values())))


def _value_buy_strength(signal: StrategySignal, cfg) -> StrengthBreakdown:
    monthly_strength = _band_centered_strength(
        signal.monthly_rsi, cfg.monthly_rsi_support_min, cfg.monthly_rsi_support_max
    )
    weekly_confirmed = signal.conditions.get("latest_confirmed_weekly_candle_green")
    weekly_strength = 100.0 if weekly_confirmed else (0.0 if weekly_confirmed is False else None)

    # Trendline breakout magnitude, when that was the trigger: how far the
    # close broke above the trendline, as a % of the trendline price at that
    # point — a fixed 3% breakout is treated as fully strong (documented
    # normalization constant, matching PRD/NRD's price-structure scale).
    breakout_price = signal.extra.get("trendline_breakout_price")
    trendline_price = signal.extra.get("trendline_price_at_breakout")
    breakout_strength = None
    if signal.extra.get("trendline_breakout_detected") and breakout_price and trendline_price:
        pct = (breakout_price - trendline_price) / trendline_price * 100.0
        breakout_strength = _clip(100.0 * pct / 3.0)
    elif signal.extra.get("key_reversal_detected"):
        breakout_strength = 100.0  # binary confirmation, already required to qualify

    components = {
        "monthly_support_centered": monthly_strength,
        "weekly_confirmation": weekly_strength,
        "daily_trigger_strength": breakout_strength,
    }
    return StrengthBreakdown(components=components, strength=_mean(list(components.values())))


_STRATEGY_STRENGTH_FUNCS = {
    "Strategy One": lambda signal, cfg: _system_one_strength(signal),
    "GFS": lambda signal, cfg: _gfs_strength(signal, cfg.gfs),
    "Advanced GFS": lambda signal, cfg: _advanced_gfs_strength(signal, cfg.advanced_gfs),
    "PRD": lambda signal, cfg: _prd_strength(signal, cfg.prd),
    "NRD": lambda signal, cfg: _nrd_strength(signal, cfg.nrd),
    "Value Buy": lambda signal, cfg: _value_buy_strength(signal, cfg.value_buy),
}


@dataclass
class StrategyRankEntry:
    strategy: str
    strength: float | None
    breakdown: StrengthBreakdown


@dataclass
class RankedCandidate:
    symbol: str
    score: float
    qualifying_strategies: list[str]
    strategy_scores: dict[str, StrategyRankEntry]
    best_strategy: str  # the single strategy that produced this candidate's base score


def compute_strategy_strength(
    strategy: str, signal: StrategySignal, config: MultiStrategyConfig
) -> StrengthBreakdown:
    """Public per-strategy entry point — also used by GET /api/ranking/strategy/{strategy}."""
    func = _STRATEGY_STRENGTH_FUNCS.get(strategy)
    if func is None or not signal.qualifies:
        return StrengthBreakdown(components={}, strength=None)
    return func(signal, config)


def rank_symbol(symbol: str, signals: dict[str, StrategySignal], config: MultiStrategyConfig) -> RankedCandidate | None:
    """
    Ranks ONE symbol from its already-computed strategy signals for this
    scan. Returns None if the symbol did not qualify for ANY strategy —
    ranking never invents a candidate that didn't actually qualify
    (Part 18: "Only show stocks that actually qualified for at least one
    strategy").
    """
    qualifying = {name: sig for name, sig in signals.items() if sig.qualifies}
    if not qualifying:
        return None

    strategy_scores: dict[str, StrategyRankEntry] = {}
    for name, sig in qualifying.items():
        breakdown = compute_strategy_strength(name, sig, config)
        strategy_scores[name] = StrategyRankEntry(strategy=name, strength=breakdown.strength, breakdown=breakdown)

    scored = {name: e.strength for name, e in strategy_scores.items() if e.strength is not None}
    if not scored:
        # Every qualifying strategy had insufficient data to score its own
        # strength (rare — e.g. missing RSI) — still a real qualifying
        # candidate, just with an unscorable base; do not fabricate a
        # number, and do not silently drop it either.
        best_strategy = next(iter(qualifying))
        base_score = 0.0
    else:
        best_strategy = max(scored, key=lambda n: scored[n])
        base_score = scored[best_strategy]

    bonus_strategies = max(0, len(qualifying) - 1)
    bonus = min(bonus_strategies, MULTI_STRATEGY_BONUS_MAX_STRATEGIES) * MULTI_STRATEGY_BONUS_PER_STRATEGY
    final_score = _clip(base_score + bonus)

    return RankedCandidate(
        symbol=symbol,
        score=round(final_score, 2),
        qualifying_strategies=sorted(qualifying),
        strategy_scores=strategy_scores,
        best_strategy=best_strategy,
    )


@dataclass
class RankingResult:
    candidates: list[RankedCandidate]  # every qualifying symbol, sorted best-first
    strategy_best: dict[str, RankedCandidate | None]  # each strategy's own top candidate

    @property
    def top_candidates(self) -> list[RankedCandidate]:
        return self.candidates[:5]

    @property
    def best(self) -> RankedCandidate | None:
        return self.candidates[0] if self.candidates else None


def build_ranking(
    strategy_signals: dict[str, list[StrategySignal]], config: MultiStrategyConfig
) -> RankingResult:
    """
    Top-level entry point (Part 18/19): `strategy_signals` is exactly
    ScanOutcome.strategy_signals — the same dict the scan already produces,
    keyed by strategy name, values = only the QUALIFYING signals for that
    strategy from this scan. No new Angel One call, no re-analysis — pure
    post-processing of results that already exist (Part 23).
    """
    by_symbol: dict[str, dict[str, StrategySignal]] = {}
    for strategy, sigs in strategy_signals.items():
        for sig in sigs:
            by_symbol.setdefault(sig.symbol, {})[strategy] = sig

    candidates = [rank_symbol(symbol, sigs, config) for symbol, sigs in by_symbol.items()]
    candidates = [c for c in candidates if c is not None]
    candidates.sort(key=lambda c: c.score, reverse=True)

    strategy_best: dict[str, RankedCandidate | None] = {}
    for strategy in strategy_signals:
        same_strategy = [c for c in candidates if strategy in c.qualifying_strategies]
        # Rank each candidate by ITS score under this specific strategy
        # (not its overall best-of score) when picking that strategy's own
        # top candidate.
        scored = [
            (c, c.strategy_scores[strategy].strength)
            for c in same_strategy
            if c.strategy_scores[strategy].strength is not None
        ]
        strategy_best[strategy] = max(scored, key=lambda p: p[1])[0] if scored else None

    return RankingResult(candidates=candidates, strategy_best=strategy_best)

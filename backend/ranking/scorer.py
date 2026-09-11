from __future__ import annotations

from dataclasses import dataclass, field

from backend.config.strategy_config import ClassificationThresholds, ScoringWeights


@dataclass
class ScoreBreakdown:
    components: dict[str, float]  # each 0-100
    weighted: dict[str, float]  # component * weight fraction
    total_score: float  # 0-100
    classification: str  # STRONG SETUP | GOOD SETUP | MODERATE SETUP | WEAK SETUP
    bias: str  # BULLISH | NEUTRAL | HIGH RISK
    explanation: list[str] = field(default_factory=list)


def compute_score(
    components: dict[str, float],
    weights: ScoringWeights,
    thresholds: ClassificationThresholds,
    explanation: list[str] | None = None,
) -> ScoreBreakdown:
    """
    `components` values must each be 0-100 and use the exact keys from
    ScoringWeights (sector_outperformance, sector_rsi, stock_rsi, divergence,
    fibonacci, trend, volume, macd_adx). The final score is the weighted
    average, normalized against the configured weight total so custom weight
    sets that don't sum to exactly 100 still yield a 0-100 score.
    """
    weight_map = weights.model_dump()
    total_weight = sum(weight_map.values()) or 1.0

    weighted: dict[str, float] = {}
    total_score = 0.0
    for key, weight in weight_map.items():
        value = components.get(key, 0.0)
        contribution = value * weight / total_weight
        weighted[key] = contribution
        total_score += contribution

    if total_score >= thresholds.strong_setup_min:
        classification = "STRONG SETUP"
    elif total_score >= thresholds.good_setup_min:
        classification = "GOOD SETUP"
    elif total_score >= thresholds.moderate_setup_min:
        classification = "MODERATE SETUP"
    else:
        classification = "WEAK SETUP"

    if components.get("divergence", 100.0) <= 20.0:
        bias = "HIGH RISK"
    elif total_score >= thresholds.moderate_setup_min:
        bias = "BULLISH"
    else:
        bias = "NEUTRAL"

    return ScoreBreakdown(
        components=components,
        weighted=weighted,
        total_score=round(total_score, 2),
        classification=classification,
        bias=bias,
        explanation=explanation or [],
    )

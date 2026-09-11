from backend.config.strategy_config import ClassificationThresholds, ScoringWeights
from backend.ranking.scorer import compute_score


def test_all_components_max_gives_strong_setup():
    weights = ScoringWeights()
    thresholds = ClassificationThresholds()
    components = {k: 100.0 for k in weights.model_dump()}

    result = compute_score(components, weights, thresholds)

    assert result.total_score == 100.0
    assert result.classification == "STRONG SETUP"
    assert result.bias == "BULLISH"


def test_all_components_zero_gives_weak_setup():
    weights = ScoringWeights()
    thresholds = ClassificationThresholds()
    components = {k: 0.0 for k in weights.model_dump()}

    result = compute_score(components, weights, thresholds)

    assert result.total_score == 0.0
    assert result.classification == "WEAK SETUP"
    # divergence=0 legitimately signals significant bearish divergence -> HIGH RISK
    assert result.bias == "HIGH RISK"


def test_weak_score_without_divergence_problem_is_neutral_not_high_risk():
    weights = ScoringWeights()
    thresholds = ClassificationThresholds()
    components = {k: 0.0 for k in weights.model_dump()}
    components["divergence"] = 100.0  # no bearish divergence

    result = compute_score(components, weights, thresholds)

    assert result.classification == "WEAK SETUP"
    assert result.bias == "NEUTRAL"


def test_low_divergence_component_forces_high_risk_bias():
    weights = ScoringWeights()
    thresholds = ClassificationThresholds()
    components = {k: 90.0 for k in weights.model_dump()}
    components["divergence"] = 0.0  # significant bearish divergence present

    result = compute_score(components, weights, thresholds)

    assert result.bias == "HIGH RISK"


def test_custom_weights_still_normalize_to_100():
    # Weights that don't sum to 100 should still produce a 0-100 score.
    weights = ScoringWeights(
        sector_outperformance=10, sector_rsi=10, stock_rsi=10, divergence=10,
        fibonacci=10, trend=10, volume=10, macd_adx=10,
    )
    thresholds = ClassificationThresholds()
    components = {k: 50.0 for k in weights.model_dump()}

    result = compute_score(components, weights, thresholds)
    assert result.total_score == 50.0


def test_classification_boundaries():
    weights = ScoringWeights()
    thresholds = ClassificationThresholds(strong_setup_min=90, good_setup_min=80, moderate_setup_min=70)

    for score_value, expected in [(95, "STRONG SETUP"), (85, "GOOD SETUP"), (75, "MODERATE SETUP"), (50, "WEAK SETUP")]:
        components = {k: score_value for k in weights.model_dump()}
        result = compute_score(components, weights, thresholds)
        assert result.classification == expected, f"{score_value} -> {result.classification}"

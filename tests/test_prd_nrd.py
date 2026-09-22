import pandas as pd

from backend.config.multi_strategy_config import NRDConfig, PRDConfig
from backend.divergence.detector import DivergenceSignal
from backend.divergence.swing import SwingPoint
from backend.strategies.nrd import evaluate_nrd
from backend.strategies.prd import evaluate_prd
from tests.prd_confirmed_helpers import confirmed_frame, install_rsi
from tests.strategy_helpers import make_result

LAST_BAR = 100  # "current completed bar" for all fixtures below


def _positive_reversal_signal(leg1_rsi: float, leg2_rsi: float, leg2_bar: int) -> DivergenceSignal:
    """Positive Reversal (PRD's real pattern): price higher low, RSI lower low."""
    p1 = SwingPoint(index=leg2_bar - 12, date=pd.Timestamp("2024-01-10"), price=90.0, kind="low")
    p2 = SwingPoint(index=leg2_bar, date=pd.Timestamp("2024-02-10"), price=100.0, kind="low")
    return DivergenceSignal(
        kind="hidden_bullish", first_point=p1, second_point=p2,
        first_rsi=leg1_rsi, second_rsi=leg2_rsi, price_change_pct=11.1, rsi_change=leg2_rsi - leg1_rsi,
    )


def _negative_reversal_signal(leg1_rsi: float, leg2_rsi: float, leg2_bar: int) -> DivergenceSignal:
    """Negative Reversal (NRD's real pattern): price lower high, RSI higher high."""
    p1 = SwingPoint(index=leg2_bar - 10, date=pd.Timestamp("2024-01-10"), price=110.0, kind="high")
    p2 = SwingPoint(index=leg2_bar, date=pd.Timestamp("2024-02-10"), price=100.0, kind="high")
    return DivergenceSignal(
        kind="hidden_bearish", first_point=p1, second_point=p2,
        first_rsi=leg1_rsi, second_rsi=leg2_rsi, price_change_pct=-9.1, rsi_change=leg2_rsi - leg1_rsi,
    )


def _regular_bullish_signal(leg2_bar: int) -> DivergenceSignal:
    """Regular bullish divergence (price lower low + RSI higher low) — must NEVER satisfy PRD."""
    p1 = SwingPoint(index=leg2_bar - 10, date=pd.Timestamp("2024-01-10"), price=100.0, kind="low")
    p2 = SwingPoint(index=leg2_bar, date=pd.Timestamp("2024-02-10"), price=90.0, kind="low")
    return DivergenceSignal(
        kind="bullish", first_point=p1, second_point=p2,
        first_rsi=65.0, second_rsi=70.0, price_change_pct=-10.0, rsi_change=5.0,
    )


def _regular_bearish_signal(leg2_bar: int) -> DivergenceSignal:
    """Regular bearish divergence (price higher high + RSI lower high) — must NEVER satisfy NRD."""
    p1 = SwingPoint(index=leg2_bar - 10, date=pd.Timestamp("2024-01-10"), price=100.0, kind="high")
    p2 = SwingPoint(index=leg2_bar, date=pd.Timestamp("2024-02-10"), price=110.0, kind="high")
    return DivergenceSignal(
        kind="bearish", first_point=p1, second_point=p2,
        first_rsi=20.0, second_rsi=15.0, price_change_pct=10.0, rsi_change=-5.0,
    )


def _ohlcv_with_last_two(red_first: bool = True) -> pd.DataFrame:
    """
    A short daily OHLCV frame whose LAST TWO rows are a confirmed RED bar
    immediately followed by a confirmed GREEN breakout bar (green close >
    red high) — the exact PRD candle-confirmation pattern. Enough rows
    precede them for to_weekly/to_monthly to run without error (their
    resampled divergences are always empty in these tests since weekly/
    monthly TimeframeReading.divergences default to [] unless set).
    """
    idx = pd.bdate_range("2024-01-01", periods=20)
    closes = [100.0 + i * 0.2 for i in range(18)]
    rows = [(c, c + 1, c - 1, c, 1000) for c in closes]
    if red_first:
        # Bar N-1: RED (close < open). Bar N: GREEN, closing above red's high.
        rows.append((110.0, 111.0, 107.0, 108.0, 1000))  # red: open 110 -> close 108
        rows.append((108.5, 112.5, 108.0, 112.0, 1000))  # green: 108.5 -> 112.0, > red high 111.0
    else:
        # No red-then-green: both green (no confirmation should trigger).
        rows.append((108.0, 111.0, 107.5, 110.0, 1000))
        rows.append((110.5, 112.5, 110.0, 112.0, 1000))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)
    return df


CONFIRMED_OHLCV = _ohlcv_with_last_two(red_first=True)
NOT_CONFIRMED_OHLCV = _ohlcv_with_last_two(red_first=False)


# ---------------------------------------------------------------------------
# PRD
# ---------------------------------------------------------------------------

def test_prd_confirmed_uses_reference_rsi_bottom_definition(monkeypatch):
    install_rsi(monkeypatch)
    signal = evaluate_prd(make_result(), confirmed_frame(), PRDConfig())
    assert signal.qualifies
    assert signal.extra["status"] == "PRD_CONFIRMED"


def test_prd_rejects_eight_bars_ago():
    sig = _positive_reversal_signal(65.0, 70.0, leg2_bar=LAST_BAR - 8)  # bars_ago = 8, too old
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_prd(result, CONFIRMED_OHLCV, PRDConfig())
    assert not signal.qualifies


def test_prd_rejects_leg_rsi_exactly_at_threshold():
    sig = _positive_reversal_signal(60.0, 70.0, leg2_bar=LAST_BAR)  # leg1 == 60, strict > required
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_prd(result, CONFIRMED_OHLCV, PRDConfig())
    assert not signal.qualifies


def test_prd_rejects_leg_rsi_below_threshold():
    sig = _positive_reversal_signal(58.0, 70.0, leg2_bar=LAST_BAR)  # leg1 < 60
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_prd(result, CONFIRMED_OHLCV, PRDConfig())
    assert not signal.qualifies


def test_prd_rejects_regular_bullish_divergence_not_positive_reversal():
    sig = _regular_bullish_signal(leg2_bar=LAST_BAR)
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_prd(result, CONFIRMED_OHLCV, PRDConfig())
    assert not signal.qualifies


def test_prd_reports_a_single_confirmed_match_per_timeframe(monkeypatch):
    install_rsi(monkeypatch)
    signal = evaluate_prd(make_result(), confirmed_frame(), PRDConfig())
    assert signal.qualifies
    per_tf = [d["timeframe"] for d in signal.extra["divergences"]]
    assert len(per_tf) == len(set(per_tf))


def test_prd_forming_when_structure_valid_but_no_candle_confirmation_yet():
    sig = _positive_reversal_signal(65.0, 70.0, leg2_bar=LAST_BAR)
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_prd(result, NOT_CONFIRMED_OHLCV, PRDConfig())
    assert not signal.qualifies
    assert signal.extra["status"] == "PRD_FORMING"


def test_prd_never_shows_confirmed_before_green_candle_closes():
    # Structure + RSI + freshness all pass, but only a RED candle so far (no
    # green breakout yet) -> must stay FORMING, never CONFIRMED.
    sig = _positive_reversal_signal(65.0, 70.0, leg2_bar=LAST_BAR)
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_prd(result, NOT_CONFIRMED_OHLCV, PRDConfig())
    assert signal.extra["status"] != "PRD_CONFIRMED"


# ---------------------------------------------------------------------------
# NRD
# ---------------------------------------------------------------------------

def test_nrd_confirmed_zero_bars_ago():
    sig = _negative_reversal_signal(25.0, 20.0, leg2_bar=LAST_BAR)
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_nrd(result, NRDConfig())
    assert signal.qualifies
    assert signal.extra["status"] == "NRD_CONFIRMED"


def test_nrd_confirmed_seven_bars_ago():
    sig = _negative_reversal_signal(25.0, 20.0, leg2_bar=LAST_BAR - 7)
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_nrd(result, NRDConfig())
    assert signal.qualifies


def test_nrd_rejects_eight_bars_ago():
    sig = _negative_reversal_signal(25.0, 20.0, leg2_bar=LAST_BAR - 8)
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_nrd(result, NRDConfig())
    assert not signal.qualifies


def test_nrd_rejects_leg_rsi_exactly_at_threshold():
    sig = _negative_reversal_signal(40.0, 20.0, leg2_bar=LAST_BAR)  # leg1 == 40, strict < required
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_nrd(result, NRDConfig())
    assert not signal.qualifies


def test_nrd_rejects_leg_rsi_above_threshold():
    sig = _negative_reversal_signal(42.0, 20.0, leg2_bar=LAST_BAR)  # leg1 > 40
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_nrd(result, NRDConfig())
    assert not signal.qualifies


def test_nrd_rejects_regular_bearish_divergence_not_negative_reversal():
    sig = _regular_bearish_signal(leg2_bar=LAST_BAR)
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    signal = evaluate_nrd(result, NRDConfig())
    assert not signal.qualifies


def test_nrd_reports_only_the_single_most_recent_setup_when_multiple_fresh_pivots_exist():
    # Two separate valid Negative Reversal pivots both fall inside the
    # 7-bar freshness window (bars_ago 5 and 1) — only the freshest (most
    # recent) one may ever be reported, never both.
    older = _negative_reversal_signal(25.0, 20.0, leg2_bar=LAST_BAR - 5)
    newer = _negative_reversal_signal(28.0, 22.0, leg2_bar=LAST_BAR - 1)
    result = make_result(daily_divergences=[older, newer], daily_last_bar_index=LAST_BAR)
    signal = evaluate_nrd(result, NRDConfig())
    assert signal.qualifies
    assert len(signal.extra["divergences"]) == 1
    assert signal.extra["divergences"][0]["bars_ago"] == 1


# ---------------------------------------------------------------------------
# Separation: PRD and NRD must never satisfy each other.
# ---------------------------------------------------------------------------

def test_daily_prd_and_weekly_nrd_appear_separately(monkeypatch):
    prd_sig = _positive_reversal_signal(65.0, 70.0, leg2_bar=LAST_BAR)
    nrd_sig = _negative_reversal_signal(25.0, 20.0, leg2_bar=LAST_BAR)
    result = make_result(
        daily_divergences=[prd_sig], weekly_divergences=[nrd_sig],
        daily_last_bar_index=LAST_BAR, weekly_last_bar_index=LAST_BAR,
    )
    install_rsi(monkeypatch)
    prd_signal = evaluate_prd(result, confirmed_frame(), PRDConfig())
    nrd_signal = evaluate_nrd(result, NRDConfig())

    assert prd_signal.qualifies
    assert nrd_signal.qualifies
    assert "DAILY" in prd_signal.extra["divergence_timeframes"]
    assert nrd_signal.extra["divergence_timeframes"] == ["WEEKLY"]


def test_prd_never_satisfies_nrd(monkeypatch):
    sig = _positive_reversal_signal(65.0, 70.0, leg2_bar=LAST_BAR)
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    install_rsi(monkeypatch)
    prd_signal = evaluate_prd(result, confirmed_frame(), PRDConfig())
    nrd_signal = evaluate_nrd(result, NRDConfig())
    assert prd_signal.qualifies
    assert not nrd_signal.qualifies


def test_nrd_never_satisfies_prd():
    sig = _negative_reversal_signal(25.0, 20.0, leg2_bar=LAST_BAR)
    result = make_result(daily_divergences=[sig], daily_last_bar_index=LAST_BAR)
    prd_signal = evaluate_prd(result, CONFIRMED_OHLCV, PRDConfig())
    nrd_signal = evaluate_nrd(result, NRDConfig())
    assert not prd_signal.qualifies
    assert nrd_signal.qualifies

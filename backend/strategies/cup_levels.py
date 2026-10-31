"""
Cup Breakout trade levels — the ONE place entry / stop loss / targets are
computed (backend/strategies/cup.py attaches them to every result; the
frontend only displays what the API returns, never recomputes).

Per the Cup Pattern (Level 1) diagram, every level is a percentage of the
stock's own NECKLINE, never of the entry price:

    Entry      = neckline * 1.04
    Stop loss  = neckline * 0.98
    Target 1   = neckline * 1.10
    Target 2   = neckline * 1.20
    Target 3   = neckline * 1.30
"""
from __future__ import annotations

from backend.config.cup_config import CupConfig

STATUS_GROUP_CUP_FORMING = "CUP_FORMING"
STATUS_GROUP_AWAITING_BREAKOUT = "AWAITING_BREAKOUT"
STATUS_GROUP_BREAKOUT_CONFIRMED = "BREAKOUT_CONFIRMED"

# Maps the detailed detector status to the three groups the user asked for.
# BREAKOUT_FORMING is deliberately NOT "confirmed": it means the still-open
# current month is above the neckline but no completed month has closed
# above it yet.
_STATUS_TO_GROUP = {
    "EARLY_CUP": STATUS_GROUP_CUP_FORMING,
    "NEAR_BREAKOUT": STATUS_GROUP_AWAITING_BREAKOUT,
    "BREAKOUT_FORMING": STATUS_GROUP_AWAITING_BREAKOUT,
    "BREAKOUT_CONFIRMED": STATUS_GROUP_BREAKOUT_CONFIRMED,
    "RECENT_BREAKOUT": STATUS_GROUP_BREAKOUT_CONFIRMED,
}


def status_group(status: str) -> str | None:
    return _STATUS_TO_GROUP.get(status)


def compute_trade_levels(neckline: float, config: CupConfig) -> dict[str, float]:
    """Returns entry/stop_loss/target_1..3, all derived from `neckline`."""
    return {
        "entry_price": round(neckline * (1 + config.entry_above_neckline_pct / 100.0), 2),
        "stop_loss": round(neckline * (1 - config.stop_loss_below_neckline_pct / 100.0), 2),
        "target_1": round(neckline * (1 + config.target_1_above_neckline_pct / 100.0), 2),
        "target_2": round(neckline * (1 + config.target_2_above_neckline_pct / 100.0), 2),
        "target_3": round(neckline * (1 + config.target_3_above_neckline_pct / 100.0), 2),
    }


def targets_crossed(price: float, levels: dict[str, float]) -> int:
    """How many of the three targets `price` has already reached (0-3)."""
    return sum(1 for key in ("target_1", "target_2", "target_3") if price >= levels[key])

"""
Ranking API — reads the last completed A Group scan's cached result and
runs it through the common Stock Ranking Engine (backend/ranking/engine.py).
Never triggers a new Angel One scan (Part 23): if no scan result is cached
yet, this returns a clean 404 telling the caller to run a scan first,
rather than starting one itself.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException

from backend.ranking.engine import RankedCandidate, StrengthBreakdown, build_ranking
from backend.services import config_store
from backend.services.instrument_classifier import get_instrument_type
from backend.services.scan_job_manager import get_cached_result
from backend.strategies.types import StrategySignal

router = APIRouter(prefix="/api/ranking", tags=["ranking"])


def _breakdown_out(b: StrengthBreakdown) -> dict:
    return {"strength": b.strength, "components": b.components}


def _candidate_out(c: RankedCandidate) -> dict:
    return {
        "symbol": c.symbol,
        "instrument_type": get_instrument_type(c.symbol),
        "score": c.score,
        "best_strategy": c.best_strategy,
        "strategies": c.qualifying_strategies,
        "strategy_breakdown": {name: _breakdown_out(entry.breakdown) for name, entry in c.strategy_scores.items()},
    }


def _load_signals_from_cache() -> tuple[dict[str, list[StrategySignal]], dict]:
    """Rebuilds StrategySignal objects from the cached A Group scan's plain
    JSON (StrategySignalOut has the exact same field names as StrategySignal,
    so this is a direct reconstruction, not a re-derivation of anything)."""
    cached = get_cached_result("a_group")
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="No A Group scan result available yet — run a scan first (ranking never starts one itself).",
        )
    raw_strategies: dict[str, list[dict]] = cached["result"].get("strategies", {})
    signals = {
        name: [StrategySignal(**{k: v for k, v in sig.items() if k in StrategySignal.__dataclass_fields__}) for sig in sigs]
        for name, sigs in raw_strategies.items()
        if name != "PRD Forming"  # developing setups are not confirmed signals — never ranked
    }
    return signals, cached


@router.get("/latest")
def get_latest_ranking() -> dict:
    signals, cached = _load_signals_from_cache()
    config = config_store.get_current_multi_strategy_config()
    ranking = build_ranking(signals, config)

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scan_completed_at": cached["completed_at"],
        "top_candidates": [_candidate_out(c) for c in ranking.top_candidates],
        "strategy_best": {
            name: (_candidate_out(c) if c is not None else None) for name, c in ranking.strategy_best.items()
        },
        "total_candidates": len(ranking.candidates),
    }


@router.get("/top")
def get_top_candidates(limit: int = 5) -> dict:
    signals, cached = _load_signals_from_cache()
    config = config_store.get_current_multi_strategy_config()
    ranking = build_ranking(signals, config)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "candidates": [_candidate_out(c) for c in ranking.candidates[:limit]],
    }


@router.get("/strategy/{strategy}")
def get_strategy_ranking(strategy: str) -> dict:
    signals, cached = _load_signals_from_cache()
    if strategy not in signals:
        raise HTTPException(status_code=404, detail=f"Unknown strategy '{strategy}'.")
    config = config_store.get_current_multi_strategy_config()
    ranking = build_ranking(signals, config)

    same_strategy_candidates = [c for c in ranking.candidates if strategy in c.qualifying_strategies]
    same_strategy_candidates.sort(key=lambda c: c.strategy_scores[strategy].strength or 0.0, reverse=True)

    return {
        "strategy": strategy,
        "top_candidate": _candidate_out(ranking.strategy_best[strategy]) if ranking.strategy_best.get(strategy) else None,
        "candidates": [_candidate_out(c) for c in same_strategy_candidates],
    }

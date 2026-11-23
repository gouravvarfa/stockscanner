"""Thrust check (2026-11-23): is a single stock's move from its last swing "stretched"?

Rule, as tested on 613 series 2005-2026 (A Group, indices, gold, silver, crude):
- swing pivots: highest high / lowest low of +-10 daily bars, alternating; a pivot counts only once 10 bars have
  closed after it (no look-ahead)
- ATR: simple 14-day mean of the true range, taken at the pivot
- pace: the move from the pivot in the new direction, in ATRs per candle elapsed. A thrust fires at the first bar
  where pace >= 1.0 (from the 5th candle on).
- climax: the thrust bar has a true range >= 1.5 ATR on volume >= 1.5x the 20-day average

What the test found (live, confirmed pivots): a new swing formed within +-3 bars 42-53% of the time against about
33% at random, and price moved 1 ATR back against the thrust 80-86% of the time, usually in 1-2 bars. Trading
against the thrust (stop beyond its extreme, 1R/2R) averaged about 0R, so this is a warning ("stretched, do not
chase"), never an entry signal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.market_data_router import DataUnavailableError
from backend.services import gann_time_service as gann

STRENGTH = 10
ATR_LEN = 14
MIN_BARS = 5
PACE = 1.0
FRESH_BARS = 3  # a thrust is "now" while it fired within the last 3 bars
LOOKBACK = 60

# The record behind the warning (scratchpad thrust test, ratio 1, confirmed pivots); shown on the page.
RECORD = {"turn_within_3": "42-53%", "turn_random": "33%", "back_1atr": "80-86%", "avg_r": "about 0R"}


def _pivots(high: np.ndarray, low: np.ndarray) -> list[tuple[int, int, float]]:
    """Confirmed alternating swing pivots: (bar, +1 high / -1 low, price)."""
    k = STRENGTH
    found: list[list] = []
    for i in range(k, len(high) - k):
        if high[i] == high[i - k:i + k + 1].max():
            p = [i, 1, float(high[i])]
        elif low[i] == low[i - k:i + k + 1].min():
            p = [i, -1, float(low[i])]
        else:
            continue
        if found and found[-1][1] == p[1]:
            if (p[1] == 1 and p[2] > found[-1][2]) or (p[1] == -1 and p[2] < found[-1][2]):
                found[-1] = p
        else:
            found.append(p)
    return [(int(a), int(b), float(c)) for a, b, c in found]


def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev = np.r_[close[0], close[:-1]]
    return np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))


def _thrust_from(p: int, kind: int, price: float, high, low, tr, vol, vma, end: int) -> dict | None:
    """The first bar after pivot p (up to `end`) where the move reaches PACE ATR per candle."""
    if p < ATR_LEN:
        return None
    atr = float(tr[p - ATR_LEN + 1:p + 1].mean())
    if atr <= 0:
        return None
    up = kind == -1  # after a low the thrust is up
    for k in range(MIN_BARS, LOOKBACK + 1):
        i = p + k
        if i > end:
            break
        move = (high[i] - price) if up else (price - low[i])
        if move >= PACE * atr * k:
            climax = bool(tr[i] >= 1.5 * atr and vma[i] > 0 and vol[i] >= 1.5 * vma[i])
            return {"bar": i, "bars": k, "atr": atr, "move": float(move), "pace": float(move / (atr * k)), "up": up, "climax": climax}
    return None


def evaluate(df: pd.DataFrame) -> dict:
    df = df.sort_index()
    high, low, close = (df[c].to_numpy(dtype=float) for c in ("high", "low", "close"))
    vol = df["volume"].to_numpy(dtype=float) if "volume" in df else np.zeros(len(df))
    vma = pd.Series(vol).rolling(20).mean().shift(1).fillna(0).to_numpy()
    tr = _true_range(high, low, close)
    dates = [d.date().isoformat() for d in pd.to_datetime(df.index)]
    last = len(df) - 1
    piv = _pivots(high, low)
    if not piv:
        raise ValueError("Not enough history to find a swing.")

    def date_of(i: int) -> str:
        return dates[i]

    # the live view: the last confirmed pivot and the move since it
    p, kind, price = piv[-1]
    atr = float(tr[max(0, p - ATR_LEN + 1):p + 1].mean())
    up = kind == -1
    bars = last - p
    move = (high[p + 1:].max() - price) if up else (price - low[p + 1:].min()) if bars > 0 else 0.0
    pace = float(move / (atr * bars)) if bars > 0 and atr > 0 else 0.0
    thrust = _thrust_from(p, kind, price, high, low, tr, vol, vma, last)
    status = "normal"
    if thrust is not None:
        status = "stretched" if last - thrust["bar"] <= FRESH_BARS else "fired"

    # this stock's own record: every past thrust, and whether a new swing formed within +-3 bars
    pidx = [q[0] for q in piv]
    history = []
    for j, (q, qk, qp) in enumerate(piv):
        nxt = piv[j + 1][0] if j + 1 < len(piv) else last
        t = _thrust_from(q, qk, qp, high, low, tr, vol, vma, min(last, nxt + 3))
        if t is None:
            continue
        turned = any(abs(x - t["bar"]) <= 3 for x in pidx if x != q)
        after = min(last, t["bar"] + 10)
        back = (close[t["bar"]] - low[t["bar"] + 1:after + 1].min()) if t["up"] else (high[t["bar"] + 1:after + 1].max() - close[t["bar"]])
        history.append({
            "date": date_of(t["bar"]), "from_date": date_of(q), "direction": "up" if t["up"] else "down",
            "bars": t["bars"], "pace": round(t["pace"], 2), "climax": t["climax"],
            "turned": bool(turned) if t["bar"] + 3 <= last else None,
            "back_atr": round(float(back) / t["atr"], 2) if t["bar"] < last else None,
        })
    done = [h for h in history if h["turned"] is not None]
    return {
        "last_date": dates[last],
        "last_close": round(float(close[last]), 2),
        "status": status,
        "pivot": {"kind": "low" if up else "high", "date": date_of(p), "price": round(price, 2)},
        "direction": "up" if up else "down",
        "bars_since": bars,
        "atr": round(atr, 2),
        "move": round(float(move), 2),
        "pace": round(pace, 2),
        "need_for_thrust": round(PACE * atr * max(bars, MIN_BARS), 2),
        "thrust": None if thrust is None else {
            "date": date_of(thrust["bar"]), "bars": thrust["bars"], "pace": round(thrust["pace"], 2),
            "climax": thrust["climax"], "bars_ago": last - thrust["bar"],
        },
        "history": history[-12:][::-1],
        "own_record": {"thrusts": len(done), "turned": sum(1 for h in done if h["turned"])},
        "record": RECORD,
    }


async def analyse_symbol(provider: AngelOneProvider, symbol: str) -> dict:
    sym = symbol.strip().upper()
    df = await gann._daily(provider, sym)
    if df is None or len(df) < 60:
        raise DataUnavailableError(f"Not enough daily candles for {sym}.")
    out = evaluate(df)
    out["symbol"] = sym
    out["company_name"] = gann.company_name(sym)
    return out

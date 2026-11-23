"""Outlook (2026-11-23): the live numbers behind the Outlook page.

- Nifty's expected range for the next week / month from India VIX (the market's own volatility forecast):
  move = close x VIX/100 x sqrt(days/252); 1 sigma (~68%) and 2 sigma (~95%).
- Gold and Silver (MCX front-month futures): the same range from their last 20 days' realised volatility.
- Market weather: Nifty against its 50- and 200-day averages, and the India VIX band.
Everything is read from Angel One; nothing is stored (a short in-memory cache keeps repeat visits cheap).
The historical records shown next to these numbers are computed offline (frontend/src/data/outlookRecord.json).
"""
from __future__ import annotations

import datetime as dt
import math
import time

import numpy as np
import pandas as pd

from backend.providers.angelone_provider import AngelOneProvider
from backend.services import chart_service, gann_time_service

CACHE_SECONDS = 15 * 60
_cache: tuple[float, dict] | None = None


def _ranges(close: float, annual_vol_pct: float) -> dict:
    out = {}
    for label, days in (("week", 5), ("month", 21)):
        move = close * annual_vol_pct / 100 * math.sqrt(days / 252)
        out[label] = {"days": days, "move_1s": round(move, 2), "move_pct_1s": round(100 * move / close, 2),
                      "low_1s": round(close - move, 2), "high_1s": round(close + move, 2),
                      "low_2s": round(close - 2 * move, 2), "high_2s": round(close + 2 * move, 2)}
    return out


def vix_band(v: float) -> str:
    return "calm (<14)" if v < 14 else "normal (14-18)" if v < 18 else "nervous (18-24)" if v < 24 else "fearful (24+)"


def trend_of(close: float, d50: float | None, d200: float | None) -> str:
    if d50 is None or d200 is None:
        return "unknown"
    if close > d50 and close > d200:
        return "uptrend (above 50 & 200-DMA)"
    if close < d50 and close < d200:
        return "downtrend (below 50 & 200-DMA)"
    return "mixed (between the averages)"


def _realised_vol(df: pd.DataFrame, days: int = 20) -> float:
    r = np.log(df["close"].astype(float)).diff().dropna().tail(days)
    return float(r.std() * math.sqrt(252) * 100)


async def snapshot(provider: AngelOneProvider) -> dict:
    global _cache
    if _cache and time.time() - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    nifty = (await chart_service.get_candles(provider, "NIFTY", "1D")).sort_index()
    vix = (await chart_service.get_candles(provider, "INDIA VIX", "1D")).sort_index()
    c = nifty["close"].astype(float)
    close, v = float(c.iloc[-1]), float(vix["close"].iloc[-1])
    d50 = float(c.tail(50).mean()) if len(c) >= 50 else None
    d200 = float(c.tail(200).mean()) if len(c) >= 200 else None
    out: dict = {
        "as_of": dt.datetime.utcnow().isoformat() + "Z",
        "nifty": {"close": round(close, 2), "date": str(c.index[-1].date()), "dma50": d50 and round(d50, 2),
                  "dma200": d200 and round(d200, 2), "trend": trend_of(close, d50, d200),
                  "vix": round(v, 2), "vix_date": str(vix.index[-1].date()), "vix_band": vix_band(v),
                  "ranges": _ranges(close, v)},
        "commodities": [],
    }
    for sym, name in (("GOLD", "Gold"), ("SILVER", "Silver")):
        try:
            df = (await gann_time_service._commodity_daily(provider, sym)).sort_index()
            vol = _realised_vol(df)
            cl = float(df["close"].iloc[-1])
            out["commodities"].append({"symbol": sym, "name": name, "close": round(cl, 2), "date": str(df.index[-1].date()),
                                       "vol": round(vol, 1), "ranges": _ranges(cl, vol)})
        except Exception as exc:  # noqa: BLE001 - one commodity without data must not hide the rest
            out["commodities"].append({"symbol": sym, "name": name, "error": str(exc)})
    _cache = (time.time(), out)
    return out

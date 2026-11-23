"""
Intraday (15m/1h) OHLCV provider backed by Angel One SmartAPI — used only by
Expiry Level 1. Session is authenticated lazily and cached in-process (a
fresh TOTP-based login each time would waste Angel's rate limits and the
30-second TOTP window makes rapid re-logins fragile).
"""
from __future__ import annotations

import asyncio

import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

from backend.indicators.confirmed_bars import drop_incomplete_trailing_bars, drop_incomplete_trailing_daily_bar
from backend.providers import angelone_scrip_master as scrip_master
from backend.providers.angelone_client import AngelOneApiError, AngelOneInterval, AngelOneSession, get_candle_data, login
from backend.services import angelone_credential_store

IST = ZoneInfo("Asia/Kolkata")

INTERVAL_MINUTES: dict[AngelOneInterval, int] = {
    "FIFTEEN_MINUTE": 15,
    "ONE_HOUR": 60,
}



def _rate_limited(exc: Exception) -> bool:
    """Angel One's rate limiter: HTTP 403 with a non-JSON body, or "Too many requests". Not a dead session, so it
    must NOT trigger a re-login (2026-11-23: every re-login invalidated the session the other parallel requests were
    using, which turned a short rate-limit burst into a cascade of failures and logins)."""
    text = str(exc).lower()
    return "http 403" in text or "too many requests" in text


async def _rate_limit_pause() -> None:
    await asyncio.sleep(RATE_LIMIT_PAUSE_S)


RATE_LIMIT_PAUSE_S = 4.0

class AngelOneNotConfiguredError(RuntimeError):
    pass


def _format_angel_date(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")


class AngelOneProvider:
    def __init__(self) -> None:
        self._session: AngelOneSession | None = None

    async def _ensure_session(self) -> AngelOneSession:
        credentials = angelone_credential_store.get_credentials()
        if credentials is None:
            raise AngelOneNotConfiguredError(
                "Angel One credentials not configured — connect from the Expiry Level 1 page, "
                "or set ANGELONE_API_KEY/CLIENT_CODE/PIN/TOTP_SECRET in .env."
            )
        if self._session is None:
            self._session = await login(
                credentials.api_key, credentials.client_code, credentials.pin, credentials.totp_secret
            )
        return self._session

    def reset_session(self) -> None:
        """Forces the next request to re-authenticate — call after credentials change."""
        self._session = None

    async def get_session(self) -> AngelOneSession:
        """Public accessor for the SAME session every REST call already
        uses — added 2026-09-25 for backend/live/market_data_service.py's
        WebSocket handshake (Authorization/x-api-key/x-client-code/
        x-feed-token), so the live engine never creates a second
        authentication path."""
        return await self._ensure_session()

    async def _fetch_rows(self, call):
        """One candle request with recovery (2026-11-23).
        - Rate limit (HTTP 403 / too many requests): pause and retry with the SAME session - no re-login.
        - Still failing, or any other API error: the session may be dead (Angel allows ONE active session per account;
          a login elsewhere silently kills ours), so exactly one fresh login and one retry. Only the first caller that
          sees the dead session resets it; parallel callers reuse the new one instead of each logging in again
          (every login kills the session the others are using - that cascade made whole scans crawl)."""
        session = await self._ensure_session()
        try:
            return await call(session)
        except AngelOneApiError as exc:
            if _rate_limited(exc):
                await _rate_limit_pause()
                try:
                    return await call(session)
                except AngelOneApiError:
                    pass
            if self._session is session:
                self.reset_session()
            session = await self._ensure_session()
            return await call(session)

    async def get_intraday_ohlc(
        self, exch_seg: str, symbol_token: str, interval: AngelOneInterval, days_back: int = 5,
        include_partial: bool = False,
    ) -> pd.DataFrame:
        """
        Returns a DataFrame of ONLY fully-closed candles (the still-forming
        current bar, if any, is dropped) — this is what makes "use only
        confirmed candles" true regardless of when during the session this
        is called.

        include_partial=True (2026-09-28, chart-only) keeps that still-
        forming current bar instead of dropping it — Angel One's own
        historical-candle endpoint already returns it (built from real
        completed ticks up to now, never fabricated); every OTHER caller
        (the scanner's daily fetch via market_data_router.py, Expiry Level
        1/5) omits this and is completely unaffected — they still only ever
        see confirmed candles, exactly as before.
        """
        now_ist = dt.datetime.now(IST)
        from_dt = now_ist - dt.timedelta(days=days_back)
        from_date = _format_angel_date(from_dt.replace(tzinfo=None))
        to_date = _format_angel_date(now_ist.replace(tzinfo=None))

        rows = await self._fetch_rows(lambda ses: get_candle_data(
            ses, exchange=exch_seg, symbol_token=symbol_token, interval=interval, from_date=from_date, to_date=to_date,
        ))

        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df.set_index("date").sort_index()

        now_naive = now_ist.replace(tzinfo=None)
        if not include_partial:
            if interval == "ONE_DAY":
                # MCX trades until 23:30 (23:55 in the US-DST months): its day is not complete at NSE's 15:30.
                df = drop_incomplete_trailing_daily_bar(
                    df, now_naive, dt.time(23, 55) if exch_seg == "MCX" else dt.time(15, 30))
            else:
                df = drop_incomplete_trailing_bars(df, INTERVAL_MINUTES[interval], now_naive)

        return df[["open", "high", "low", "close", "volume"]].astype(float)

    async def get_daily_ohlc_range(
        self, exch_seg: str, symbol_token: str, from_dt: dt.datetime, to_dt: dt.datetime
    ) -> pd.DataFrame:
        """
        Same session/retry-on-dead-session handling as get_intraday_ohlc,
        but for an EXPLICIT date range instead of "the last N days from
        now" — used only by the Cup Breakout scanner's chunked multi-year
        history fetch (backend/providers/cup_history.py). Does not drop a
        trailing incomplete bar (the caller is asking for a specific past
        window, not "up to now"); Cup's own pipeline handles the current
        in-progress month separately via to_monthly().
        """
        from_date = _format_angel_date(from_dt)
        to_date = _format_angel_date(to_dt)
        rows = await self._fetch_rows(lambda ses: get_candle_data(
            ses, exchange=exch_seg, symbol_token=symbol_token, interval="ONE_DAY", from_date=from_date, to_date=to_date,
        ))
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df.set_index("date").sort_index()
        return df[["open", "high", "low", "close", "volume"]].astype(float)

    async def resolve_index(self, name: str) -> scrip_master.ScripMatch | None:
        return await scrip_master.resolve_index(name)

    async def resolve_equity(self, symbol: str) -> scrip_master.ScripMatch | None:
        return await scrip_master.resolve_equity(symbol)

    async def resolve_stock_future(self, symbol: str) -> scrip_master.ScripMatch | None:
        return await scrip_master.resolve_stock_future(symbol)

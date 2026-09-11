"""
Intraday (15m/1h) OHLCV provider backed by Angel One SmartAPI — used only by
Expiry Level 1. Session is authenticated lazily and cached in-process (a
fresh TOTP-based login each time would waste Angel's rate limits and the
30-second TOTP window makes rapid re-logins fragile).
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

from backend.indicators.confirmed_bars import drop_incomplete_trailing_bars, drop_incomplete_trailing_daily_bar
from backend.providers import angelone_scrip_master as scrip_master
from backend.providers.angelone_client import AngelOneInterval, AngelOneSession, get_candle_data, login
from backend.services import angelone_credential_store

IST = ZoneInfo("Asia/Kolkata")

INTERVAL_MINUTES: dict[AngelOneInterval, int] = {
    "FIFTEEN_MINUTE": 15,
    "ONE_HOUR": 60,
}


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

    async def get_intraday_ohlc(
        self, exch_seg: str, symbol_token: str, interval: AngelOneInterval, days_back: int = 5
    ) -> pd.DataFrame:
        """
        Returns a DataFrame of ONLY fully-closed candles (the still-forming
        current bar, if any, is dropped) — this is what makes "use only
        confirmed candles" true regardless of when during the session this
        is called.
        """
        session = await self._ensure_session()
        now_ist = dt.datetime.now(IST)
        from_dt = now_ist - dt.timedelta(days=days_back)

        rows = await get_candle_data(
            session,
            exchange=exch_seg,
            symbol_token=symbol_token,
            interval=interval,
            from_date=_format_angel_date(from_dt.replace(tzinfo=None)),
            to_date=_format_angel_date(now_ist.replace(tzinfo=None)),
        )

        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df.set_index("date").sort_index()

        now_naive = now_ist.replace(tzinfo=None)
        if interval == "ONE_DAY":
            df = drop_incomplete_trailing_daily_bar(df, now_naive)
        else:
            df = drop_incomplete_trailing_bars(df, INTERVAL_MINUTES[interval], now_naive)

        return df[["open", "high", "low", "close", "volume"]].astype(float)

    async def resolve_index(self, name: str) -> scrip_master.ScripMatch | None:
        return await scrip_master.resolve_index(name)

    async def resolve_equity(self, symbol: str) -> scrip_master.ScripMatch | None:
        return await scrip_master.resolve_equity(symbol)

    async def resolve_stock_future(self, symbol: str) -> scrip_master.ScripMatch | None:
        return await scrip_master.resolve_stock_future(symbol)

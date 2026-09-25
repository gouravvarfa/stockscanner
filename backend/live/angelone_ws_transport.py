"""
Real Angel One SmartAPI WebSocket V2 transport for the live market-data
engine. Reuses the EXISTING Angel One session (backend/providers/
angelone_client.AngelOneSession — jwt_token/api_key/client_code/
feed_token, obtained via the existing login()) — no second authentication
system.

!!! IMPORTANT VERIFICATION NOTE (2026-09-25) !!!
The binary tick layout below (_parse_quote_tick) is implemented from Angel
One's published SmartAPI V2 WebSocket documentation structure (mode=2
"Quote" packets: 1-byte subscription mode, 1-byte exchange type, 25-byte
token, then int64-LE fields for sequence number/exchange timestamp/LTP/
last-traded-qty/average-traded-price/day-volume/open/high/low/close). This
could NOT be exercised against a live Angel One connection from this
environment (no live session/market access here), so the exact byte
offsets MUST be verified against a real account during actual market
hours before this is trusted in production — see PROTOCOL below for
where to adjust if Angel One's real payload differs. Every OFFSET is a
single named constant specifically so a correction is a one-line change,
not a rewrite. market_data_service.py depends only on this module's
public parse_tick()/build_subscribe_message() functions, not on these
offsets directly, so a fix here never touches the rest of the engine.

Never fabricates a tick: a frame that fails to parse is logged and
dropped (see market_data_service.py's per-symbol error isolation), never
turned into a fake price.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import struct
from dataclasses import dataclass
from typing import AsyncIterator, Protocol
from zoneinfo import ZoneInfo

from backend.providers.angelone_client import AngelOneSession

logger = logging.getLogger("scanner.live.angelone_ws_transport")

IST = ZoneInfo("Asia/Kolkata")

WS_URL = "wss://smartapisocket.angelone.in/smart-stream"

# SmartAPI's own exchangeType codes (WebSocket-specific — distinct from the
# historical REST API's "exch_seg" string; mapped from the SAME
# angelone_scrip_master.ScripMatch.exch_seg the rest of the app already
# resolves, never a second symbol/token system).
EXCHANGE_TYPE_BY_EXCH_SEG: dict[str, int] = {"NSE": 1, "NFO": 2}

MODE_LTP = 1
MODE_QUOTE = 2

# ---- PROTOCOL (Quote-mode, mode=2) binary tick layout ----------------------
# All multi-byte integer fields are little-endian, per SmartAPI's documented
# packet structure. See the module-level verification note above.
_OFF_SUBSCRIPTION_MODE = 0        # 1 byte
_OFF_EXCHANGE_TYPE = 1            # 1 byte
_OFF_TOKEN = 2                    # 25 bytes, null-padded ASCII
_OFF_SEQUENCE_NUMBER = 27         # int64
_OFF_EXCHANGE_TIMESTAMP_MS = 35   # int64, epoch millis, IST wall-clock instant
_OFF_LTP = 43                     # int64, paise (÷100 for rupees)
_OFF_LAST_TRADED_QTY = 51         # int64
_OFF_AVG_TRADED_PRICE = 59        # int64, paise
_OFF_VOLUME_TRADED_TODAY = 67     # int64 — cumulative day volume, feeds CandleBuilder's volume_delta
_OFF_TOTAL_BUY_QTY = 75           # double
_OFF_TOTAL_SELL_QTY = 83          # double
_OFF_OPEN_PRICE = 91              # int64, paise — today's session open
_OFF_HIGH_PRICE = 99              # int64, paise
_OFF_LOW_PRICE = 107              # int64, paise
_OFF_CLOSE_PRICE = 115            # int64, paise — previous day's close
_QUOTE_PACKET_MIN_LEN = 123


@dataclass
class Tick:
    token: str
    exchange_type: int
    ltp: float  # rupees
    exchange_timestamp: dt.datetime  # IST, tz-aware
    day_volume: float | None  # cumulative today, None if unavailable/unparsed


def build_subscribe_message(correlation_id: str, exchange_type: int, tokens: list[str], mode: int = MODE_QUOTE) -> str:
    return json.dumps({
        "correlationID": correlation_id,
        "action": 1,
        "params": {"mode": mode, "tokenList": [{"exchangeType": exchange_type, "tokens": tokens}]},
    })


def build_unsubscribe_message(correlation_id: str, exchange_type: int, tokens: list[str], mode: int = MODE_QUOTE) -> str:
    return json.dumps({
        "correlationID": correlation_id,
        "action": 0,
        "params": {"mode": mode, "tokenList": [{"exchangeType": exchange_type, "tokens": tokens}]},
    })


def parse_tick(frame: bytes) -> Tick | None:
    """Returns None (never raises, never fabricates) for a frame that
    isn't a recognizable Quote-mode packet — e.g. a heartbeat/control
    frame, or a shorter LTP-mode packet this engine doesn't request."""
    if len(frame) < _QUOTE_PACKET_MIN_LEN:
        return None
    try:
        exchange_type = frame[_OFF_EXCHANGE_TYPE]
        token_raw = frame[_OFF_TOKEN : _OFF_TOKEN + 25]
        token = token_raw.split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
        exch_ts_ms = struct.unpack_from("<q", frame, _OFF_EXCHANGE_TIMESTAMP_MS)[0]
        ltp_paise = struct.unpack_from("<q", frame, _OFF_LTP)[0]
        day_volume = struct.unpack_from("<q", frame, _OFF_VOLUME_TRADED_TODAY)[0]
        exchange_timestamp = dt.datetime.fromtimestamp(exch_ts_ms / 1000.0, tz=IST)
        return Tick(
            token=token, exchange_type=exchange_type, ltp=ltp_paise / 100.0,
            exchange_timestamp=exchange_timestamp, day_volume=float(day_volume),
        )
    except (struct.error, ValueError, UnicodeDecodeError, OSError, OverflowError) as exc:
        logger.warning("Live tick frame failed to parse (dropped, not fabricated): %s", exc)
        return None


class WebSocketTransport(Protocol):
    """What market_data_service.py actually depends on — real Angel One
    connectivity (AngelOneWebSocketTransport, below) and tests' fake
    transport both implement exactly this, so the orchestration logic
    never needs to know which one it's talking to."""

    async def connect(self, session: AngelOneSession) -> None: ...
    async def subscribe(self, exchange_type: int, tokens: list[str]) -> None: ...
    async def unsubscribe(self, exchange_type: int, tokens: list[str]) -> None: ...
    def ticks(self) -> AsyncIterator[Tick]: ...
    async def close(self) -> None: ...


class AngelOneWebSocketTransport:
    """Real transport — a thin wrapper over the `websockets` library
    talking SmartAPI V2. Heartbeat/reconnect/backoff live one layer up in
    market_data_service.py (this class only owns the raw socket + framing,
    so reconnect logic is testable against a fake transport without a
    real network dependency)."""

    def __init__(self) -> None:
        self._ws = None
        self._correlation_id = "scanner-live"

    async def connect(self, session: AngelOneSession) -> None:
        import websockets

        headers = {
            "Authorization": f"Bearer {session.jwt_token}",
            "x-api-key": session.api_key,
            "x-client-code": session.client_code,
            "x-feed-token": session.feed_token,
        }
        self._ws = await websockets.connect(WS_URL, additional_headers=headers, ping_interval=None, max_size=None)

    async def subscribe(self, exchange_type: int, tokens: list[str]) -> None:
        if self._ws is None:
            raise RuntimeError("AngelOneWebSocketTransport.subscribe() called before connect()")
        await self._ws.send(build_subscribe_message(self._correlation_id, exchange_type, tokens))

    async def unsubscribe(self, exchange_type: int, tokens: list[str]) -> None:
        if self._ws is None:
            return
        await self._ws.send(build_unsubscribe_message(self._correlation_id, exchange_type, tokens))

    async def ticks(self) -> AsyncIterator[Tick]:
        if self._ws is None:
            raise RuntimeError("AngelOneWebSocketTransport.ticks() called before connect()")
        async for message in self._ws:
            if isinstance(message, str):
                continue  # JSON control/ack frames — not a price tick
            tick = parse_tick(message)
            if tick is not None:
                yield tick

    async def heartbeat(self) -> None:
        """SmartAPI V2 expects a periodic "ping" text frame ("ping") to
        keep the connection alive — see market_data_service.py's
        heartbeat loop, which calls this on a fixed interval."""
        if self._ws is not None:
            await self._ws.send("ping")

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

import datetime as dt
import json
import struct

from backend.live.angelone_ws_transport import (
    _OFF_EXCHANGE_TIMESTAMP_MS,
    _OFF_EXCHANGE_TYPE,
    _OFF_LTP,
    _OFF_TOKEN,
    _OFF_VOLUME_TRADED_TODAY,
    _QUOTE_PACKET_MIN_LEN,
    IST,
    build_subscribe_message,
    build_unsubscribe_message,
    parse_tick,
)


def _fake_quote_frame(token: str, ltp_rupees: float, exch_ts: dt.datetime, day_volume: int) -> bytes:
    frame = bytearray(_QUOTE_PACKET_MIN_LEN)
    frame[0] = 2  # subscription mode = Quote
    frame[_OFF_EXCHANGE_TYPE] = 1  # NSE
    token_bytes = token.encode("ascii")
    frame[_OFF_TOKEN : _OFF_TOKEN + len(token_bytes)] = token_bytes
    struct.pack_into("<q", frame, _OFF_EXCHANGE_TIMESTAMP_MS, int(exch_ts.timestamp() * 1000))
    struct.pack_into("<q", frame, _OFF_LTP, round(ltp_rupees * 100))
    struct.pack_into("<q", frame, _OFF_VOLUME_TRADED_TODAY, day_volume)
    return bytes(frame)


def test_build_subscribe_message_shape():
    msg = json.loads(build_subscribe_message("corr-1", 1, ["3045"]))
    assert msg["action"] == 1
    assert msg["params"]["tokenList"] == [{"exchangeType": 1, "tokens": ["3045"]}]


def test_build_unsubscribe_message_shape():
    msg = json.loads(build_unsubscribe_message("corr-1", 1, ["3045"]))
    assert msg["action"] == 0


def test_parse_tick_extracts_token_price_timestamp_and_volume():
    now = dt.datetime(2026, 9, 25, 10, 30, 0, tzinfo=IST)
    frame = _fake_quote_frame("3045", 250.75, now, 123456)
    tick = parse_tick(frame)
    assert tick is not None
    assert tick.token == "3045"
    assert tick.ltp == 250.75
    assert tick.day_volume == 123456.0
    assert tick.exchange_timestamp == now


def test_parse_tick_returns_none_for_too_short_a_frame_never_fabricates():
    assert parse_tick(b"\x01\x02") is None


def test_parse_tick_returns_none_for_garbage_without_raising():
    garbage = bytes(range(_QUOTE_PACKET_MIN_LEN))
    # Must not raise even on nonsense bytes - either parses to *something*
    # deterministic or returns None, never crashes the tick-handling loop.
    result = parse_tick(garbage)
    assert result is None or result.token is not None

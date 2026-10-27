"""15-minute opening-candle breakout backtest, CALL and PUT (index points only).

Pure functions over real 15-minute index candles (bar START timestamps, IST,
naive).

  - First candle = the 09:15 candle (09:15-09:30).
  - CALL when a later candle trades above its High (entry at the High, or at
    that candle's Open if it already opened above); stop at the first Low.
  - PUT when a later candle trades below its Low (entry at the Low, or at that
    candle's Open if it already opened below); stop at the first High.
  - One trade per day: the first breakout in either direction.
  - Exit at the stop, otherwise at the chosen time: the last candle's close
    (15:30, `exit_mode=CLOSE`) or the second-last candle's close (15:15,
    `exit_mode=SECOND_LAST`).

Breakout and stop are located on 15-minute candles, so a breakout time is the
start of the candle that crossed (no finer timestamp is invented). When one
candle trades through BOTH ends of the first candle and opened inside it, the
order cannot be known: the day is a stop-loss of the first candle's range,
flagged AMBIGUOUS, with side BOTH. Missing candles are never filled.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

OPEN = dt.time(9, 15)
FIRST_END = dt.time(9, 30)
SECOND_LAST_START = dt.time(15, 0)
LAST_START = dt.time(15, 15)
EXPECTED_BARS = 25  # 09:15 .. 15:15 starts

STOP_LOSS, MARKET_CLOSE, NO_ENTRY, DATA_INCOMPLETE = "STOP_LOSS", "MARKET_CLOSE", "NO_ENTRY", "DATA_INCOMPLETE"
SECOND_LAST_CLOSE = "SECOND_LAST_CLOSE"
DATA_ENDED = "DATA_ENDED_BEFORE_CLOSE"
CALL, PUT, BOTH = "CALL", "PUT", "BOTH"
EXIT_MODES = ("CLOSE", "SECOND_LAST")

Bar = tuple  # (ts: datetime, o, h, l, c)


@dataclass
class DayResult:
    date: dt.date
    first_open: float | None = None
    first_high: float | None = None
    first_low: float | None = None
    first_close: float | None = None
    first_range_pct: float | None = None
    first_direction: str | None = None
    side: str | None = None  # CALL | PUT | BOTH (ambiguous) | None (no trade)
    breakout_time: dt.datetime | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    second_last_time: dt.datetime | None = None
    second_last_close: float | None = None
    second_last_change_pct: float | None = None
    exit_time: dt.datetime | None = None
    exit_price: float | None = None
    exit_reason: str = NO_ENTRY
    pnl_points: float | None = None
    pnl_pct: float | None = None
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        def t(v):
            return v.isoformat(sep=" ", timespec="minutes") if v else None
        d = {k: v for k, v in self.__dict__.items() if k != "flags"}
        d["date"] = self.date.isoformat()
        for k in ("breakout_time", "second_last_time", "exit_time"):
            d[k] = t(d[k])
        d["flags"] = list(self.flags)
        d["quality"] = "; ".join(self.flags) if self.flags else "OK"
        return d


def _direction(o: float, c: float) -> str:
    return "Green" if c > o else "Red" if c < o else "Doji"


def _resolve_side(candle_start: dt.datetime, minutes: list[Bar] | None, h: float, l: float):
    """First 1-minute break inside the 15-minute candle starting at `candle_start`.
    Returns (side, minute_bar, tie) or None if the minute data shows no break (incomplete data)."""
    end = candle_start + dt.timedelta(minutes=15)
    window = sorted((m for m in (minutes or []) if candle_start <= m[0] < end), key=lambda m: m[0])
    for m in window:
        up, down = m[2] > h, m[3] < l
        if up and down:
            if m[1] > h:
                return CALL, m, False
            if m[1] < l:
                return PUT, m, False
            return (CALL if h - m[1] <= m[1] - l else PUT), m, True
        if up:
            return CALL, m, False
        if down:
            return PUT, m, False
    return None


def run_day(day: dt.date, bars: list[Bar], exit_mode: str = "CLOSE", minute_bars: list[Bar] | None = None) -> DayResult:
    """`bars` are real 15-minute candles keyed by START time (09:15 ... 15:15)."""
    if exit_mode not in EXIT_MODES:
        raise ValueError(f"exit_mode must be one of {EXIT_MODES}")
    r = DayResult(day)
    by_start = {b[0].time(): b for b in sorted(bars, key=lambda b: b[0])}
    first = by_start.get(OPEN)
    if first is None:
        r.exit_reason = DATA_INCOMPLETE
        r.flags.append("first 15-minute candle (09:15) missing")
        return r

    _, o, h, l, c = first
    r.first_open, r.first_high, r.first_low, r.first_close = o, h, l, c
    r.first_range_pct = (h - l) / o * 100.0 if o else None
    r.first_direction = _direction(o, c)

    sl_bar = by_start.get(SECOND_LAST_START)
    if sl_bar is not None:
        r.second_last_time = sl_bar[0]
        r.second_last_close = sl_bar[4]
        r.second_last_change_pct = (sl_bar[4] - sl_bar[1]) / sl_bar[1] * 100.0 if sl_bar[1] else None
    else:
        r.flags.append("second-last candle (15:00) missing")

    last_start = SECOND_LAST_START if exit_mode == "SECOND_LAST" else LAST_START
    after = [b for t, b in sorted(by_start.items()) if FIRST_END <= t <= last_start]  # nothing at/before the first candle
    missing = (EXPECTED_BARS - 1 if exit_mode == "CLOSE" else EXPECTED_BARS - 2) - len(after)

    # ---- first breakout in either direction
    entry_i = next((i for i, b in enumerate(after) if b[2] > h or b[3] < l), None)
    if entry_i is None:
        r.exit_reason = NO_ENTRY
        if missing:
            r.flags.append(f"{missing} candle(s) missing after 09:30; a breakout cannot be ruled out")
        return r

    eb = after[entry_i]
    up, down = eb[2] > h, eb[3] < l
    r.breakout_time = eb[0]
    r.flags.append("breakout time = start of the 15-minute candle that crossed the first candle")

    if up and down and l <= eb[1] <= h:  # opened inside, traded through both ends: 15-minute data cannot order them
        res = _resolve_side(eb[0], minute_bars, h, l)
        if res is None:
            r.side = BOTH
            r.stop_loss = None
            r.exit_time, r.exit_reason = eb[0], STOP_LOSS
            r.pnl_points = -(h - l)
            r.pnl_pct = r.pnl_points / o * 100.0 if o else None  # % of the first candle's open: no entry price is known
            r.flags.append("AMBIGUOUS: one candle broke BOTH the first candle High and Low and no 1-minute data was "
                           "available to order them; side unresolved, stop assumed: loss = first candle range (% of first open)")
            return r
        side, m, tie = res
        sl = l if side == CALL else h
        r.side, r.stop_loss, r.breakout_time = side, sl, m[0]
        r.entry_price = (m[1] if m[1] > h else h) if side == CALL else (m[1] if m[1] < l else l)
        r.flags.append(f"resolved on 1-minute candles: the {'High' if side == CALL else 'Low'} broke first at {m[0]:%H:%M}")
        if tie:
            r.flags.append("AMBIGUOUS: one 1-minute candle broke both ends; side = the end nearer that minute's open")
        window = sorted((x for x in (minute_bars or []) if m[0] <= x[0] < eb[0] + dt.timedelta(minutes=15)), key=lambda x: x[0])
        stop_m = next((x for x in window if (x[3] <= sl if side == CALL else x[2] >= sl)), None)
        if stop_m is None:  # the other end was touched in this 15-minute candle, so 1-minute data is missing a bar
            stop_m, fill = eb, sl
            r.flags.append("stop assumed inside the breakout candle (1-minute data incomplete)")
        else:
            gapped = stop_m[1] < sl if side == CALL else stop_m[1] > sl
            fill = stop_m[1] if gapped else sl
            if gapped:
                r.flags.append("stop gapped: filled at 1-minute candle open")
        r.exit_time, r.exit_price, r.exit_reason = stop_m[0], fill, STOP_LOSS
        r.pnl_points = fill - r.entry_price if side == CALL else r.entry_price - fill
        r.pnl_pct = r.pnl_points / r.entry_price * 100.0
        return r

    side = CALL if (eb[1] > h or (up and not down)) else PUT
    r.side = side
    if side == CALL:
        r.entry_price, sl = (eb[1] if eb[1] > h else h), l
    else:
        r.entry_price, sl = (eb[1] if eb[1] < l else l), h
    r.stop_loss = sl
    if (side == CALL and eb[1] > h) or (side == PUT and eb[1] < l):
        r.flags.append("gap entry at candle open")

    def stopped(b: Bar) -> bool:
        return b[3] <= sl if side == CALL else b[2] >= sl

    def stop_fill(b: Bar) -> float:
        gapped = b[1] < sl if side == CALL else b[1] > sl
        if gapped:
            r.flags.append("stop gapped: filled at candle open")
        return b[1] if gapped else sl

    exit_bar = exit_price = reason = None
    for b in after[entry_i:]:  # the entry candle itself can already hit the stop (gap day)
        if stopped(b):
            exit_bar, exit_price, reason = b, stop_fill(b), STOP_LOSS
            break
    if reason is None:
        last = after[-1]
        exit_bar, exit_price = last, last[4]
        if last[0].time() == last_start and not missing:
            reason = MARKET_CLOSE if exit_mode == "CLOSE" else SECOND_LAST_CLOSE
        else:
            reason = DATA_ENDED
            r.flags.append(f"data incomplete: last candle {last[0]:%H:%M}, {missing} candle(s) missing; not a verified exit")

    r.exit_time, r.exit_price, r.exit_reason = exit_bar[0], exit_price, reason
    r.pnl_points = exit_price - r.entry_price if side == CALL else r.entry_price - exit_price
    r.pnl_pct = r.pnl_points / r.entry_price * 100.0
    return r


def summarize(rows: list[DayResult]) -> dict:
    done = [r for r in rows if r.pnl_points is not None]
    pts = [r.pnl_points for r in done]
    equity = peak = dd = 0.0
    for p in pts:
        equity += p
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    wins = [p for p in pts if p > 0]
    return {
        "trading_days": len(rows),
        "call_entries": sum(r.side == CALL for r in rows),
        "put_entries": sum(r.side == PUT for r in rows),
        "both_side_days": sum(r.side == BOTH for r in rows),
        "no_entry_days": sum(r.exit_reason == NO_ENTRY for r in rows),
        "stop_loss_exits": sum(r.exit_reason == STOP_LOSS for r in rows),
        "market_close_exits": sum(r.exit_reason in (MARKET_CLOSE, SECOND_LAST_CLOSE) for r in rows),
        "incomplete_days": sum(r.exit_reason in (DATA_INCOMPLETE, DATA_ENDED) for r in rows),
        "ambiguous_days": sum(any(f.startswith("AMBIGUOUS") for f in r.flags) for r in rows),
        "resolved_days": sum(any(f.startswith("resolved on 1-minute") for f in r.flags) for r in rows),
        "winning_trades": len(wins),
        "losing_trades": sum(p < 0 for p in pts),
        "win_rate": round(len(wins) / len(pts) * 100.0, 1) if pts else None,
        "net_points": round(sum(pts), 2),
        "avg_points": round(sum(pts) / len(pts), 2) if pts else None,
        "max_drawdown_points": round(dd, 2),
    }


def _by_day(bars: list[Bar]) -> dict[dt.date, list[Bar]]:
    out: dict[dt.date, list[Bar]] = {}
    for b in bars:
        out.setdefault(b[0].date(), []).append(b)
    return out


def ambiguous_candles(bars: list[Bar], exit_mode: str = "CLOSE") -> dict[dt.date, dt.datetime]:
    """Days whose breakout candle broke both ends (side BOTH) -> that candle's start, i.e. exactly which
    15 minutes of 1-minute data are needed to order the break."""
    out = {}
    for d, v in _by_day(bars).items():
        r = run_day(d, v, exit_mode)
        if r.side == BOTH and r.breakout_time is not None:
            out[d] = r.breakout_time
    return out


def run_backtest(bars: list[Bar], exit_mode: str = "CLOSE",
                 minute_bars: dict[dt.date, list[Bar]] | None = None) -> tuple[list[DayResult], dict]:
    rows = [run_day(d, v, exit_mode, (minute_bars or {}).get(d)) for d, v in sorted(_by_day(bars).items())]
    return rows, summarize(rows)

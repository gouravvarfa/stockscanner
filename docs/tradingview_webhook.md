# TradingView Webhook Integration

TradingView is an **optional, additional signal source** wired into the
scanner via a webhook. It does not replace, and cannot influence, the
existing Tapetide/Angel One-driven scan — the two live side by side, clearly
labeled in the UI.

Disabled by default (`TRADINGVIEW_ENABLED=false`). While disabled, the
webhook endpoint always returns `success: false` and nothing in the rest of
the app is affected.

## Endpoint

`POST /api/tradingview/webhook`

### Auth

Every request must carry the secret configured in `TRADINGVIEW_WEBHOOK_SECRET`,
either as:
- an `X-TradingView-Secret` header (preferred), or
- a `"secret"` field inside the JSON body (used by the bundled Pine Script,
  since TradingView's free/basic alert webhooks don't support custom headers
  on all plans).

A request with a missing/incorrect secret, or sent while
`TRADINGVIEW_ENABLED=false`, is rejected with `success: false` — never a raw
500 or an unhandled exception.

### Request JSON

| Field | Type | Required | Notes |
|---|---|---|---|
| `source` | string | yes | must be `"tradingview"` |
| `symbol` | string | yes | e.g. `"RELIANCE"` |
| `exchange` | string | no | e.g. `"NSE"` |
| `strategy` | string | yes | one of `Strategy One`, `GFS`, `Advanced GFS`, `PRD`, `NRD`, `Value Buy` |
| `timeframe` | string | yes | the chart timeframe the alert fired on, e.g. `"1D"` |
| `signal_date` | ISO datetime | yes | bar time the alert fired on |
| `daily_rsi` / `weekly_rsi` / `monthly_rsi` | number | strategy-dependent | required for Strategy One/GFS/Advanced GFS; `monthly_rsi` required for Value Buy |
| `signal` | bool | yes | must be `true` — the alert should only ever fire on a confirmed condition |
| `divergence_type` | `"PRD"` \| `"NRD"` | PRD/NRD only | must match `strategy` |
| `divergence_timeframe` | `"Daily"` \| `"Weekly"` \| `"Monthly"` | PRD/NRD only | the timeframe that confirmed |
| `weekly_candle` | `"GREEN"` | Value Buy only | must be `GREEN` |
| `daily_trigger` | `"KEY_REVERSAL"` \| `"TRENDLINE_BREAKOUT"` | Value Buy only | |
| `secret` | string | yes (if not using the header) | must equal `TRADINGVIEW_WEBHOOK_SECRET` |

### Valid example (GFS)

```json
{
  "source": "tradingview",
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "strategy": "GFS",
  "timeframe": "1D",
  "signal_date": "2026-09-12T15:30:00Z",
  "daily_rsi": 42.31,
  "weekly_rsi": 67.82,
  "monthly_rsi": 71.15,
  "signal": true,
  "secret": "your-webhook-secret"
}
```

Response:

```json
{ "success": true, "message": "TradingView signal received", "signal_id": "12", "strategy": "GFS", "symbol": "RELIANCE" }
```

### Invalid example (missing strategy)

```json
{ "source": "tradingview", "symbol": "RELIANCE", "signal": true }
```

Response:

```json
{ "success": false, "message": "Invalid TradingView webhook payload: Field required" }
```

## Idempotency

Each alert is deduped on a deterministic key: `symbol + strategy + timeframe
+ signal_date + trigger` (SHA-256 hashed). A re-delivered alert (TradingView
retries webhooks that don't return 2xx; a user can also fire the same alert
twice) returns the same `signal_id` and never creates a duplicate row or
deletes anything.

## Other endpoints

- `GET /api/tradingview/status` → `{ enabled, configured, signal_count, latest_signal_at }`
- `GET /api/tradingview/signals?limit=200` → list of stored signals, newest first

## TradingView Setup (manual, one-time)

1. Open a NIFTY 200 constituent's chart on TradingView.
2. Add the indicator: Pine Editor → paste `pinescript/nifty200_scanner_signals.pine` → Add to Chart.
3. In the indicator's settings, fill in **Webhook Secret** with the same value as `TRADINGVIEW_WEBHOOK_SECRET`.
4. Click **Create Alert** (Alt+A), condition = the indicator, "Any alert() function call".
5. Under **Notifications**, enable **Webhook URL** and set it to:
   `https://<your-backend-host>/api/tradingview/webhook`
   (a publicly reachable URL — TradingView cannot reach `127.0.0.1`; use a
   tunnel such as ngrok/Cloudflare Tunnel for local development).
6. Leave the alert **Message** field as `{{strategy.order.alert_message}}` (TradingView's default, which forwards exactly what the script's `alert()` call built) — do not overwrite it, since the script already emits the full JSON body per strategy.
7. Save the alert.
8. Repeat per symbol/strategy you want to monitor (TradingView alerts are per chart+condition).

## Configuration

```
TRADINGVIEW_ENABLED=false
TRADINGVIEW_WEBHOOK_SECRET=
```

- `TRADINGVIEW_ENABLED=false` (default): the webhook route exists but always
  rejects requests; nothing else in the app changes.
- `TRADINGVIEW_ENABLED=true` + a non-empty `TRADINGVIEW_WEBHOOK_SECRET`:
  the webhook accepts correctly-authenticated, valid signals.

## Verification status

The webhook, validation, idempotency, and disabled-mode behavior are covered
by `tests/test_tradingview_webhook.py` (18 tests) using FastAPI's `TestClient`
against a real in-memory database — this is genuine integration testing of
the backend path.

**The Pine Script → TradingView Alert → live webhook round trip has NOT been
executed against a real TradingView account from this environment** (no
browser/TradingView access here). Before relying on it in production:
1. Paste the script into TradingView's Pine Editor and confirm it compiles
   without errors.
2. Create one alert per the steps above pointed at a publicly reachable
   tunnel to a local backend, and confirm a real alert delivery appears in
   `GET /api/tradingview/signals`.
3. Only then should TradingView's connection status be considered verified
   end-to-end.

# NIFTY 200 Scanner & Intelligence Tool

A standalone scanner that finds the strongest NIFTY 200 setups by combining
NIFTY-relative sector strength, multi-timeframe RSI, real swing-based RSI
divergence detection, Fibonacci structure, trend, and volume/momentum — all
computed from real market data pulled through the **Tapetide MCP** server.

## 1. Project structure

```
backend/
  api/            FastAPI routers (scan, history, config)
  config/         strategy_config.py (all thresholds/weights), sector_mapping.py
  core/           settings, SQLAlchemy database, cache abstraction
  models/         SQLAlchemy models (ScanRun, ScanResultRow)
  schemas/        Pydantic response schemas
  providers/      Tapetide MCP client (own OAuth) + provider normalization
  indicators/     RSI, EMA/SMA, MACD, ADX, volume, timeframe resampling
  divergence/     swing-point detection + regular/hidden divergence engine
  fibonacci/      Fibonacci retracement engine
  sector_analysis/ sector return/RSI vs NIFTY benchmark
  screeners/      per-stock indicator aggregation (stock_analysis.py)
  ranking/        weighted scoring + classification
  strategies/     trade setup (entry/SL/targets) calculator
  services/       scan orchestration, DB persistence, config store, provider factory
  main.py         FastAPI app

frontend/         React + Vite + TypeScript dashboard
tests/            pytest unit tests (indicators, fibonacci, divergence, scoring, resample)
docker/           Dockerfile.backend, Dockerfile.frontend, docker-compose.yml
```

## 2. Technologies used

- **Backend**: Python, FastAPI, SQLAlchemy, Pandas/NumPy for all indicator math
- **Data source**: Tapetide MCP (`https://mcp.tapetide.com/mcp`), via the official
  `mcp` Python SDK with its own OAuth client (independent of any Claude session)
- **Database**: SQLite by default (`DATABASE_URL` in `.env`), swappable to
  PostgreSQL with zero code changes (same SQLAlchemy models)
- **Cache**: disk-backed by default (`CACHE_URL=file://...`), swappable to Redis
- **Frontend**: React + Vite + TypeScript, plain CSS (no chart library wired
  yet — see Known limitations)
- **Containerization**: `docker/Dockerfile.backend`, `docker/Dockerfile.frontend`,
  `docker/docker-compose.yml` (Postgres + Redis + backend + frontend). These were
  written but **not run** in this environment — Docker is not installed on this
  machine (confirmed at the start of the build).

## 3. Tapetide MCP connection status

Connected and authorized. Two *separate* OAuth-authorized clients exist:
1. This Claude Code session's own MCP connection (used during development to
   inspect tools and validate data).
2. The **backend's own, independent MCP client**
   (`backend/providers/tapetide_client.py`) — this is what a running/deployed
   instance of the app actually uses. It performs its own dynamic client
   registration + OAuth authorization-code+PKCE flow (opens a browser once,
   caches the token to `.tapetide_token.json`, refreshes silently thereafter).
   This was authorized and verified working during this build (see log excerpt
   in Test results below).

## 4. Available Tapetide tools (discovered via `read_me`, ~40 tools)

Full categorized list is in the MCP server's own `read_me` tool output. The
ones this app actually uses:

| Tool | Used for |
|---|---|
| `market_heatmap` | NIFTY 200 universe + per-stock sector tag (see limitation below) |
| `get_index_history` | NIFTY 50 benchmark OHLC + sectoral index OHLC |
| `get_index_performance` | official NSE sectoral index return ranking (cross-check) |
| `get_price_history` | per-stock daily OHLCV (RSI/EMA/MACD/ADX/Fibonacci/divergence source) |
| `get_index_membership_asof` | (available, not currently used — see limitations) |
| `screen_stocks_technical`, `get_batch_quotes`, `search_stocks`, `get_company_profile` | available for future first-pass batch screening (see limitations) |

Not used: options tools, FII/DII tools, fundamentals/screener ratios,
portfolio/watchlist tools — out of scope for this technical scanner (options
support is left for future extension per the provider interface design).

## 5. Data fields available

- **OHLCV**: date, open, high, low, close, volume, delivery% (per stock);
  OHLC + PE/PB/dividend yield (per index) — all real, exchange-sourced.
- **Universe**: symbol, sector (Tapetide's own taxonomy), exchange, ISIN,
  market cap.
- Everything else (RSI, EMA, MACD, ADX, Fibonacci, divergence, sector
  relative strength, scores) is **computed locally** from that OHLCV — Tapetide
  does not provide these directly, matching the "verify before assuming"
  instruction in the spec.

## 6. Scanner methodology

`backend/services/scan_service.py::run_full_scan`:
1. Fetch NIFTY 200 universe (real, current — see limitation #1 below).
2. Fetch NIFTY 50 benchmark OHLC, compute daily/weekly/monthly return + RSI.
3. For each sector present, resolve its NSE sectoral index (`sector_mapping.py`),
   fetch that index's OHLC, compute the same daily/weekly/monthly return + RSI,
   and compare to the NIFTY benchmark.
4. A sector **qualifies** only if it outperforms NIFTY on **all three**
   timeframes **and** clears the configured RSI floor on all three (never a
   single strong day).
5. Only stocks belonging to qualifying sectors are analyzed in depth (this is
   the "screener, not 200 individual calls" requirement — see limitation #2 on
   why the *technical screener* itself isn't used as a further pre-filter yet).
6. Per stock: daily OHLCV → resampled to weekly/monthly (dropping any
   in-progress trailing period) → RSI on all three timeframes, real
   swing-based divergence detection on all three, Fibonacci retracement,
   EMA20/50/200, MACD, ADX, volume ratio, 52-week high distance.
7. A stock **qualifies** only if weekly RSI is in the configured band, monthly
   RSI clears its floor, and it isn't disqualified by bearish divergence.
8. Qualifying stocks are scored 0–100 (weighted, fully configurable — see
   `backend/config/strategy_config.py`), classified, and ranked → Top 10 → Top
   3 → Best Stock.

## 7. RSI methodology

Classic Wilder's RSI (`backend/indicators/rsi.py`): first average gain/loss is
a simple mean of the first `period` deltas, then Wilder's recursive smoothing
(`avg = (prev_avg * (period-1) + current) / period`) — verified against a
published reference value in `tests/test_indicators.py`.

Weekly/monthly series are built by resampling daily OHLCV
(`backend/indicators/resample.py`), **explicitly dropping the trailing
in-progress period** — this was a real bug caught during development (weekly
RSI was silently collapsing to the daily value) and is now covered by
`tests/test_resample.py`.

## 8. Divergence methodology

Real fractal/pivot swing-point detection (`backend/divergence/swing.py`) — a
bar is a swing high/low only if it's the strict extreme within a configurable
`SWING_LOOKBACK` window on both sides — not a bare current-vs-previous RSI
comparison. `backend/divergence/detector.py` then compares consecutive swing
highs/lows on both price and RSI, requiring both `MIN_PRICE_DIFFERENCE` and
`MIN_RSI_DIFFERENCE` to be cleared and `CONFIRMATION_CANDLES` to have printed
after the second swing point before counting it as a signal. Detects regular
bearish/bullish and hidden bearish/bullish divergence. A `strict_mode` config
flag controls whether any bearish divergence (daily/weekly/monthly) disqualifies
a stock, or only weekly (the default). Verified in `tests/test_divergence.py`
against a hand-constructed price series with a genuine higher-high/lower-RSI
pattern (not synthetic RSI values).

## 9. Fibonacci methodology

`backend/fibonacci/engine.py` selects the most relevant recent swing
(highest high / lowest low within a configurable lookback window), computes
23.6/38.2/50/61.8/78.6% levels, and reports the nearest level plus whether
price sits in a "preferred zone" (38.2/50/61.8 by default, configurable).
A separate `has_bullish_confirmation` check (recent higher closes) is required
before treating a zone as bullish-confirmed — the engine does **not** assume
every retracement is bullish.

## 10. Sector methodology

See section 6 above. Sector-to-index mapping (`backend/config/sector_mapping.py`)
was built by cross-referencing Tapetide's actual per-stock sector labels
against the real ~35-index NSE sectoral catalog (via `get_index_performance`),
not guessed. Sectors with no reasonable NSE sectoral index (e.g. "Aerospace &
Defense", "Food Products", "Transport") are explicitly mapped to `None` and
reported as `DATA UNAVAILABLE` rather than approximated.

## 11. Scoring methodology

`backend/ranking/scorer.py` — weighted average of 8 components (each 0-100),
normalized against the configured weight total so custom weights need not sum
to exactly 100:

| Component | Default weight |
|---|---|
| Sector outperformance | 25 |
| Sector RSI | 15 |
| Stock RSI | 20 |
| Divergence | 15 |
| Fibonacci | 10 |
| Trend | 5 |
| Volume | 5 |
| MACD/ADX | 5 |

Classification bands (STRONG/GOOD/MODERATE/WEAK) and bias (BULLISH/NEUTRAL/HIGH
RISK) are both configurable via `/api/config`. Every score carries a
human-readable `explanation` list built from the actual computed values.

## 12. API endpoints

- `POST /api/scan/run?scan_type=manual|daily|weekly|monthly` — runs a full scan, persists it, returns full results
- `GET /api/history` / `GET /api/history/{id}` / `GET /api/history/{id}/results` — scan history
- `GET /api/config` / `PUT /api/config` / `POST /api/config/reset` — strategy configuration
- `GET /api/health`

## 13. Database schema

`ScanRun` (one row per scan: timing, universe coverage, counts, errors) and
`ScanResultRow` (one row per Top-10 stock per scan, with the full serialized
result in a JSON `detail` column). See `backend/models/scan.py`.

## 14. Test results

28/28 tests passing (`pytest tests/ -q`): RSI (incl. a published Wilder
reference value), EMA/SMA, MACD, ADX, volume, Fibonacci (uptrend/downtrend
retracement, nearest-level selection, degenerate-input handling), real
swing-based divergence detection (positive and negative cases), resample
period-completeness (the bug described in section 7), sector-mapping honesty
(unmapped sectors return `None`, never a guess), and the scoring/classification
engine (boundaries, custom weights, high-risk bias override).

A full end-to-end scan was also run against **live** Tapetide data during
development (see the qualifying-sectors/scores output captured mid-build) —
it correctly identified Automobiles and Financial Services as qualifying
sectors with real return/RSI numbers, before the free-tier daily call quota
was hit (see limitations).

## 15. Known limitations

1. **NIFTY 200 universe coverage is partial (~169–173/200), not 100%.**
   `market_heatmap` truncates its own response at ~25,000 characters
   server-side with no pagination parameter — confirmed empirically (even a
   single `nifty-50` call truncates to ~33 of 50 rows). The universe service
   works around this by combining `nifty-200` with `nifty-50`/`nifty-next-50`
   and every sectoral index heatmap small enough to return in full, de-duplicating
   by symbol — but this is a best-effort reconstruction, not an
   exchange-verified list. `GET` results always report `universe_returned`,
   `universe_requested`, `complete`, and a `note` explaining this honestly; the
   UI surfaces it too. This is the single most consequential unresolved
   limitation.

2. **Tapetide's free tier caps requests at 50 MCP calls/day.** A full scan of
   even a couple of qualifying sectors' worth of stocks can exceed this. The
   provider layer caches every Tapetide response to disk
   (`backend/core/cache.py`, `.cache/tapetide_cache.pkl`) with data-appropriate
   TTLs so repeat scans within a day don't re-spend quota, but a *first* full
   scan on a given day can still hit the limit partway through — the pipeline
   handles this gracefully (failed symbols are logged and skipped per spec
   section 28, not fatal), but coverage of the Top 10 will be incomplete until
   quota resets or the plan is upgraded.

3. **The `screen_stocks_technical` batch screener is not yet used as a
   pre-filter.** Its `RSI` field is a live/daily reading with unclear
   timeframe semantics for our weekly/monthly-band requirement, and given the
   call-quota constraint above, wiring it in without being certain of its
   exact semantics risked misrepresenting a filter rather than genuinely
   reducing calls. Instead, the sector-qualification step already narrows the
   universe from ~200 to a handful of sectors before any per-stock call is
   made, which satisfies the spirit of "don't call once per stock for the
   whole universe" even without this additional layer.
4. **No live options data or economic/earnings calendar** — Tapetide doesn't
   provide these (confirmed via `read_me`), and they're out of scope for this
   technical scanner. The provider interface (`backend/providers/base.py`) is
   deliberately vendor-agnostic so an options provider can be added later
   without touching the scanner/scoring logic.
5. **Frontend has no interactive candlestick chart yet** — the Stock Details
   page with candlestick + Fibonacci overlay + separate RSI panels described in
   the spec (section 20) was not built in this pass; the current frontend
   covers Dashboard, Sector Scanner, NIFTY 200 Scanner, Scan History, and
   Settings, all wired to real API data.
6. **Docker was written but not run** — Docker isn't installed on this
   machine; the app was built and verified via a local Python venv + SQLite
   instead, per your instruction.
7. **Celery/background scheduling is not wired up** — the scan endpoint takes
   a `scan_type` (manual/daily/weekly/monthly) and persists results, but an
   actual Celery beat schedule to trigger daily/weekly/monthly scans
   automatically was not implemented in this pass.

## 16. How to start the application

Backend (from the project root):
```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env
uvicorn backend.main:app --reload
```
On first run, a browser window opens once for the backend to authorize its own
Tapetide MCP connection — sign in, then it's cached to `.tapetide_token.json`.

Frontend:
```
cd frontend
npm install
npm run dev
```
Visit `http://localhost:5173`.

## 17. How to run a scan

Click **Run Scan** on the Dashboard (calls `POST /api/scan/run`), or directly:
```
curl -X POST "http://127.0.0.1:8000/api/scan/run?scan_type=manual"
```

## 18. How to change strategy parameters

Via the **Settings** page in the UI, or directly:
```
GET  /api/config        # current configuration
PUT  /api/config        # replace with a new StrategyConfig JSON body
POST /api/config/reset  # back to defaults
```
All thresholds and weights live in `backend/config/strategy_config.py` as the
defaults; runtime overrides persist to `strategy_config_overrides.json`.

---
*This tool is for market research and technical screening. It is not
guaranteed investment advice.*

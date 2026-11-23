import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { SearchIcon } from "../components/icons";
import { PageHero, RangeMotif } from "../components/PageHero";
import { StockLogo } from "../components/StockLogo";
import {
  downloadRangeXlsx,
  fetchRangeTable,
  searchRangeInstruments,
  type RangeCell,
  type RangeSearchHit,
  type RangeTable,
} from "../services/rangeAnalysisApi";

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v.toFixed(2)}%`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function fmtMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

/** Search any NSE stock or index: suggestions appear after the first letters, like Top-Bottom's search. */
function InstrumentSearch({ value, onPick }: { value: string; onPick: (symbol: string) => void }) {
  const [query, setQuery] = useState(value);
  const [hits, setHits] = useState<RangeSearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => setQuery(value), [value]);

  useEffect(() => {
    const q = query.trim();
    if (!q || q.toUpperCase() === value) {
      setHits([]);
      return;
    }
    const handle = setTimeout(() => {
      setLoading(true);
      searchRangeInstruments(q)
        .then((r) => {
          setHits(r);
          setOpen(true);
        })
        .catch(() => setHits([]))
        .finally(() => setLoading(false));
    }, 180);
    return () => clearTimeout(handle);
  }, [query, value]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function pick(symbol: string) {
    setQuery(symbol);
    setOpen(false);
    setHits([]);
    onPick(symbol);
  }

  return (
    <div ref={boxRef} className="tb-field tb-search-field" style={{ position: "relative" }}>
      <label>
        Stock or index
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value.toUpperCase())}
          onFocus={() => hits.length > 0 && setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && query.trim()) pick(hits[0]?.symbol ?? query.trim().toUpperCase());
          }}
          placeholder="Type a few letters, e.g. CGP, RELI, NIFTY"
          autoComplete="off"
        />
      </label>
      <span className="tb-search-icon" aria-hidden="true">
        <SearchIcon width={15} height={15} />
      </span>
      {open && (loading || hits.length > 0) && (
        <div className="tb-search-dropdown">
          {loading && hits.length === 0 && <div className="tb-search-empty">Searching…</div>}
          {hits.map((h) => (
            <button key={h.symbol} type="button" className="tb-search-result" onClick={() => pick(h.symbol)}>
              <div className="tb-search-result-title logo-line"><span className="wk-logo"><StockLogo symbol={h.symbol} /></span>{h.symbol}</div>
              <div className="tb-search-result-meta">
                {h.name ? `${h.name} · ` : ""}
                {h.kind === "INDEX" ? "NSE index" : "NSE stock"}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Cell({ cell }: { cell: RangeCell | null }) {
  if (!cell) return <td className="rm-cell rm-empty" />;
  const cls = ["rm-cell", cell.in_progress ? "rm-progress" : `rm-${cell.level}`, cell.boxed ? "rm-boxed" : ""].join(" ");
  const title = `${cell.direction === "up" ? "Up month: (High − Low) / Low" : "Down month: (High − Low) / High"}${cell.in_progress ? " · month in progress, not in the averages" : ""}`;
  return (
    <td className={cls} title={title}>
      {cell.pct.toFixed(2)}%
    </td>
  );
}

function RangeSheet({ table }: { table: RangeTable }) {
  const best = new Set(table.jan_mar.best);
  return (
    <div className="table-wrap rm-wrap">
      <table className="range-table">
        <thead>
          <tr>
            <th className="rm-year">YEAR / MONTH</th>
            {MONTHS.map((m) => (
              <th key={m} className={best.has(m) ? "rm-best" : undefined}>
                {m}
              </th>
            ))}
            <th className="rm-avg">AVG MONTHLY RANGE</th>
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r) => (
            <tr key={r.year}>
              <td className="rm-year">{r.year}</td>
              {r.months.map((c, i) => (
                <Cell key={i} cell={c} />
              ))}
              <td className="rm-avg">{pct(r.avg)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td className="rm-year">Average</td>
            {table.month_stats.map((s) => (
              <td key={s.month}>{pct(s.avg)}</td>
            ))}
            <td className="rm-avg">{pct(table.overall.avg)}</td>
          </tr>
          <tr>
            <td className="rm-year">Median</td>
            {table.month_stats.map((s) => (
              <td key={s.month} className={s.month === table.overall.most_active ? "rm-top" : undefined}>
                {pct(s.median)}
              </td>
            ))}
            <td className="rm-avg">{pct(table.overall.median)}</td>
          </tr>
          <tr>
            <td className="rm-year">20%+ months</td>
            {table.month_stats.map((s) => (
              <td key={s.month}>
                {s.ge20}/{s.years}
              </td>
            ))}
            <td className="rm-avg">
              {table.overall.ge20}/{table.overall.months}
            </td>
          </tr>
          <tr>
            <td className="rm-year">30%+ months</td>
            {table.month_stats.map((s) => (
              <td key={s.month}>
                {s.ge30}/{s.years}
              </td>
            ))}
            <td className="rm-avg">
              {table.overall.ge30}/{table.overall.months}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

/** What every colour in the sheet means (user request, 2026-11-21). */
function RangeLegend() {
  const items: [string, string, string][] = [
    ["rm-sw rm-sw-green", "Green", "the month moved 30% or more"],
    ["rm-sw rm-sw-orange", "Orange", "the month moved 20% to 30%"],
    ["rm-sw rm-sw-plain", "No colour", "below 20%"],
    ["rm-sw rm-sw-box", "Boxed", "a 30%+ month in January–March"],
    ["rm-sw rm-sw-best", "Green month header", "the best January–March month (most 30%+ years)"],
    ["rm-sw rm-sw-progress", "Grey italic", "month still in progress, not in any average"],
  ];
  return (
    <div className="rm-legend" aria-label="Colour legend">
      {items.map(([cls, name, text]) => (
        <span key={name} className="rm-legend-item">
          <span className={cls} aria-hidden="true">
            {cls.includes("progress") ? "12%" : ""}
          </span>
          <span className="rm-legend-text">
            <strong>{name}</strong> — {text}
          </span>
        </span>
      ))}
    </div>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="tb-summary-tile">
      <div className="tb-summary-label">{label}</div>
      <div className="tb-summary-value">{value}</div>
      {sub && <div className="tb-config-hint" style={{ margin: 0 }}>{sub}</div>}
    </div>
  );
}

const THIS_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: THIS_YEAR - 1990 + 1 }, (_, i) => String(THIS_YEAR - i)); // newest first

export function RangeAnalysisPage() {
  // The stock and period live in the URL, so a refresh or a shared link keeps them. Nothing runs on its own:
  // the sheet is built only when "Run Backtest" is pressed (2026-11-21, user request).
  const [params, setParams] = useSearchParams();
  const symbol = (params.get("symbol") ?? "").toUpperCase();
  const mode: "inception" | "years" = params.get("range") === "years" ? "years" : "inception";
  const fromYear = params.get("fy") ?? String(THIS_YEAR - 10);
  const toYear = params.get("ty") ?? String(THIS_YEAR);
  const [table, setTable] = useState<RangeTable | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setParam(updates: Record<string, string>) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(updates)) {
          if (v) next.set(k, v);
          else next.delete(k);
        }
        return next;
      },
      { replace: true },
    );
  }

  const invalidRange = mode === "years" && Number(fromYear) > Number(toYear);

  async function run() {
    if (!symbol || invalidRange) return;
    setError(null);
    setLoading(true);
    try {
      setTable(await fetchRangeTable(symbol, mode === "years" ? `${fromYear}-01` : "", mode === "years" ? `${toYear}-12` : ""));
    } catch (e) {
      setTable(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const ov = table?.overall;

  return (
    <div>
      <PageHero
        tone="range"
        eyebrow="History · monthly range"
        title="Range Analysis"
        subtitle="How far a stock moves inside each month, year after year — from the oldest daily data Angel One has."
        motif={<RangeMotif />}
      >
        <span className="hero-pill">Green 30%+ · orange 20–30%</span>
        <span className="hero-pill hero-pill-soft">Boxed = a 30%+ month in January–March</span>
      </PageHero>

      <div className="card">
        <div className="tb-config-grid">
          <InstrumentSearch
            value={symbol}
            onPick={(s) => {
              // choosing a stock only fills it in; the data is fetched when "Run Backtest" is pressed
              setParam({ symbol: s });
              setTable(null);
              setError(null);
            }}
          />
          <div className="tb-field">
            <span className="rm-field-label">Period</span>
            <div className="rm-seg" role="group" aria-label="Period">
              <button type="button" className={mode === "inception" ? "active" : ""} onClick={() => setParam({ range: "" })}>
                Since inception
              </button>
              <button
                type="button"
                className={mode === "years" ? "active" : ""}
                onClick={() => setParam({ range: "years", fy: fromYear, ty: toYear })}
              >
                Year to year
              </button>
            </div>
          </div>
          {mode === "years" && (
            <>
              <div className="tb-field">
                <label>
                  From year
                  <select value={fromYear} onChange={(e) => setParam({ fy: e.target.value })}>
                    {YEARS.map((y) => (
                      <option key={y} value={y}>
                        {y}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="tb-field">
                <label>
                  To year
                  <select value={toYear} onChange={(e) => setParam({ ty: e.target.value })}>
                    {YEARS.map((y) => (
                      <option key={y} value={y}>
                        {y}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </>
          )}
        </div>
        <div className="tb-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 12 }}>
          <button className="primary-button" onClick={() => void run()} disabled={!symbol || loading || invalidRange}>
            {loading ? "Running…" : "Run Backtest"}
          </button>
          <button
            className="secondary-button"
            disabled={!table || exporting}
            onClick={() => {
              if (!table) return;
              setExporting(true);
              downloadRangeXlsx(table)
                .catch((e) => setError(e instanceof Error ? e.message : "Export failed"))
                .finally(() => setExporting(false));
            }}
          >
            {exporting ? "Preparing…" : "Download Excel"}
          </button>
          {invalidRange && <span className="tb-config-hint">"From year" is after "To year".</span>}
          {!symbol && <span className="tb-config-hint">Search a stock or index, then press Run Backtest.</span>}
          {symbol && !table && !loading && !invalidRange && (
            <span className="tb-config-hint">
              {symbol} · {mode === "years" ? `${fromYear} to ${toYear}` : "since inception"} — press Run Backtest to build the sheet.
            </span>
          )}
        </div>
      </div>

      {loading && !table && (
        <div className="card state-block">
          <div className="state-title">Fetching every daily candle for {symbol}…</div>
          <div className="state-subtitle">The first time takes a few seconds (30+ years of history); after that it is quick.</div>
        </div>
      )}

      {error && !loading && (
        <div className="error-banner">
          <div>
            <strong>Could not build the sheet.</strong> {error}
          </div>
        </div>
      )}

      {table && ov && (
        <>
          <div className="card">
            <h2 style={{ marginTop: 0 }}>
              <span className="logo-line"><span className="wk-logo"><StockLogo symbol={table.symbol} /></span>{table.symbol} — % Range Move</span>{table.name ? <span className="muted"> · {table.name}</span> : null}
            </h2>
            <div className="tb-summary-grid" style={{ marginTop: 12 }}>
              <Tile label="Data available" value={fmtDate(table.data_from).replace(/^\d+ /, "")} sub={`to ${fmtDate(table.data_to)} · ${table.kind === "INDEX" ? "index" : "spot"}`} />
              <Tile
                label="Shown"
                value={`${table.filter_from.slice(0, 4)} – ${table.filter_to.slice(0, 4)}`}
                sub={`${fmtMonth(table.filter_from)} to ${fmtMonth(table.filter_to)} · ${ov.months} complete months`}
              />
              <Tile label="Avg monthly range" value={pct(ov.avg)} sub={`median ${pct(ov.median)}`} />
              <Tile label="20%+ months" value={`${ov.ge20}`} sub={`of ${ov.months} (${ov.months ? Math.round((ov.ge20 / ov.months) * 100) : 0}%)`} />
              <Tile label="30%+ months" value={`${ov.ge30}`} sub={`of ${ov.months} (${ov.months ? Math.round((ov.ge30 / ov.months) * 100) : 0}%)`} />
              <Tile label="Most active month" value={ov.most_active ?? "—"} sub="highest median" />
              <Tile label="Quietest month" value={ov.quietest ?? "—"} sub="lowest median" />
              <Tile
                label="Jan–Mar best"
                value={table.jan_mar.best.join(" / ") || "—"}
                sub={`30%+: ${Object.entries(table.jan_mar.ge30)
                  .map(([m, n]) => `${m.charAt(0)}${m.slice(1).toLowerCase()} ${n}`)
                  .join(" · ")}`}
              />
            </div>
          </div>

          <div className="card">
            <RangeLegend />
            <RangeSheet table={table} />
            <p className="muted small" style={{ marginTop: 10, marginBottom: 0 }}>
              Up month (closed at or above the previous month&apos;s close): (High − Low) / Low. Down month: (High − Low) /
              High. Grey italic = month in progress, not in any average. Averages and counts use complete months only.
              Historical data; not investment advice.
            </p>
          </div>
        </>
      )}
    </div>
  );
}

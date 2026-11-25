/**
 * Ratio analysis (2026-11-25): A / B ratio from end-of-day closes, its zones, where it stands now, what followed each
 * zone in the past and a simple switch backtest.
 *
 * No hindsight: the zones used for the past (backtest, zone events) are the 15th / 85th percentile of the ratio's history
 * UP TO that month only (first 36 months: no zone). Today's zones are the same percentiles over all history so far.
 */
export type Pt = [number, number]; // [unix seconds, value]

export const LOW_PCT = 0.15;
export const HIGH_PCT = 0.85;
export const WARMUP_MONTHS = 36;

/** A / B on the dates both have. */
export function ratioOf(a: Pt[], b: Pt[]): Pt[] {
  const bm = new Map(b.map(([t, v]) => [t, v]));
  const out: Pt[] = [];
  for (const [t, v] of a) {
    const w = bm.get(t);
    if (w && w > 0 && v > 0) out.push([t, v / w]);
  }
  return out;
}

/** The last value of each calendar month. */
export function monthly(pts: Pt[]): Pt[] {
  const out: Pt[] = [];
  let key = "";
  for (const p of pts) {
    const d = new Date(p[0] * 1000);
    const k = `${d.getUTCFullYear()}-${d.getUTCMonth()}`;
    if (k === key) out[out.length - 1] = p;
    else { out.push(p); key = k; }
  }
  return out;
}

/** Monthly rows from ratio_closes.json: [year*12 + month-1, c, c, ...]. */
export function fromMonthPacked(row: number[]): Pt[] {
  const [first, ...closes] = row;
  return closes.map((c, i) => {
    const m = first + i;
    return [Date.UTC(Math.floor(m / 12), m % 12, 1) / 1000, c] as Pt;
  });
}

export function quantile(xs: number[], q: number): number {
  if (!xs.length) return NaN;
  const s = [...xs].sort((x, y) => x - y);
  const pos = (s.length - 1) * q;
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  return s[lo] + (s[hi] - s[lo]) * (pos - lo);
}

const mean = (xs: number[]) => xs.reduce((s, x) => s + x, 0) / xs.length;
const std = (xs: number[]) => {
  const m = mean(xs);
  return Math.sqrt(xs.reduce((s, x) => s + (x - m) ** 2, 0) / Math.max(1, xs.length - 1));
};

export type Zone = "high" | "low" | "mid";
export type Perf = { cagr: number; maxDD: number; growth: number };
export type ZoneStats = { times: number; aAvg: number; bAvg: number; bBeatA: number } | null;
export type RatioAnalysis = {
  now: number; asOf: number; years: number;
  low: number; high: number; median: number; zone: Zone;
  pctRank: number;      // 0-100: share of history at or below today's ratio
  z3y: number | null;   // (now - 3y mean) / 3y std
  trendUp: boolean | null; ma: number | null; // ratio above its 40-week (10-month) average
  chg: { m1: number | null; m3: number | null; m12: number | null };
  afterHigh: ZoneStats; afterLow: ZoneStats; // next 12 months of A and B after the ratio entered a zone
  backtest: { switchPerf: Perf; a: Perf; b: Perf; half: Perf; switches: number; holding: "A" | "B"; from: number } | null;
};

function perf(rets: number[]): Perf {
  let eq = 1, peak = 1, dd = 0;
  for (const r of rets) {
    eq *= 1 + r; peak = Math.max(peak, eq); dd = Math.min(dd, eq / peak - 1);
  }
  const yrs = rets.length / 12;
  return { cagr: yrs > 0 ? eq ** (1 / yrs) - 1 : 0, maxDD: dd, growth: eq };
}

/**
 * `ratio` - the series to show (weekly or monthly); `a`, `b` - the legs on the same dates.
 * `perYear` - points per year of `ratio` (52 weekly, 12 monthly).
 */
export function analyse(ratio: Pt[], a: Pt[], b: Pt[], perYear: number): RatioAnalysis | null {
  if (ratio.length < 24) return null;
  const vals = ratio.map((p) => p[1]);
  const now = vals[vals.length - 1];
  const low = quantile(vals, LOW_PCT), high = quantile(vals, HIGH_PCT), median = quantile(vals, 0.5);
  const back = (n: number) => (vals.length > n ? now / vals[vals.length - 1 - n] - 1 : null);
  const per = perYear / 12;
  const last3 = vals.slice(-Math.round(3 * perYear));
  const maLen = perYear === 52 ? 40 : 10;
  const ma = vals.length >= maLen ? mean(vals.slice(-maLen)) : null;

  // monthly view for the backtest and zone events
  const rm = monthly(ratio), am = monthly(a), bm = monthly(b);
  const amap = new Map(am.map((p) => [p[0], p[1]])), bmap = new Map(bm.map((p) => [p[0], p[1]]));
  const mt = rm.map((p) => p[0]).filter((t) => amap.has(t) && bmap.has(t));
  const mv = mt.map((t) => (amap.get(t) as number) / (bmap.get(t) as number));
  const av = mt.map((t) => amap.get(t) as number), bv = mt.map((t) => bmap.get(t) as number);

  let backtest: RatioAnalysis["backtest"] = null;
  const hiEvents: [number, number][] = [], loEvents: [number, number][] = [];
  if (mv.length > WARMUP_MONTHS + 12) {
    let hold: "A" | "B" = "B", switches = 0, prevZone: Zone = "mid";
    const sw: number[] = [], ra: number[] = [], rb: number[] = [], rh: number[] = [];
    for (let i = WARMUP_MONTHS; i < mv.length; i++) {
      const hist = mv.slice(0, i + 1);
      const lo = quantile(hist, LOW_PCT), hi = quantile(hist, HIGH_PCT);
      const zone: Zone = mv[i] >= hi ? "high" : mv[i] <= lo ? "low" : "mid";
      // high ratio = A expensive against B -> hold B; low ratio -> hold A
      const want: "A" | "B" = zone === "high" ? "B" : zone === "low" ? "A" : hold;
      if (i > WARMUP_MONTHS && want !== hold) switches++;
      hold = want;
      if (zone !== prevZone && i + 12 < mv.length) {
        const ev: [number, number] = [av[i + 12] / av[i] - 1, bv[i + 12] / bv[i] - 1];
        if (zone === "high") hiEvents.push(ev);
        if (zone === "low") loEvents.push(ev);
      }
      prevZone = zone;
      if (i + 1 < mv.length) {
        const ga = av[i + 1] / av[i] - 1, gb = bv[i + 1] / bv[i] - 1;
        ra.push(ga); rb.push(gb); rh.push((ga + gb) / 2); sw.push(hold === "A" ? ga : gb);
      }
    }
    backtest = { switchPerf: perf(sw), a: perf(ra), b: perf(rb), half: perf(rh), switches, holding: hold, from: mt[WARMUP_MONTHS] };
  }
  const zs = (ev: [number, number][]): ZoneStats =>
    ev.length ? { times: ev.length, aAvg: mean(ev.map((e) => e[0])), bAvg: mean(ev.map((e) => e[1])), bBeatA: ev.filter((e) => e[1] > e[0]).length / ev.length } : null;

  return {
    now, asOf: ratio[ratio.length - 1][0], years: (ratio[ratio.length - 1][0] - ratio[0][0]) / (365.25 * 86400),
    low, high, median, zone: now >= high ? "high" : now <= low ? "low" : "mid",
    pctRank: (100 * vals.filter((v) => v <= now).length) / vals.length,
    z3y: last3.length >= perYear * 2 ? (now - mean(last3)) / (std(last3) || 1) : null,
    trendUp: ma == null ? null : now > ma, ma,
    chg: { m1: back(Math.round(per)), m3: back(Math.round(3 * per)), m12: back(Math.round(12 * per)) },
    afterHigh: zs(hiEvents), afterLow: zs(loEvents), backtest,
  };
}

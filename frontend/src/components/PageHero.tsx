import type { ReactNode } from "react";

/**
 * A page's hero header (2026-11-23): title, subtitle and a decorative motif on a softly tinted card. `tone` picks the
 * page's own colour (astro / gann / angle) - everything else is the app's normal card, type and theme tokens.
 */
export function PageHero({ tone, eyebrow, title, subtitle, motif, children }: {
  tone: "astro" | "gann" | "angle" | "outlook" | "anniv";
  eyebrow: string;
  title: string;
  subtitle: ReactNode;
  motif: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className={`hero hero-${tone}`}>
      <div className="hero-text">
        <span className="hero-eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p className="hero-sub">{subtitle}</p>
        {children && <div className="hero-extra">{children}</div>}
      </div>
      <div className="hero-motif" aria-hidden="true">{motif}</div>
    </header>
  );
}

/** North Indian (Uttar Bharatiya) kundali: the diamond chart of 12 bhavas, rashi numbers and the nine grahas in
 *  Devanagari - the classic Vedic chart, drawn as a quiet motif (an illustrative placement, not a live chart). */
export function VedicKundali() {
  const S = 100; // half size
  const houses: { x: number; y: number; rashi: number; graha?: string }[] = [
    { x: 0, y: -50, rashi: 1, graha: "सू" }, { x: -50, y: -78, rashi: 2 }, { x: -78, y: -50, rashi: 3, graha: "बु" },
    { x: -50, y: 0, rashi: 4, graha: "चं" }, { x: -78, y: 50, rashi: 5 }, { x: -50, y: 78, rashi: 6, graha: "रा" },
    { x: 0, y: 50, rashi: 7, graha: "शु" }, { x: 50, y: 78, rashi: 8 }, { x: 78, y: 50, rashi: 9, graha: "गु" },
    { x: 50, y: 0, rashi: 10, graha: "श" }, { x: 78, y: -50, rashi: 11, graha: "मं" }, { x: 50, y: -78, rashi: 12, graha: "के" },
  ];
  return (
    <svg viewBox="-112 -112 224 224" className="motif-svg">
      <rect x={-S} y={-S} width={2 * S} height={2 * S} rx={6} className="m-frame" />
      <line x1={-S} y1={-S} x2={S} y2={S} className="m-line" />
      <line x1={S} y1={-S} x2={-S} y2={S} className="m-line" />
      <polygon points={`0,${-S} ${S},0 0,${S} ${-S},0`} className="m-line m-diamond" />
      {houses.map((h) => (
        <g key={h.rashi}>
          <text x={h.x} y={h.y - (h.graha ? 9 : 0)} className="m-rashi" textAnchor="middle" dominantBaseline="central">{h.rashi}</text>
          {h.graha && <text x={h.x} y={h.y + 9} className="m-graha" textAnchor="middle" dominantBaseline="central">{h.graha}</text>}
        </g>
      ))}
      <circle r={4} className="m-bindu" />
    </svg>
  );
}

/** Gann's Square of Nine: numbers spiralling out from the centre, the cardinal cross and diagonals highlighted. */
export function SquareOfNine() {
  const N = 7, cell = 26, half = ((N - 1) / 2) * cell;
  const grid: { x: number; y: number; n: number }[] = [];
  let x = 0, y = 0, n = 1, step = 1;
  grid.push({ x, y, n });
  const dirs = [[1, 0], [0, -1], [-1, 0], [0, 1]];
  let d = 0;
  while (n < N * N) {
    for (let rep = 0; rep < 2 && n < N * N; rep++) {
      for (let s = 0; s < step && n < N * N; s++) { x += dirs[d][0]; y += dirs[d][1]; n++; grid.push({ x, y, n }); }
      d = (d + 1) % 4;
    }
    step++;
  }
  return (
    <svg viewBox={`${-half - 20} ${-half - 20} ${2 * half + 40} ${2 * half + 40}`} className="motif-svg">
      <line x1={-half - 13} y1={0} x2={half + 13} y2={0} className="m-cross" />
      <line x1={0} y1={-half - 13} x2={0} y2={half + 13} className="m-cross" />
      <line x1={-half - 13} y1={-half - 13} x2={half + 13} y2={half + 13} className="m-diag" />
      <line x1={-half - 13} y1={half + 13} x2={half + 13} y2={-half - 13} className="m-diag" />
      {grid.map((c) => {
        const onAxis = c.x === 0 || c.y === 0 || Math.abs(c.x) === Math.abs(c.y);
        return (
          <g key={c.n}>
            <rect x={c.x * cell - cell / 2 + 1} y={c.y * cell - cell / 2 + 1} width={cell - 2} height={cell - 2} rx={4} className={onAxis ? "m-cell-on" : "m-cell"} />
            <text x={c.x * cell} y={c.y * cell} className={onAxis ? "m-num-on" : "m-num"} textAnchor="middle" dominantBaseline="central">{c.n}</text>
          </g>
        );
      })}
    </svg>
  );
}

/** Angle halving fan from a swing point: the full angle, its halves, flat, and the mirrored (dashed) side. */
export function AngleFanMotif() {
  const ox = -95, oy = 70, L = 200;
  const base = 38;
  const angles = [base, base / 2, base / 4, base / 8, 0, -base / 8, -base / 4, -base / 2];
  return (
    <svg viewBox="-110 -110 220 220" className="motif-svg">
      <polyline points="-105,95 -95,70 -70,40 -50,55 -30,10" className="m-price" />
      {angles.map((a, i) => {
        const rad = (a * Math.PI) / 180;
        return (
          <line key={i} x1={ox} y1={oy} x2={ox + Math.cos(rad) * L} y2={oy - Math.sin(rad) * L}
            className={a < 0 ? "m-ray m-ray-mirror" : a === 0 ? "m-ray m-ray-flat" : "m-ray"} style={{ opacity: 1 - i * 0.07 }} />
        );
      })}
      <path d={`M ${ox + 34} ${oy} A 34 34 0 0 0 ${ox + Math.cos((base * Math.PI) / 180) * 34} ${oy - Math.sin((base * Math.PI) / 180) * 34}`} className="m-arc" />
      <circle cx={ox} cy={oy} r={5} className="m-origin" />
    </svg>
  );
}

/** A bell curve with its 1-sigma and 2-sigma bands - the shape behind every range on the Outlook page. */
export function BellCurveMotif() {
  const pts: string[] = [];
  for (let x = -100; x <= 100; x += 4) {
    const z = x / 34;
    pts.push(`${x},${60 - Math.exp(-z * z / 2) * 120}`);
  }
  const band = (a: number, b: number) => {
    const p: string[] = [`${a},60`];
    for (let x = a; x <= b; x += 2) { const z = x / 34; p.push(`${x},${60 - Math.exp(-z * z / 2) * 120}`); }
    p.push(`${b},60`);
    return p.join(" ");
  };
  return (
    <svg viewBox="-110 -80 220 160" className="motif-svg">
      <polygon points={band(-68, 68)} className="m-band2" />
      <polygon points={band(-34, 34)} className="m-band1" />
      <polyline points={pts.join(" ")} className="m-curve" />
      <line x1={-108} y1={60} x2={108} y2={60} className="m-axis" />
      <line x1={0} y1={60} x2={0} y2={-64} className="m-mid" />
      <text x={0} y={74} className="m-lab" textAnchor="middle">today</text>
      <text x={-51} y={74} className="m-lab" textAnchor="middle">−1σ</text>
      <text x={51} y={74} className="m-lab" textAnchor="middle">+1σ</text>
    </svg>
  );
}

/** A ring of 12 months with a few marked dates - the same day coming round again each year. */
export function AnniversaryMotif() {
  const marks = [0, 3, 7, 10];
  return (
    <svg viewBox="-110 -110 220 220" className="motif-svg">
      <circle r={92} className="m-faint" />
      <circle r={70} className="m-line" />
      {Array.from({ length: 12 }, (_, i) => {
        const a = (i * 30 - 90) * (Math.PI / 180);
        const on = marks.includes(i);
        return (
          <g key={i}>
            <line x1={Math.cos(a) * 70} y1={Math.sin(a) * 70} x2={Math.cos(a) * 92} y2={Math.sin(a) * 92} className="m-faint" />
            <circle cx={Math.cos(a + 0.26) * 81} cy={Math.sin(a + 0.26) * 81} r={on ? 6 : 2.5} className={on ? "m-mark" : "m-dot"} />
          </g>
        );
      })}
      <path d="M -38 -6 L -16 -6 L -4 -30 L 10 24 L 22 -2 L 40 -2" className="m-pulse" />
      <text x={0} y={46} className="m-lab" textAnchor="middle">same date, every year</text>
    </svg>
  );
}

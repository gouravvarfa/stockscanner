import type { SectorRow } from "../../services/weeklySectorsApi";

/**
 * Sector rotation (2026-11-22): every sector by its 1-month (x) and 1-week (y) return minus the Nifty 50's, with the
 * faint line of its last 4 weeks. Top right = Leading, top left = Improving, bottom right = Weakening, bottom left =
 * Lagging. Clicking a sector opens it below.
 */

const W = 760;
const H = 430;
const PAD = { l: 46, r: 14, t: 14, b: 38 };

function step(span: number): number {
  for (const s of [0.5, 1, 2, 2.5, 5, 10, 20, 25, 50]) if (span / s <= 3) return s;
  return 100;
}

const verdictClass = (v: string | undefined) => `rot-${(v ?? "N/A").replace("/", "").toLowerCase()}`;

export function RotationMap({ sectors, onPick }: { sectors: SectorRow[]; onPick: (key: string) => void }) {
  const items = sectors
    .filter((s) => (s.trail?.length ?? 0) > 0)
    .map((s) => {
      const path = (s.trail ?? []).map((t) => [t.rel_1m, t.rel_1w] as [number, number]);
      // the 4-week line only for the STRONG sectors: 20 lines at once are unreadable
      return { s, path: s.verdict === "STRONG" ? path : path.slice(-1) };
    });
  if (items.length === 0) {
    return <p className="muted small">Run the report again to see the rotation map.</p>;
  }
  const xs = items.flatMap((i) => i.path.map((p) => Math.abs(p[0])));
  const ys = items.flatMap((i) => i.path.map((p) => Math.abs(p[1])));
  const xmax = Math.max(1, Math.max(...xs) * 1.15);
  const ymax = Math.max(1, Math.max(...ys) * 1.15);
  const pw = W - PAD.l - PAD.r;
  const ph = H - PAD.t - PAD.b;
  const sx = (v: number) => PAD.l + ((v + xmax) / (2 * xmax)) * pw;
  const sy = (v: number) => PAD.t + (1 - (v + ymax) / (2 * ymax)) * ph;
  const x0 = sx(0);
  const y0 = sy(0);
  const ticks = (max: number) => {
    const st = step(max);
    const out: number[] = [];
    for (let k = st; k < max; k += st) out.push(k, -k);
    return out;
  };

  // labels: right of the dot when there is room, else left / above / below (a simple collision check)
  const boxes: [number, number, number, number][] = [];
  const labels = items.map(({ s, path }) => {
    const [cx, cy] = [sx(path[path.length - 1][0]), sy(path[path.length - 1][1])];
    const w = s.label.length * 6.3;
    const options: [number, number][] = [
      [cx + 9, cy + 4], [cx - 9 - w, cy + 4], [cx - w / 2, cy - 10], [cx - w / 2, cy + 18],
      [cx + 9, cy - 8], [cx + 9, cy + 16], [cx - 9 - w, cy - 8], [cx - 9 - w, cy + 16],
      [cx + 9, cy - 20], [cx + 9, cy + 28], [cx - 9 - w, cy - 20], [cx - 9 - w, cy + 28],
      [cx - w / 2, cy - 24], [cx - w / 2, cy + 32],
    ];
    let chosen = options[0];
    for (const [tx, ty] of options) {
      const box: [number, number, number, number] = [tx - 2, ty - 11, tx + w + 2, ty + 3];
      const inside = box[0] >= PAD.l && box[2] <= W - PAD.r && box[1] >= PAD.t && box[3] <= H - PAD.b;
      if (inside && !boxes.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) {
        chosen = [tx, ty];
        break;
      }
    }
    boxes.push([chosen[0] - 2, chosen[1] - 11, chosen[0] + w + 2, chosen[1] + 3]);
    return { key: s.key, label: s.label, x: chosen[0], y: chosen[1] };
  });

  return (
    <div className="rot-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="rot-svg" role="img" aria-label="Sector rotation map">
        <rect x={x0} y={PAD.t} width={sx(xmax) - x0} height={y0 - PAD.t} className="rot-q rot-q-leading" />
        <rect x={PAD.l} y={PAD.t} width={x0 - PAD.l} height={y0 - PAD.t} className="rot-q rot-q-improving" />
        <rect x={x0} y={y0} width={sx(xmax) - x0} height={sy(-ymax) - y0} className="rot-q rot-q-weakening" />
        <rect x={PAD.l} y={y0} width={x0 - PAD.l} height={sy(-ymax) - y0} className="rot-q rot-q-lagging" />
        <text x={W - PAD.r - 8} y={PAD.t + 16} className="rot-qlabel" textAnchor="end">LEADING</text>
        <text x={PAD.l + 8} y={PAD.t + 16} className="rot-qlabel">IMPROVING</text>
        <text x={W - PAD.r - 8} y={H - PAD.b - 8} className="rot-qlabel" textAnchor="end">WEAKENING</text>
        <text x={PAD.l + 8} y={H - PAD.b - 8} className="rot-qlabel">LAGGING</text>
        {ticks(xmax).map((v) => (
          <g key={`x${v}`}>
            <line x1={sx(v)} x2={sx(v)} y1={PAD.t} y2={H - PAD.b} className="rot-grid" />
            <text x={sx(v)} y={H - PAD.b + 14} textAnchor="middle" className="rot-tick">{v > 0 ? `+${v}` : v}</text>
          </g>
        ))}
        {ticks(ymax).map((v) => (
          <g key={`y${v}`}>
            <line x1={PAD.l} x2={W - PAD.r} y1={sy(v)} y2={sy(v)} className="rot-grid" />
            <text x={PAD.l - 6} y={sy(v) + 4} textAnchor="end" className="rot-tick">{v > 0 ? `+${v}` : v}</text>
          </g>
        ))}
        <line x1={x0} x2={x0} y1={PAD.t} y2={H - PAD.b} className="rot-axis" />
        <line x1={PAD.l} x2={W - PAD.r} y1={y0} y2={y0} className="rot-axis" />
        <text x={PAD.l + pw / 2} y={H - 6} textAnchor="middle" className="rot-axis-label">1-month return vs Nifty 50 (pp)</text>
        <text x={12} y={PAD.t + ph / 2} textAnchor="middle" className="rot-axis-label" transform={`rotate(-90 12 ${PAD.t + ph / 2})`}>
          1-week return vs Nifty 50 (pp)
        </text>
        {items.map(({ s, path }) => (
          <g key={`t-${s.key}`} className={verdictClass(s.verdict)}>
            <polyline points={path.map(([x, y]) => `${sx(x)},${sy(y)}`).join(" ")} className="rot-tail" />
            {path.slice(0, -1).map(([x, y], i) => (
              <circle key={i} cx={sx(x)} cy={sy(y)} r={2.2} className="rot-old" />
            ))}
          </g>
        ))}
        {items.map(({ s, path }) => {
          const [x, y] = path[path.length - 1];
          return (
            <circle
              key={`d-${s.key}`}
              cx={sx(x)}
              cy={sy(y)}
              r={6}
              className={`rot-dot ${verdictClass(s.verdict)}`}
              onClick={() => onPick(s.key)}
            >
              <title>{`${s.label}: ${s.quadrant ?? ""} · ${x > 0 ? "+" : ""}${x.toFixed(2)}pp 1M, ${y > 0 ? "+" : ""}${y.toFixed(2)}pp 1W vs Nifty`}</title>
            </circle>
          );
        })}
        {labels.map((l) => (
          <text key={`l-${l.key}`} x={l.x} y={l.y} className="rot-label" onClick={() => onPick(l.key)}>
            {l.label}
          </text>
        ))}
      </svg>
      <div className="rot-legend muted small">
        <span><i className="rot-swatch rot-strong" /> STRONG</span>
        <span><i className="rot-swatch rot-mixed" /> MIXED</span>
        <span><i className="rot-swatch rot-weak" /> WEAK</span>
        <span><i className="rot-swatch rot-na" /> no verdict</span>
        <span>Dot = this week · faint line = a STRONG sector's last 4 weeks · click a sector to open it</span>
      </div>
    </div>
  );
}

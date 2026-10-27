import type { SystemOneEquityPoint } from "../../services/systemOneBacktestApi";

/** Cumulative realised P&L after each closed trade, drawn from the backend's equity_curve. */
export function EquityCurve({ points }: { points: SystemOneEquityPoint[] }) {
  if (points.length === 0) {
    return <p className="tb-config-hint">No closed trades yet, so there is no equity curve.</p>;
  }
  const W = 900;
  const H = 220;
  const PAD = { l: 70, r: 16, t: 12, b: 24 };
  const values = [0, ...points.map((p) => p.cumulative_pnl)];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => PAD.l + (points.length === 1 ? 0.5 : i / (points.length - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - min) / span) * (H - PAD.t - PAD.b);
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.cumulative_pnl).toFixed(1)}`).join(" ");
  const fmt = (v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: 0 });
  const last = points[points.length - 1].cumulative_pnl;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Cumulative realised P&L after each closed trade">
      <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} stroke="currentColor" strokeOpacity={0.35} strokeDasharray="4 4" />
      {[max, min].map((v) => (
        <text key={v} x={PAD.l - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="currentColor" opacity={0.7}>
          {fmt(v)}
        </text>
      ))}
      <text x={PAD.l - 6} y={y(0) + 4} textAnchor="end" fontSize="11" fill="currentColor" opacity={0.7}>
        0
      </text>
      <path d={line} fill="none" stroke={last >= 0 ? "var(--success)" : "var(--danger)"} strokeWidth={2} />
      {points.map((p, i) => (
        <circle key={p.trade_number} cx={x(i)} cy={y(p.cumulative_pnl)} r={3} fill={p.cumulative_pnl >= 0 ? "var(--success)" : "var(--danger)"}>
          <title>{`Trade #${p.trade_number} · ${new Date(p.date).toLocaleDateString("en-IN")} · ₹${fmt(p.cumulative_pnl)}`}</title>
        </circle>
      ))}
      <text x={PAD.l} y={H - 6} fontSize="11" fill="currentColor" opacity={0.7}>
        Trade 1
      </text>
      <text x={W - PAD.r} y={H - 6} textAnchor="end" fontSize="11" fill="currentColor" opacity={0.7}>
        Trade {points[points.length - 1].trade_number} (by exit order)
      </text>
    </svg>
  );
}

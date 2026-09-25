import type { CrosshairReadout } from "./useTradingViewChart";

function fmt(value: number): string {
  return value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtVolume(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  if (value >= 1e7) return `${(value / 1e7).toFixed(2)}Cr`;
  if (value >= 1e5) return `${(value / 1e5).toFixed(2)}L`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return String(Math.round(value));
}

/** Price-pane legend: always shows a bar — the hovered one, or the latest. */
export function OHLCReadout({ readout, showVolume }: { readout: CrosshairReadout | null; showVolume: boolean }) {
  if (!readout) return null;
  const change = readout.prevClose !== null ? readout.close - readout.prevClose : null;
  const changePct = change !== null && readout.prevClose ? (change / readout.prevClose) * 100 : null;
  const tone = change === null ? (readout.close >= readout.open ? "ohlc-up" : "ohlc-down") : change >= 0 ? "ohlc-up" : "ohlc-down";
  return (
    <span className="ohlc-readout">
      <span>O <strong className={tone}>{fmt(readout.open)}</strong></span>
      <span>H <strong className={tone}>{fmt(readout.high)}</strong></span>
      <span>L <strong className={tone}>{fmt(readout.low)}</strong></span>
      <span>C <strong className={tone}>{fmt(readout.close)}</strong></span>
      {change !== null && changePct !== null && (
        <strong className={tone}>
          {change >= 0 ? "+" : ""}{fmt(change)} ({change >= 0 ? "+" : ""}{changePct.toFixed(2)}%)
        </strong>
      )}
      {showVolume && readout.volume !== null && <span>Vol <strong>{fmtVolume(readout.volume)}</strong></span>}
    </span>
  );
}

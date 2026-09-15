import type { CrosshairReadout } from "./useTradingViewChart";

function fmt(value: number): string {
  return value.toFixed(2);
}

export function OHLCReadout({ readout }: { readout: CrosshairReadout | null }) {
  if (!readout) {
    return <span className="ohlc-readout-empty">Hover the chart for OHLC</span>;
  }
  const changeUp = readout.close >= readout.open;
  return (
    <span className="ohlc-readout">
      <span>O <strong>{fmt(readout.open)}</strong></span>
      <span>H <strong>{fmt(readout.high)}</strong></span>
      <span>L <strong>{fmt(readout.low)}</strong></span>
      <span>
        C <strong className={changeUp ? "ohlc-up" : "ohlc-down"}>{fmt(readout.close)}</strong>
      </span>
    </span>
  );
}

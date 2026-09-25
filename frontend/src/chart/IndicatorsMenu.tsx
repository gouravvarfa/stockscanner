import { useState } from "react";
import type { IndicatorSettings } from "./chartTypes";

export function IndicatorsMenu({ value, onChange }: { value: IndicatorSettings; onChange: (next: IndicatorSettings) => void }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="chart-dropdown">
      <button
        type="button"
        className={open ? "chart-toolbar-btn active" : "chart-toolbar-btn"}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M1.5 12.5l4-5 3 3 6-8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Indicators
      </button>
      {open && (
        <>
          <div className="chart-dropdown-backdrop" onClick={() => setOpen(false)} />
          <div className="chart-dropdown-panel">
            <span className="chart-dropdown-heading">Overlays</span>

            <label className="chart-dropdown-item">
              <input type="checkbox" checked={value.bollinger} onChange={(e) => onChange({ ...value, bollinger: e.target.checked })} />
              Bollinger Bands
            </label>
            {value.bollinger && (
              <div className="chart-dropdown-subrow">
                <label>
                  Length
                  <input
                    type="number"
                    min={2}
                    value={value.bollingerPeriod}
                    onChange={(e) => onChange({ ...value, bollingerPeriod: Number(e.target.value) })}
                  />
                </label>
                <label>
                  Std Dev
                  <input
                    type="number"
                    min={0.5}
                    step={0.5}
                    value={value.bollingerMultiplier}
                    onChange={(e) => onChange({ ...value, bollingerMultiplier: Number(e.target.value) })}
                  />
                </label>
              </div>
            )}

            <span className="chart-dropdown-heading">Panes</span>
            <label className="chart-dropdown-item">
              <input type="checkbox" checked={value.volume} onChange={(e) => onChange({ ...value, volume: e.target.checked })} />
              Volume
            </label>
            <label className="chart-dropdown-item">
              <input type="checkbox" checked={value.rsi} onChange={(e) => onChange({ ...value, rsi: e.target.checked })} />
              RSI
            </label>
            {value.rsi && (
              <div className="chart-dropdown-subrow">
                <label>
                  Period
                  <input
                    type="number"
                    min={2}
                    value={value.rsiPeriod}
                    onChange={(e) => onChange({ ...value, rsiPeriod: Number(e.target.value) })}
                  />
                </label>
                <label>
                  Upper
                  <input
                    type="number"
                    value={value.rsiUpper}
                    onChange={(e) => onChange({ ...value, rsiUpper: Number(e.target.value) })}
                  />
                </label>
                <label>
                  Lower
                  <input
                    type="number"
                    value={value.rsiLower}
                    onChange={(e) => onChange({ ...value, rsiLower: Number(e.target.value) })}
                  />
                </label>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

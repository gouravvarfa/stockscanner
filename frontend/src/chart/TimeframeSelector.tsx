import { TIMEFRAMES, type Timeframe } from "./chartTypes";

export function TimeframeSelector({ value, onChange }: { value: Timeframe; onChange: (timeframe: Timeframe) => void }) {
  return (
    <div className="timeframe-row" role="tablist" aria-label="Chart timeframe">
      {TIMEFRAMES.map((timeframe) => (
        <button
          key={timeframe}
          type="button"
          role="tab"
          aria-selected={value === timeframe}
          className={value === timeframe ? "timeframe-pill active" : "timeframe-pill"}
          onClick={() => onChange(timeframe)}
        >
          {timeframe}
        </button>
      ))}
    </div>
  );
}

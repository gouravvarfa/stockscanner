import type { IChartApi, ISeriesApi, Time } from "lightweight-charts";

export interface OhlcBar {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
}

function fmt(v: number): string {
  return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtTime(t: Time): string {
  if (typeof t === "number") {
    // Intraday stamps are naive exchange time read as UTC (see SystemOneChart.toTime).
    return new Date(t * 1000).toISOString().slice(0, 16).replace("T", " ");
  }
  if (typeof t === "string") return t;
  return `${t.year}-${String(t.month).padStart(2, "0")}-${String(t.day).padStart(2, "0")}`;
}

/** TradingView-style legend in the chart's top-left corner: the O / H / L / C
 *  (and change) of the candle under the crosshair, or of the latest candle when
 *  the pointer is off the chart. Returns a function that removes it. */
export function attachOhlcLegend(
  container: HTMLElement,
  chart: IChartApi,
  series: ISeriesApi<"Candlestick">,
  bars: OhlcBar[],
  colors: { up: string; down: string; text: string },
): (() => void) & { refresh: () => void } {
  const el = document.createElement("div");
  el.setAttribute("data-ohlc-legend", "true");
  el.style.cssText =
    "position:absolute;top:6px;left:8px;z-index:3;pointer-events:none;font-size:12px;" +
    "font-variant-numeric:tabular-nums;display:flex;flex-wrap:wrap;gap:4px 10px;line-height:1.4;";
  container.appendChild(el);

  const render = (bar: OhlcBar | undefined) => {
    if (!bar) {
      el.textContent = "";
      return;
    }
    const change = bar.close - bar.open;
    const pct = bar.open !== 0 ? (change / bar.open) * 100 : 0;
    const color = change >= 0 ? colors.up : colors.down;
    const sign = change >= 0 ? "+" : "";
    const item = (label: string, value: string) =>
      `<span><span style="opacity:.65">${label}</span> <span style="color:${color}">${value}</span></span>`;
    el.innerHTML =
      `<span style="opacity:.8;color:${colors.text}">${fmtTime(bar.time)}</span>` +
      item("O", fmt(bar.open)) + item("H", fmt(bar.high)) + item("L", fmt(bar.low)) + item("C", fmt(bar.close)) +
      `<span style="color:${color}">${sign}${fmt(change)} (${sign}${pct.toFixed(2)}%)</span>`;
  };

  render(bars[bars.length - 1]);
  const handler = (param: Parameters<Parameters<IChartApi["subscribeCrosshairMove"]>[0]>[0]) => {
    const d = param.seriesData.get(series) as OhlcBar | undefined;
    if (param.time !== undefined && d && "open" in d) render({ ...d, time: param.time });
    else render(bars[bars.length - 1]);
  };
  chart.subscribeCrosshairMove(handler);

  const detach = () => {
    try {
      chart.unsubscribeCrosshairMove(handler);
    } catch {
      // chart already removed
    }
    el.remove();
  };
  // `bars` may be filled after attaching (SystemOneChart loads data in a later effect).
  return Object.assign(detach, { refresh: () => render(bars[bars.length - 1]) });
}

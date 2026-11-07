import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from "lightweight-charts";
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type { SystemOneCandle } from "../../services/systemOneBacktestApi";

/** One stretch where RSI is above the level. `from` is the first bar above it;
 *  `to` is the first bar back at/below it (`ended` = false: still above on the last bar). */
export interface RsiBand {
  from: Time;
  to: Time;
  ended: boolean;
}

/** Stretches of consecutive bars with RSI strictly above `level`. On the daily
 *  chart the GFS setup reads the latest completed weekly/monthly bar, so these
 *  are exactly the dates on which that timeframe's condition holds. */
export function computeRsiBands(candles: SystemOneCandle[], level = 60): RsiBand[] {
  const bands: RsiBand[] = [];
  let from: Time | null = null;
  for (const k of candles) {
    const t = k.date.slice(0, 10) as Time;
    const above = k.rsi !== null && k.rsi > level;
    if (above && from === null) from = t;
    else if (!above && from !== null) {
      bands.push({ from, to: t, ended: true });
      from = null;
    }
  }
  if (from !== null && candles.length > 0) {
    bands.push({ from, to: candles[candles.length - 1].date.slice(0, 10) as Time, ended: false });
  }
  return bands;
}

const FILL = "rgba(34, 197, 94, 0.12)";
const START_LINE = "rgba(34, 197, 94, 0.95)";
const END_LINE = "rgba(239, 68, 68, 0.95)";

class BandRenderer implements IPrimitivePaneRenderer {
  private readonly owner: RsiBandsPrimitive;
  constructor(owner: RsiBandsPrimitive) {
    this.owner = owner;
  }

  draw(target: CanvasRenderingTarget2D): void {
    const chart = this.owner.chart;
    if (!chart) return;
    const scale = chart.timeScale();
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      for (const band of this.owner.bands) {
        const x1 = scale.timeToCoordinate(band.from);
        const x2 = scale.timeToCoordinate(band.to);
        if (x1 === null || x2 === null) continue;
        if (Math.max(x1, x2) < 0 || Math.min(x1, x2) > mediaSize.width) continue;
        ctx.fillStyle = FILL;
        ctx.fillRect(x1, 0, x2 - x1, mediaSize.height);
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 4]);
        ctx.strokeStyle = START_LINE;
        ctx.beginPath();
        ctx.moveTo(x1, 0);
        ctx.lineTo(x1, mediaSize.height);
        ctx.stroke();
        if (band.ended) {
          ctx.strokeStyle = END_LINE;
          ctx.beginPath();
          ctx.moveTo(x2, 0);
          ctx.lineTo(x2, mediaSize.height);
          ctx.stroke();
        }
        ctx.setLineDash([]);
      }
    });
  }
}

class BandPaneView implements IPrimitivePaneView {
  private readonly rend: BandRenderer;
  constructor(owner: RsiBandsPrimitive) {
    this.rend = new BandRenderer(owner);
  }
  zOrder() {
    return "bottom" as const;
  }
  renderer() {
    return this.rend;
  }
}

/** Shades the full pane height between the start and end of each RSI > 60
 *  stretch, with a dashed vertical line at each edge. Attach one to a series in
 *  each pane that should show it. */
export class RsiBandsPrimitive implements ISeriesPrimitive<Time> {
  chart: IChartApi | null = null;
  private readonly view = new BandPaneView(this);
  bands: RsiBand[];
  constructor(bands: RsiBand[]) {
    this.bands = bands;
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chart = param.chart;
  }
  detached(): void {
    this.chart = null;
  }
  paneViews(): readonly IPrimitivePaneView[] {
    return [this.view];
  }
}

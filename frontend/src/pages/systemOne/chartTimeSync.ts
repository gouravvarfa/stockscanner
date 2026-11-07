import type { IChartApi, Time } from "lightweight-charts";

type Range = { from: Time; to: Time };

/** Keeps several charts on the SAME date window: moving or zooming one moves
 *  the others (bars differ per timeframe, so it syncs by date, not bar index).
 *
 *  Only the chart the user is driving broadcasts. Which chart that is follows
 *  the pointer (enter / press / wheel), or is set explicitly with `drive()` for
 *  programmatic moves. This stops the other charts' own events (which they
 *  clamp to their own data) from echoing back and shifting the driver. */
export class ChartTimeSync {
  private readonly charts = new Set<IChartApi>();
  private active: IChartApi | null = null;
  private applying = false;

  add(chart: IChartApi, container: HTMLElement): () => void {
    const activate = () => {
      this.active = chart;
    };
    const events = ["pointerenter", "pointerdown", "wheel", "touchstart"] as const;
    events.forEach((e) => container.addEventListener(e, activate, { passive: true }));

    const onRange = (range: Range | null) => {
      if (this.applying || this.active !== chart || !range) return;
      this.broadcast(chart, range);
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(onRange);
    this.charts.add(chart);

    return () => {
      chart.timeScale().unsubscribeVisibleTimeRangeChange(onRange);
      events.forEach((e) => container.removeEventListener(e, activate));
      this.charts.delete(chart);
      if (this.active === chart) this.active = null;
    };
  }

  /** Run a programmatic range change on `chart` and mirror it to the others. */
  drive(chart: IChartApi, move: () => void): void {
    this.active = chart;
    move();
    const range = chart.timeScale().getVisibleRange();
    if (range) this.broadcast(chart, range);
  }

  private broadcast(source: IChartApi, range: Range): void {
    this.applying = true;
    try {
      for (const other of this.charts) {
        if (other === source) continue;
        try {
          other.timeScale().setVisibleRange(range);
        } catch {
          // A chart without data yet, or a range it cannot satisfy, must not break the others.
        }
      }
    } finally {
      this.applying = false;
    }
  }
}

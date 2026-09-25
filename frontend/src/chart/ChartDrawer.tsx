import { useEffect, useRef, useState } from "react";
import { TradingViewChart } from "./TradingViewChart";
import type { ChartState } from "./chartTypes";

export interface ChartDrawerProps {
  state: ChartState;
  onToggleMaximize: () => void;
  onClose: () => void;
}

// Must match the .chart-drawer-closing animation duration in index.css.
const EXIT_MS = 180;

/**
 * Mounted once at the app root (see App.tsx) — switching symbols only
 * updates `state.symbol`, it never unmounts/remounts this drawer or the
 * chart instance inside it. Opening/closing never touches the scanner
 * page or triggers a scan.
 *
 * On close, the last open state is kept rendered for EXIT_MS with a
 * `closing` class so the drawer slides/fades out instead of vanishing.
 */
export function ChartDrawer({ state, onToggleMaximize, onClose }: ChartDrawerProps) {
  const isOpen = state.isOpen && Boolean(state.symbol);
  const lastOpenRef = useRef<ChartState | null>(null);
  const [, forceRender] = useState(0);
  if (isOpen) lastOpenRef.current = state;

  useEffect(() => {
    if (isOpen || !lastOpenRef.current) return;
    const timer = window.setTimeout(() => {
      lastOpenRef.current = null;
      forceRender((n) => n + 1);
    }, EXIT_MS);
    return () => window.clearTimeout(timer);
  }, [isOpen]);

  const current = isOpen ? state : lastOpenRef.current;
  if (!current || !current.symbol) return null;

  const classes = ["chart-drawer-backdrop"];
  if (current.isMaximized) classes.push("chart-drawer-backdrop-maximized");
  if (!isOpen) classes.push("chart-drawer-closing");

  return (
    <div className={classes.join(" ")} onClick={isOpen ? onClose : undefined}>
      <div onClick={(e) => e.stopPropagation()} className="chart-drawer-wrap">
        <TradingViewChart
          symbol={current.symbol}
          signalContext={current.signalContext}
          isMaximized={current.isMaximized}
          onToggleMaximize={onToggleMaximize}
          onClose={onClose}
        />
      </div>
    </div>
  );
}

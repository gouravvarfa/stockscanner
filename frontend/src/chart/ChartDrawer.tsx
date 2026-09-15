import { TradingViewChart } from "./TradingViewChart";
import type { ChartState } from "./chartTypes";

export interface ChartDrawerProps {
  state: ChartState;
  onToggleMaximize: () => void;
  onClose: () => void;
}

/**
 * Mounted once at the app root (see App.tsx) — switching symbols only
 * updates `state.symbol`, it never unmounts/remounts this drawer or the
 * chart instance inside it. Opening/closing never touches the scanner
 * page or triggers a scan.
 */
export function ChartDrawer({ state, onToggleMaximize, onClose }: ChartDrawerProps) {
  if (!state.isOpen || !state.symbol) return null;

  return (
    <div className={state.isMaximized ? "chart-drawer-backdrop chart-drawer-backdrop-maximized" : "chart-drawer-backdrop"} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="chart-drawer-wrap">
        <TradingViewChart
          symbol={state.symbol}
          signalContext={state.signalContext}
          isMaximized={state.isMaximized}
          onToggleMaximize={onToggleMaximize}
          onClose={onClose}
        />
      </div>
    </div>
  );
}

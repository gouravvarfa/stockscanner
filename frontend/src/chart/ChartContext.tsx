import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import type { ChartSignalContext, ChartState } from "./chartTypes";

interface ChartContextValue {
  state: ChartState;
  openChart: (symbol: string, signalContext?: ChartSignalContext | null) => void;
  closeChart: () => void;
  toggleMaximize: () => void;
}

const ChartContext = createContext<ChartContextValue | undefined>(undefined);

const INITIAL_STATE: ChartState = { isOpen: false, symbol: null, isMaximized: false, signalContext: null };

export function ChartProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ChartState>(INITIAL_STATE);

  const openChart = useCallback((symbol: string, signalContext: ChartSignalContext | null = null) => {
    // Switching symbols while already open reuses the same drawer/chart
    // instance — only `symbol`/`signalContext` change, isMaximized is kept.
    setState((current) => ({ ...current, isOpen: true, symbol, signalContext }));
  }, []);

  const closeChart = useCallback(() => {
    setState((current) => ({ ...current, isOpen: false, isMaximized: false }));
  }, []);

  const toggleMaximize = useCallback(() => {
    setState((current) => ({ ...current, isMaximized: !current.isMaximized }));
  }, []);

  return (
    <ChartContext.Provider value={{ state, openChart, closeChart, toggleMaximize }}>
      {children}
    </ChartContext.Provider>
  );
}

export function useChart(): ChartContextValue {
  const ctx = useContext(ChartContext);
  if (!ctx) throw new Error("useChart must be used within ChartProvider");
  return ctx;
}

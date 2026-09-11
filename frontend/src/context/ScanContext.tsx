import { createContext, useContext, useState, type ReactNode } from "react";
import type { ScanResult } from "../services/api";

interface ScanContextValue {
  latest: ScanResult | null;
  setLatest: (result: ScanResult | null) => void;
}

const ScanContext = createContext<ScanContextValue | undefined>(undefined);

export function ScanProvider({ children }: { children: ReactNode }) {
  const [latest, setLatest] = useState<ScanResult | null>(null);
  return <ScanContext.Provider value={{ latest, setLatest }}>{children}</ScanContext.Provider>;
}

export function useScan(): ScanContextValue {
  const ctx = useContext(ScanContext);
  if (!ctx) throw new Error("useScan must be used within ScanProvider");
  return ctx;
}

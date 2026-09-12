import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { api, type ScanResult } from "../services/api";

interface ScanContextValue {
  latest: ScanResult | null;
  setLatest: (result: ScanResult | null) => void;
  // Scan-in-progress state lives here (not in the Dashboard page component)
  // specifically so it survives navigating to another page — the fetch
  // itself was already running in the background regardless, but local
  // page state made it LOOK like the scan had stopped/reset the moment you
  // switched tabs, then come back to a plain "Run Scan" button as if
  // nothing happened.
  scanning: boolean;
  scanError: string | null;
  runScan: () => Promise<void>;
}

const ScanContext = createContext<ScanContextValue | undefined>(undefined);

export function ScanProvider({ children }: { children: ReactNode }) {
  const [latest, setLatest] = useState<ScanResult | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  // Guards against a double-trigger (e.g. clicking Run Scan again from a
  // different page) firing a second overlapping request.
  const inFlight = useRef(false);

  const runScan = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setScanning(true);
    setScanError(null);
    try {
      const result = await api.runScan("manual");
      setLatest(result);
    } catch (e) {
      setScanError(e instanceof Error ? e.message : String(e));
    } finally {
      inFlight.current = false;
      setScanning(false);
    }
  }, []);

  return (
    <ScanContext.Provider value={{ latest, setLatest, scanning, scanError, runScan }}>
      {children}
    </ScanContext.Provider>
  );
}

export function useScan(): ScanContextValue {
  const ctx = useContext(ScanContext);
  if (!ctx) throw new Error("useScan must be used within ScanProvider");
  return ctx;
}

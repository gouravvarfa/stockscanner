import { useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export type LiveConnectionStatus = "CONNECTED" | "RECONNECTING" | "DISCONNECTED" | "OFF";

export interface LiveCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  complete: boolean;
}

export type LiveCandlesByTimeframe = Record<string, LiveCandle>;

/**
 * 2026-09-25 WebSocket master prompt: opens a live tick stream for
 * `symbol` for as long as the chart using this hook stays mounted (the
 * effect's cleanup is the "chart close" signal — backend/api/live.py's
 * SSE endpoint acquires a subscription reference on connect and releases
 * it the moment this EventSource closes, so a symbol nobody has open
 * anywhere gets unsubscribed automatically, and re-opening the same
 * symbol elsewhere reuses the existing live stream rather than creating a
 * duplicate one).
 *
 * Degrades silently: if live data is unavailable (backend not deployed
 * yet, Angel One session not configured, market closed with no ticks
 * arriving) the hook just never updates `liveCandles` — the chart still
 * shows its normal historical data from fetchCandles(), unaffected.
 */
export function useLiveChart(symbol: string, enabled: boolean) {
  const [liveCandles, setLiveCandles] = useState<LiveCandlesByTimeframe | null>(null);
  const [status, setStatus] = useState<LiveConnectionStatus>("OFF");
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!enabled || !symbol) {
      setStatus("OFF");
      setLiveCandles(null);
      return;
    }

    setStatus("RECONNECTING");
    const source = new EventSource(`${API_BASE}/api/live/stream/${encodeURIComponent(symbol)}`);
    sourceRef.current = source;

    source.addEventListener("candle", (event) => {
      try {
        const candles = JSON.parse((event as MessageEvent).data) as LiveCandlesByTimeframe;
        setLiveCandles(candles);
        setStatus("CONNECTED");
      } catch {
        // Malformed payload - never crash the chart over a bad live tick.
      }
    });

    // Connected but no tick yet (e.g. market closed): the chart is showing
    // the last close, not "reconnecting".
    source.onopen = () => setStatus((prev) => (prev === "CONNECTED" ? prev : "OFF"));

    source.onerror = () => {
      // Browser's EventSource auto-reconnects on its own; this just
      // reflects that state in the UI without any custom retry logic.
      setStatus("RECONNECTING");
    };

    return () => {
      source.close();
      sourceRef.current = null;
      setStatus("OFF");
      setLiveCandles(null);
    };
  }, [symbol, enabled]);

  return { liveCandles, status };
}

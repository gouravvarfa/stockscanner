import { api, type AngelOneStatus } from "./api";
import { loadDeviceCredentials } from "./angeloneDeviceStore";

/**
 * One shared Angel One connection check for the whole app.
 *
 * Why: the backend (Render free plan) sleeps after ~15 idle minutes and its disk is wiped on every restart, so
 * it often comes back WITHOUT the saved credentials. Before, only the Settings page re-sent this device's saved
 * credentials, and a single failed status call (the server still waking up) was shown as "Not connected".
 *
 * Now, as soon as the app opens (and whenever the window becomes visible again or the internet comes back):
 *  1. ask the backend for its status, retrying while it wakes up (a cold start takes about a minute);
 *  2. if it has no credentials but this device remembers them, reconnect silently;
 *  3. while the app stays open, ping it every few minutes so it does not fall asleep under the user.
 */
export type ConnectionPhase = "checking" | "waking" | "connecting" | "connected" | "disconnected" | "offline";

export interface ConnectionState {
  phase: ConnectionPhase;
  status: AngelOneStatus | null;
  message: string;
}

const RETRY_DELAYS_MS = [0, 3000, 5000, 8000, 10000, 15000, 15000, 20000, 20000, 30000]; // ~2 minutes in total
const KEEP_AWAKE_MS = 4 * 60 * 1000;

let state: ConnectionState = { phase: "checking", status: null, message: "Checking the connection…" };
let inflight: Promise<ConnectionState> | null = null;
const listeners = new Set<(s: ConnectionState) => void>();

function set(next: ConnectionState) {
  state = next;
  listeners.forEach((fn) => fn(state));
}

export function getConnectionState(): ConnectionState {
  return state;
}

export function onConnectionChange(fn: (s: ConnectionState) => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Lets the Settings form publish a manual connect / disconnect to every listener. */
export function publishStatus(status: AngelOneStatus) {
  set({
    phase: status.configured ? "connected" : "disconnected",
    status,
    message: status.configured ? status.message : "Angel One not connected",
  });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function statusWithRetry(): Promise<AngelOneStatus | null> {
  for (let i = 0; i < RETRY_DELAYS_MS.length; i++) {
    if (RETRY_DELAYS_MS[i]) await sleep(RETRY_DELAYS_MS[i]);
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      set({ phase: "offline", status: state.status, message: "No internet connection" });
      return null;
    }
    try {
      return await api.getAngelOneStatus();
    } catch {
      if (i >= 1) set({ phase: "waking", status: state.status, message: "Server is waking up… (up to a minute)" });
    }
  }
  return null;
}

async function run(): Promise<ConnectionState> {
  if (state.phase !== "connected") set({ ...state, phase: "checking", message: "Checking the connection…" });
  const status = await statusWithRetry();
  if (status === null) {
    if (state.phase !== "offline") set({ phase: "disconnected", status: null, message: "Server not reachable - retrying shortly" });
    return state;
  }
  if (status.configured) {
    publishStatus(status);
    return state;
  }
  const saved = loadDeviceCredentials();
  if (!saved) {
    publishStatus(status);
    return state;
  }
  set({ phase: "connecting", status, message: "Reconnecting Angel One…" });
  try {
    publishStatus(await api.connectAngelOne(saved));
  } catch {
    set({ phase: "disconnected", status, message: "Saved credentials did not work - reconnect in Settings" });
  }
  return state;
}

/** Make sure the backend is awake and Angel One is connected. Concurrent calls share one attempt. */
export function ensureAngelOneConnected(): Promise<ConnectionState> {
  if (!inflight) {
    inflight = run().finally(() => {
      inflight = null;
    });
  }
  return inflight;
}

let started = false;

/** Call once at app start. Returns a cleanup function. */
export function startAutoConnect(): () => void {
  if (started) return () => undefined;
  started = true;
  void ensureAngelOneConnected();
  const onVisible = () => {
    if (document.visibilityState === "visible") void ensureAngelOneConnected();
  };
  const onOnline = () => void ensureAngelOneConnected();
  document.addEventListener("visibilitychange", onVisible);
  window.addEventListener("online", onOnline);
  const timer = window.setInterval(() => {
    if (document.visibilityState === "visible") void ensureAngelOneConnected();
  }, KEEP_AWAKE_MS);
  // A failed attempt is retried sooner than the keep-awake interval.
  const unsub = onConnectionChange((s) => {
    if (s.phase === "disconnected" && s.status === null) {
      window.setTimeout(() => void ensureAngelOneConnected(), 30000);
    }
  });
  return () => {
    started = false;
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onOnline);
    window.clearInterval(timer);
    unsub();
  };
}

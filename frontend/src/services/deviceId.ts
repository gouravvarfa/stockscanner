const STORAGE_KEY = "scanner_device_id";

function randomUuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  // Fallback for older browsers without crypto.randomUUID.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * A persistent, per-device/browser identifier — generated once and reused
 * from localStorage (never synced anywhere else). Used ONLY to scope which
 * browser sees/controls a live scan job (Active Scans panel): starting a
 * scan on a laptop must not make it appear as running on a phone that opens
 * the same deployed app, since both simply poll the same Render backend.
 * The scan computation itself is unaffected — this never leaves the browser
 * except as a plain id string sent back to this app's own API.
 */
export function getDeviceId(): string {
  try {
    const existing = localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;
    const id = randomUuid();
    localStorage.setItem(STORAGE_KEY, id);
    return id;
  } catch {
    // Private browsing / storage blocked — fall back to a per-session id
    // (this tab won't confuse itself with another device, it just won't
    // remember across a full reload either).
    return randomUuid();
  }
}

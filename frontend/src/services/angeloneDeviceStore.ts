import type { AngelOneConnectRequest } from "./api";

/**
 * Remembers Angel One credentials on THIS device only (browser localStorage),
 * so a server-side restart (which wipes the backend's saved-credentials file
 * on a free/ephemeral host) doesn't force retyping them every time. This is
 * a convenience for a single-user deployment, not a security boundary:
 * localStorage is plain text, readable by anything with access to this
 * browser profile. Never sent anywhere except back to this same backend's
 * own /connect endpoint, exactly like typing it into the form.
 */
const STORAGE_KEY = "angelone_device_credentials_v1";

export function saveDeviceCredentials(creds: AngelOneConnectRequest): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(creds));
  } catch {
    // Best-effort only (private browsing / storage disabled) — the form still works, just won't auto-fill next time.
  }
}

export function loadDeviceCredentials(): AngelOneConnectRequest | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && parsed.api_key && parsed.client_code && parsed.pin && parsed.totp_secret) {
      return parsed as AngelOneConnectRequest;
    }
    return null;
  } catch {
    return null;
  }
}

export function clearDeviceCredentials(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

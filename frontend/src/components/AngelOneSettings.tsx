import { useEffect, useState } from "react";
import { api, type AngelOneStatus } from "../services/api";

/**
 * The ONE centralized place credentials are entered/updated/cleared.
 * Scanner, Chart, Expiry Level 1, and Expiry Level 5 all share this same
 * backend-side credential store and Angel One provider instance — none of
 * them has (or should have) its own separate connect form. Saved values
 * are never echoed back from the backend, so this always shows a static
 * masked placeholder for a configured field, never a real character of
 * the actual key/PIN/TOTP secret.
 */
export function AngelOneSettings() {
  const [status, setStatus] = useState<AngelOneStatus | null>(null);
  const [editing, setEditing] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [clientCode, setClientCode] = useState("");
  const [pin, setPin] = useState("");
  const [totpSecret, setTotpSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);

  function refreshStatus() {
    api.getAngelOneStatus().then(setStatus).catch(() => undefined);
  }

  useEffect(() => {
    refreshStatus();
  }, []);

  function resetForm() {
    setApiKey("");
    setClientCode("");
    setPin("");
    setTotpSecret("");
    setMessage(null);
    setMessageKind(null);
  }

  function startEditing() {
    resetForm();
    setEditing(true);
  }

  const formComplete = apiKey && clientCode && pin && totpSecret;

  async function handleTestConnection() {
    if (!formComplete) return;
    setTesting(true);
    setMessage(null);
    try {
      const result = await api.testAngelOneConnection({ api_key: apiKey, client_code: clientCode, pin, totp_secret: totpSecret });
      setMessage(result.message);
      setMessageKind(result.success ? "success" : "error");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
      setMessageKind("error");
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    if (!formComplete) return;
    setSaving(true);
    setMessage(null);
    try {
      const s = await api.connectAngelOne({ api_key: apiKey, client_code: clientCode, pin, totp_secret: totpSecret });
      setStatus(s);
      setEditing(false);
      resetForm();
      setMessage("Saved and connected.");
      setMessageKind("success");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
      setMessageKind("error");
    } finally {
      setSaving(false);
    }
  }

  async function handleClear() {
    const s = await api.disconnectAngelOne();
    setStatus(s);
    setEditing(false);
    resetForm();
  }

  return (
    <div className="card angelone-settings">
      <h3>Angel One Settings</h3>
      <p className="muted small">
        One shared connection used by the A Group Scanner, Chart, Expiry Level 1, and Expiry Level 5 — there is no
        separate configuration for any of them. Credentials are verified with a real login before being saved, then
        stored locally on this machine only (never in this browser, never committed to git, never shown back to you
        once saved).
      </p>

      <div className="angelone-status">
        <span className={status?.configured ? "chip chip-pass" : "chip chip-fail"}>
          ● {status?.configured ? `Connected as ${status.client_code}` : "Not connected"}
        </span>
        {status?.connected_at && (
          <span className="muted small">Last successful connection: {new Date(status.connected_at).toLocaleString()}</span>
        )}
      </div>

      {!editing && (
        <div className="settings-actions">
          <button className="primary-button" onClick={startEditing}>
            {status?.configured ? "Update Credentials" : "Connect Angel One"}
          </button>
          {status?.configured && (
            <button className="secondary-button" onClick={handleClear}>
              Clear Configuration
            </button>
          )}
        </div>
      )}

      {editing && (
        <>
          <div className="filters-row">
            <label>
              API Key
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="off"
                placeholder={status?.configured ? "••••••••" : ""}
              />
            </label>
            <label>
              Client ID
              <input
                type="password"
                value={clientCode}
                onChange={(e) => setClientCode(e.target.value)}
                autoComplete="off"
                placeholder={status?.configured ? "••••••••" : ""}
              />
            </label>
            <label>
              PIN
              <input type="password" value={pin} onChange={(e) => setPin(e.target.value)} autoComplete="off" placeholder={status?.configured ? "••••" : ""} />
            </label>
            <label>
              TOTP Secret
              <input
                type="password"
                value={totpSecret}
                onChange={(e) => setTotpSecret(e.target.value)}
                autoComplete="off"
                placeholder={status?.configured ? "••••••••" : ""}
              />
            </label>
          </div>
          <div className="settings-actions">
            <button className="secondary-button" onClick={handleTestConnection} disabled={!formComplete || testing || saving}>
              {testing ? "Testing…" : "Test Connection"}
            </button>
            <button className="primary-button" onClick={handleSave} disabled={!formComplete || saving || testing}>
              {saving ? "Saving…" : "Save & Connect"}
            </button>
            <button
              className="secondary-button"
              onClick={() => {
                setEditing(false);
                resetForm();
              }}
            >
              Cancel
            </button>
          </div>
        </>
      )}

      {message && <p className={messageKind === "error" ? "error-banner small" : "muted small"}>{message}</p>}
    </div>
  );
}

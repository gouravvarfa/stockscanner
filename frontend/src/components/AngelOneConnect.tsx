import { useEffect, useState } from "react";
import { api, type AngelOneStatus } from "../services/api";

export function AngelOneConnect({ onConnectedChange }: { onConnectedChange?: (configured: boolean) => void }) {
  const [status, setStatus] = useState<AngelOneStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [clientCode, setClientCode] = useState("");
  const [pin, setPin] = useState("");
  const [totpSecret, setTotpSecret] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refreshStatus() {
    api
      .getAngelOneStatus()
      .then((s) => {
        setStatus(s);
        onConnectedChange?.(s.configured);
      })
      .catch(() => {
        /* status check failing shouldn't block the form from rendering */
      });
  }

  useEffect(() => {
    refreshStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      const s = await api.connectAngelOne({ api_key: apiKey, client_code: clientCode, pin, totp_secret: totpSecret });
      setStatus(s);
      onConnectedChange?.(s.configured);
      setPin("");
      setTotpSecret("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    const s = await api.disconnectAngelOne();
    setStatus(s);
    onConnectedChange?.(s.configured);
  }

  if (status?.configured) {
    return (
      <div className="card angelone-connect">
        <div className="angelone-status">
          <span className="chip chip-pass">● {status.message}</span>
          <button className="secondary-button" onClick={handleDisconnect}>
            Disconnect
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="card angelone-connect">
      <h3>Connect Angel One</h3>
      <p className="muted small">
        Needed only for Expiry Level 1's intraday (15m/1h) data. Credentials are sent once to verify a real login,
        then stored locally on this machine (never in this browser's localStorage, never committed to git).
      </p>
      <div className="filters-row">
        <label>
          API Key
          <input type="text" value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" />
        </label>
        <label>
          Client Code
          <input type="text" value={clientCode} onChange={(e) => setClientCode(e.target.value)} autoComplete="off" />
        </label>
        <label>
          PIN
          <input type="password" value={pin} onChange={(e) => setPin(e.target.value)} autoComplete="off" />
        </label>
        <label>
          TOTP Secret
          <input type="password" value={totpSecret} onChange={(e) => setTotpSecret(e.target.value)} autoComplete="off" />
        </label>
        <button
          className="primary-button"
          onClick={handleConnect}
          disabled={connecting || !apiKey || !clientCode || !pin || !totpSecret}
        >
          {connecting ? "Connecting…" : "Connect"}
        </button>
      </div>
      {error && <div className="error-banner small">{error}</div>}
    </div>
  );
}

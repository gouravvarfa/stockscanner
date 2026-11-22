import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ensureAngelOneConnected, getConnectionState, onConnectionChange } from "../services/angeloneAutoConnect";

/**
 * Read-only status display for pages that NEED Angel One connected
 * (scans and backtests) but don't own the credential form themselves -
 * credentials are configured in exactly one place: Settings. This shows the
 * app-wide connection (angeloneAutoConnect.ts), which wakes the server and
 * reconnects with this device's saved credentials on its own.
 */
export function AngelOneStatusBanner({ onConnectedChange }: { onConnectedChange?: (configured: boolean) => void }) {
  const [conn, setConn] = useState(getConnectionState());

  useEffect(() => {
    const unsub = onConnectionChange((s) => {
      setConn(s);
      if (s.phase === "connected" || s.phase === "disconnected") onConnectedChange?.(s.phase === "connected");
    });
    void ensureAngelOneConnected().then((s) => onConnectedChange?.(s.phase === "connected"));
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (conn.phase === "connected") {
    return (
      <div className="card angelone-status">
        <span className="chip chip-pass">● {conn.message}</span>
      </div>
    );
  }

  if (conn.phase === "checking" || conn.phase === "waking" || conn.phase === "connecting") {
    return (
      <div className="card angelone-status">
        <span className="chip">● {conn.message}</span>
      </div>
    );
  }

  return (
    <div className="card angelone-status">
      <span className="chip chip-fail">● {conn.message}</span>
      <button type="button" className="secondary-button" onClick={() => void ensureAngelOneConnected()}>
        Retry
      </button>
      <Link to="/settings" className="secondary-button">
        Configure in Settings
      </Link>
    </div>
  );
}

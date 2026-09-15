import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AngelOneStatus } from "../services/api";

/**
 * Read-only status display for pages that NEED Angel One connected
 * (Expiry Level 1/5) but don't own the credential form themselves —
 * credentials are configured in exactly one place: Settings. This just
 * reports the shared connection's current state and points there.
 */
export function AngelOneStatusBanner({ onConnectedChange }: { onConnectedChange?: (configured: boolean) => void }) {
  const [status, setStatus] = useState<AngelOneStatus | null>(null);

  useEffect(() => {
    api
      .getAngelOneStatus()
      .then((s) => {
        setStatus(s);
        onConnectedChange?.(s.configured);
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (status?.configured) {
    return (
      <div className="card angelone-status">
        <span className="chip chip-pass">● {status.message}</span>
      </div>
    );
  }

  return (
    <div className="card angelone-status">
      <span className="chip chip-fail">● Angel One not connected</span>
      <Link to="/settings" className="secondary-button">
        Configure in Settings
      </Link>
    </div>
  );
}

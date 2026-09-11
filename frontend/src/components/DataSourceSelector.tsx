import { useEffect, useState } from "react";
import { api, type DataSourceMode, type ProviderStatus } from "../services/api";

const OPTIONS: { value: DataSourceMode; label: string }[] = [
  { value: "auto", label: "Auto / Fallback" },
  { value: "tapetide", label: "Tapetide" },
  { value: "angel_one", label: "Angel One" },
];

const STATUS_LABEL: Record<string, string> = {
  OK: "Available",
  RATE_LIMITED: "Rate Limited",
  CONNECTED: "Connected",
  NOT_CONFIGURED: "Not Connected",
  UNKNOWN: "Unknown (no recent call)",
};

function statusChipClass(status: string): string {
  if (status === "OK" || status === "CONNECTED") return "chip chip-pass";
  if (status === "RATE_LIMITED" || status === "NOT_CONFIGURED") return "chip chip-fail";
  return "chip";
}

export function DataSourceSelector() {
  const [mode, setMode] = useState<DataSourceMode>("auto");
  const [statuses, setStatuses] = useState<ProviderStatus[]>([]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function refresh() {
    api.getDataSource().then((c) => setMode(c.mode));
    api.getProviderStatus().then(setStatuses).catch(() => undefined);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleChange(newMode: DataSourceMode) {
    setMode(newMode);
    setSaving(true);
    setMessage(null);
    try {
      await api.updateDataSource({ mode: newMode });
      setMessage("Saved.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h3>Market Data Source</h3>
      <p className="muted small">
        Applies globally across all strategies. Auto prefers Tapetide, falling back to Angel One only when
        required data is unavailable (never because a stock simply doesn't qualify).
      </p>
      <div className="chip-row" style={{ marginBottom: 14 }}>
        {OPTIONS.map((opt) => (
          <label key={opt.value} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
            <input
              type="radio"
              name="data-source-mode"
              checked={mode === opt.value}
              onChange={() => handleChange(opt.value)}
              disabled={saving}
            />
            {opt.label}
          </label>
        ))}
      </div>
      {message && <p className="muted small">{message}</p>}

      <h4>Market Data Providers</h4>
      <div className="chip-row">
        {statuses.map((s) => (
          <span key={s.name} className={statusChipClass(s.status)} title={s.detail ?? undefined}>
            {s.name.replace("_", " ")} · {STATUS_LABEL[s.status] ?? s.status}
          </span>
        ))}
        <button className="secondary-button" onClick={refresh} style={{ marginLeft: 8 }}>
          Refresh
        </button>
      </div>
    </div>
  );
}

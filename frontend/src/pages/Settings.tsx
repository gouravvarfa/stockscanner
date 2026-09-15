import { useEffect, useState } from "react";
import { api, type StrategyConfig } from "../services/api";
import { AngelOneSettings } from "../components/AngelOneSettings";

export function Settings() {
  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api.getConfig().then(setConfig);
  }, []);

  function updateWeight(key: string, value: number) {
    setConfig((c) => (c ? { ...c, weights: { ...c.weights, [key]: value } } : c));
  }

  async function save() {
    if (!config) return;
    setSaving(true);
    setMessage(null);
    try {
      const updated = await api.updateConfig(config);
      setConfig(updated);
      setMessage("Saved.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function reset() {
    const defaults = await api.resetConfig();
    setConfig(defaults);
    setMessage("Reset to defaults.");
  }

  const weightTotal = config ? Object.values(config.weights).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p className="page-subtitle">Provider configuration, data usage, and strategy scoring</p>
        </div>
      </div>

      <AngelOneSettings />

      {!config ? (
        <div className="card">
          <p className="muted small">Loading…</p>
        </div>
      ) : (
        <>
          <div className="card">
            <h3>Scoring Weights (sum: {weightTotal.toFixed(0)})</h3>
            <div className="settings-grid">
              {Object.entries(config.weights).map(([key, value]) => (
                <label key={key}>
                  {key.replace(/_/g, " ")}
                  <input type="number" value={value} onChange={(e) => updateWeight(key, Number(e.target.value))} />
                </label>
              ))}
            </div>
          </div>

          <div className="card">
            <h3>Stock RSI thresholds</h3>
            <div className="settings-grid">
              <label>
                Weekly min
                <input
                  type="number"
                  value={config.stock_rsi.weekly_min}
                  onChange={(e) =>
                    setConfig({ ...config, stock_rsi: { ...config.stock_rsi, weekly_min: Number(e.target.value) } })
                  }
                />
              </label>
              <label>
                Weekly max
                <input
                  type="number"
                  value={config.stock_rsi.weekly_max}
                  onChange={(e) =>
                    setConfig({ ...config, stock_rsi: { ...config.stock_rsi, weekly_max: Number(e.target.value) } })
                  }
                />
              </label>
              <label>
                Monthly min
                <input
                  type="number"
                  value={config.stock_rsi.monthly_min}
                  onChange={(e) =>
                    setConfig({ ...config, stock_rsi: { ...config.stock_rsi, monthly_min: Number(e.target.value) } })
                  }
                />
              </label>
            </div>
          </div>

          <div className="card">
            <h3>Divergence</h3>
            <div className="settings-grid">
              <label>
                Strict mode (any bearish divergence disqualifies)
                <input
                  type="checkbox"
                  checked={config.divergence.strict_mode}
                  onChange={(e) =>
                    setConfig({ ...config, divergence: { ...config.divergence, strict_mode: e.target.checked } })
                  }
                />
              </label>
            </div>
          </div>

          <div className="settings-actions">
            <button className="primary-button" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button className="secondary-button" onClick={reset}>
              Reset to defaults
            </button>
            {message && <span className="muted">{message}</span>}
          </div>
        </>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { api, type CallMetrics, type StrategyConfig } from "../services/api";
import { DataSourceSelector } from "../components/DataSourceSelector";

function DataUsageCard() {
  const [metrics, setMetrics] = useState<CallMetrics | null>(null);

  function refresh() {
    api.getCallMetrics().then(setMetrics).catch(() => undefined);
  }

  useEffect(() => {
    refresh();
  }, []);

  if (!metrics) {
    return (
      <div className="card">
        <h3>Data Usage</h3>
        <p className="muted small">Loading…</p>
      </div>
    );
  }

  const usedPct = metrics.tapetide_quota > 0 ? (metrics.tapetide_calls / metrics.tapetide_quota) * 100 : 0;
  const barClass = usedPct >= 90 ? "usage-bar-fill danger" : usedPct >= 70 ? "usage-bar-fill warning" : "usage-bar-fill";

  return (
    <div className="card">
      <h3>Data Usage — Tapetide ({metrics.day})</h3>
      <div className="usage-bar">
        <div className={barClass} style={{ width: `${Math.min(100, usedPct)}%` }} />
      </div>
      <div className="usage-grid" style={{ marginTop: 14 }}>
        <div className="usage-stat">
          <span className="usage-value">{metrics.tapetide_quota}</span>
          <span className="usage-label">Daily Limit</span>
        </div>
        <div className="usage-stat">
          <span className="usage-value">{metrics.tapetide_calls}</span>
          <span className="usage-label">Calls Used</span>
        </div>
        <div className="usage-stat">
          <span className="usage-value">{metrics.tapetide_quota_remaining}</span>
          <span className="usage-label">Calls Remaining</span>
        </div>
        <div className="usage-stat">
          <span className="usage-value">{metrics.tapetide_cache_hits}</span>
          <span className="usage-label">Cache Hits</span>
        </div>
        <div className="usage-stat">
          <span className="usage-value">{metrics.tapetide_cache_misses}</span>
          <span className="usage-label">Cache Misses</span>
        </div>
        <div className="usage-stat">
          <span className="usage-value">{metrics.angelone_calls}</span>
          <span className="usage-label">Angel One Calls</span>
        </div>
      </div>
      <div className="settings-actions">
        <button className="secondary-button" onClick={refresh}>
          Refresh
        </button>
      </div>
    </div>
  );
}

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

      <DataSourceSelector />
      <DataUsageCard />

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

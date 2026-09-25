import { NavLink } from "react-router-dom";
import { useScan } from "../context/ScanContext";
import { STRATEGY_NAMES } from "../services/api";
import {
  BellIcon,
  CalendarIcon,
  DashboardIcon,
  HistoryIcon,
  ListIcon,
  SectorIcon,
  SettingsIcon,
  TargetIcon,
  TrendIcon,
} from "./icons";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true, icon: DashboardIcon },
  { to: "/strategies", label: "Strategies", icon: TargetIcon },
  { to: "/expiry-level-1", label: "Expiry Level 1", icon: CalendarIcon },
  { to: "/expiry-level-5", label: "Expiry Level 5", icon: CalendarIcon },
  { to: "/stocks", label: "A Group Scanner", icon: ListIcon },
  { to: "/tradingview", label: "TradingView Signals", icon: BellIcon },
  { to: "/top-bottom", label: "Top Bottom Backtesting", icon: TrendIcon },
  { to: "/cup-breakout", label: "Cup Breakout", icon: SectorIcon },
  { to: "/history", label: "Scan History", icon: HistoryIcon },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

/**
 * On desktop this is the always-visible left rail (unchanged). On mobile
 * (see the `.app-sidebar` responsive rules) it becomes an off-canvas panel
 * toggled by the hamburger button in Header — `open`/`onClose` are only
 * meaningful there; desktop ignores them.
 */
export function Sidebar({ open, onClose }: { open?: boolean; onClose?: () => void }) {
  return (
    <>
      {open && <div className="sidebar-backdrop" onClick={onClose} aria-hidden="true" />}
      <aside className={open ? "app-sidebar open" : "app-sidebar"}>
        <div className="sidebar-brand">
          <img src="/apple-touch-icon.png" alt="" className="sidebar-brand-icon sidebar-brand-logo" width={30} height={30} />
          A Group Scanner
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => (isActive ? "sidebar-link active" : "sidebar-link")}
                onClick={onClose}
              >
                <Icon />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <ScanEngineWidget />
      </aside>
    </>
  );
}

function fmtEta(seconds: number | null): string {
  if (seconds === null) return "Estimating…";
  const s = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * A Group scan status at the foot of the sidebar — live progress while a
 * scan runs, otherwise the last completed scan's totals. Reads only the
 * existing ScanContext (no extra requests, no new state).
 */
function ScanEngineWidget() {
  const { scanning, progress, latest } = useScan();
  if (!scanning && !latest) return null;

  const lastSignals = latest
    ? STRATEGY_NAMES.reduce((sum, name) => sum + (latest.strategies?.[name]?.length ?? 0), 0)
    : 0;
  const pct = scanning && progress ? Math.min(progress.percentage, 100) : 100;

  return (
    <div className={scanning ? "scan-engine scan-engine-running" : "scan-engine"}>
      <div className="scan-engine-head">
        <span className="scan-engine-dot" aria-hidden="true" />
        <div>
          <div className="scan-engine-title">Scan Engine</div>
          <div className="scan-engine-state">{scanning ? "Running…" : "Idle · last scan done"}</div>
        </div>
      </div>
      <div className="scan-engine-bar-row">
        <div className="active-scan-bar scan-engine-bar">
          <div className="active-scan-bar-fill" style={{ transform: `scaleX(${pct / 100})` }} />
        </div>
        <span className="scan-engine-pct">{Math.round(pct)}%</span>
      </div>
      <dl className="scan-engine-stats">
        {scanning && progress ? (
          <>
            <dt>Processed</dt><dd>{progress.processed} / {progress.total || "?"}</dd>
            <dt>Signals</dt><dd>{progress.signalsFound}</dd>
            <dt>Failed</dt><dd>{progress.failed}</dd>
            <dt>ETA</dt><dd>{fmtEta(progress.etaSeconds)}</dd>
          </>
        ) : latest ? (
          <>
            <dt>Processed</dt><dd>{latest.stocks_scanned} / {latest.universe_requested}</dd>
            <dt>Signals</dt><dd>{lastSignals}</dd>
            <dt>Failed</dt><dd>{latest.stocks_failed}</dd>
            <dt>Time</dt><dd>{latest.execution_seconds.toFixed(0)}s</dd>
          </>
        ) : null}
      </dl>
    </div>
  );
}

import type React from "react";
import { NavLink } from "react-router-dom";
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

// `tone`: each item's own colour for its icon tile and its active tint (see design.css).
const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true, icon: DashboardIcon, tone: "#2563eb" },
  { to: "/strategies", label: "Strategies", icon: TargetIcon, tone: "#9333ea" },
  { to: "/expiry-level-1", label: "Expiry Level 1", icon: CalendarIcon, tone: "#0284c7" },
  { to: "/expiry-level-5", label: "Expiry Level 5", icon: CalendarIcon, tone: "#0d9488" },
  { to: "/stocks", label: "A Group Scanner", icon: ListIcon, tone: "#16a34a" },
  { to: "/tradingview", label: "TradingView Signals", icon: BellIcon, tone: "#db2777" },
  { to: "/top-bottom", label: "Top Bottom Backtesting", icon: TrendIcon, tone: "#ea580c" },
  { to: "/cup-breakout", label: "Cup Breakout", icon: SectorIcon, tone: "#7c3aed" },
  { to: "/history", label: "Scan History", icon: HistoryIcon, tone: "#059669" },
  { to: "/breakout-15", label: "15-Min Breakout", icon: TrendIcon, tone: "#0284c7" },
  { to: "/settings", label: "Settings", icon: SettingsIcon, tone: "#475b8a" },
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
          <img src="/logo-mark.png" alt="" className="brand-mark" width={36} height={36} />
          <span className="brand-name">A Group Scanner</span>
          <span className="brand-tag">NSE strategy scanner</span>
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
                style={{ "--tone": item.tone } as React.CSSProperties}
                onClick={onClose}
              >
                <span className="nav-tile">
                  <Icon />
                </span>
                {item.label}
              </NavLink>
            );
          })}
        </nav>
      </aside>
    </>
  );
}

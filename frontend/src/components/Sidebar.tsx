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

type NavItem = { to: string; label: string; end?: boolean; icon: typeof DashboardIcon; tone: string };

// The menu, grouped like a product's navigation. `tone`: each item's own colour for its icon tile and its
// active tint (see design.css). Routes and labels are unchanged; only the grouping is visual.
export const NAV_SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Overview",
    items: [
      { to: "/", label: "Dashboard", end: true, icon: DashboardIcon, tone: "#2563eb" },
      { to: "/strategies", label: "Strategies", icon: TargetIcon, tone: "#9333ea" },
    ],
  },
  {
    title: "Scanners",
    items: [
      { to: "/stocks", label: "A Group Scanner", icon: ListIcon, tone: "#16a34a" },
      { to: "/expiry-level-1", label: "Expiry Level 1", icon: CalendarIcon, tone: "#0284c7" },
      { to: "/expiry-level-5", label: "Expiry Level 5", icon: CalendarIcon, tone: "#0d9488" },
      { to: "/cup-breakout", label: "Cup Breakout", icon: SectorIcon, tone: "#7c3aed" },
      { to: "/tradingview", label: "TradingView Signals", icon: BellIcon, tone: "#db2777" },
    ],
  },
  {
    title: "Backtesting",
    items: [
      { to: "/top-bottom", label: "Top Bottom Backtesting", icon: TrendIcon, tone: "#ea580c" },
      { to: "/breakout-15", label: "15-Min Breakout", icon: TrendIcon, tone: "#0284c7" },
    ],
  },
  {
    title: "Workspace",
    items: [
      { to: "/history", label: "Scan History", icon: HistoryIcon, tone: "#059669" },
      { to: "/settings", label: "Settings", icon: SettingsIcon, tone: "#475b8a" },
    ],
  },
];

const SUB_PAGES: Record<string, string> = {
  "/strategies/system-one": "System One",
  "/strategies/gfs": "GFS",
  "/strategies/advanced-gfs": "Advanced GFS",
  "/strategies/gfs-50": "50 GFS",
};

/** Breadcrumb for the top bar, e.g. ["Backtesting", "Top Bottom Backtesting"] or ["Overview", "Strategies", "GFS", "All Stocks"]. */
export function navTrail(pathname: string): string[] {
  const path = pathname.replace(/\/+$/, "") || "/";
  for (const section of NAV_SECTIONS) {
    for (const item of section.items) {
      const hit = item.to === "/" ? path === "/" : path === item.to || path.startsWith(item.to + "/");
      if (!hit) continue;
      const trail = [section.title, item.label];
      const sub = Object.keys(SUB_PAGES).find((p) => path === p || path.startsWith(p + "/"));
      if (sub) trail.push(SUB_PAGES[sub]);
      if (sub && path.endsWith("/stocks")) trail.push("All Stocks");
      return trail;
    }
  }
  return [];
}

/**
 * On desktop this is the always-visible left rail. On mobile (see the `.app-sidebar` responsive rules) it
 * becomes an off-canvas panel toggled by the hamburger button in Header — `open`/`onClose` are only
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
        <nav className="sidebar-nav" aria-label="Main">
          {NAV_SECTIONS.map((section) => (
            <div className="nav-section" key={section.title}>
              <div className="nav-section-title">{section.title}</div>
              {section.items.map((item) => {
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
                    <span className="nav-label">{item.label}</span>
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="sidebar-foot-dot" />
          NSE · BSE · MCX
        </div>
      </aside>
    </>
  );
}

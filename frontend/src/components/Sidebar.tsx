import type React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { navigateSmoothly } from "../services/pageTransition";
import {
  CalendarIcon,
  AngleIcon,
  ChartBarIcon,
  DashboardIcon,
  HistoryIcon,
  ListIcon,
  SectorIcon,
  SettingsIcon,
  TargetIcon,
  HeatmapIcon,
  StarIcon,
  TrendIcon,
  ValueTagIcon,
} from "./icons";

type NavItem = { to: string; label: string; end?: boolean; icon: typeof DashboardIcon; tone: string };

// The menu (one flat list). Order set by the user (2026-11-23): Dashboard, Strategies, Cup Breakout, Value Buy, Weekly
// Sectors, Heatmap, Top Bottom, 15-Min Breakout, Gann Square, Angle Projection, Anniversary Dates, Astro Watch, then
// the rest, Settings last. `tone`: each item's
// own colour for its icon tile and its active tint (see design.css).
export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Setup Scanner", end: true, icon: DashboardIcon, tone: "#2563eb" },
  { to: "/strategies", label: "Backtesting", icon: TargetIcon, tone: "#0f766e" },
  { to: "/cup-breakout", label: "Cup Breakout", icon: SectorIcon, tone: "#ca8a04" },
  { to: "/value-buy", label: "Value Buy", icon: ValueTagIcon, tone: "#0d9488" },
  { to: "/weekly-sectors", label: "Weekly Sectors", icon: TrendIcon, tone: "#16a34a" },
  { to: "/heatmap", label: "Heatmap", icon: HeatmapIcon, tone: "#65a30d" },
  { to: "/range-analysis", label: "Range Analysis", icon: ChartBarIcon, tone: "#0891b2" },
  { to: "/ratio-charts", label: "Ratio Charts", icon: AngleIcon, tone: "#155e75" },
  { to: "/top-bottom", label: "Top Bottom Backtesting", icon: TrendIcon, tone: "#ea580c" },
  { to: "/breakout-15", label: "15-Min Breakout", icon: TrendIcon, tone: "#0284c7" },
  { to: "/gann-time", label: "Gann Square", icon: CalendarIcon, tone: "#0f5e9c" },
  { to: "/gann-angles", label: "Angle Projection", icon: AngleIcon, tone: "#4f46e5" },
  { to: "/anniversary-dates", label: "Anniversary Dates", icon: HistoryIcon, tone: "#b45309" },
  { to: "/astro-watch", label: "Astro Watch", icon: StarIcon, tone: "#d97706" },
  { to: "/stocks", label: "Stock Scanner", icon: ListIcon, tone: "#16a34a" },
  { to: "/history", label: "Scan History", icon: HistoryIcon, tone: "#059669" },
  { to: "/settings", label: "Settings", icon: SettingsIcon, tone: "#475b8a" },
];

const SUB_PAGES: Record<string, string> = {
  "/strategies/system-one": "System One",
  "/strategies/gfs": "GFS",
  "/strategies/advanced-gfs": "Advanced GFS",
  "/strategies/gfs-50": "50 GFS",
};

/** Breadcrumb for the top bar, e.g. ["Top Bottom Backtesting"] or ["Backtesting", "GFS", "All Stocks"]. */
export function navTrail(pathname: string): string[] {
  const path = pathname.replace(/\/+$/, "") || "/";
  for (const item of NAV_ITEMS) {
    const hit = item.to === "/" ? path === "/" : path === item.to || path.startsWith(item.to + "/");
    if (!hit) continue;
    const trail = [item.label];
    const sub = Object.keys(SUB_PAGES).find((p) => path === p || path.startsWith(p + "/"));
    if (sub) trail.push(SUB_PAGES[sub]);
    if (sub && path.endsWith("/stocks")) trail.push("All Stocks");
    return trail;
  }
  return [];
}

/**
 * On desktop this is the always-visible left rail. On mobile (see the `.app-sidebar` responsive rules) it
 * becomes an off-canvas panel toggled by the hamburger button in Header — `open`/`onClose` are only
 * meaningful there; desktop ignores them.
 */
export function Sidebar({ open, onClose }: { open?: boolean; onClose?: () => void }) {
  const navigate = useNavigate();
  return (
    <>
      {open && <div className="sidebar-backdrop" onClick={onClose} aria-hidden="true" />}
      <aside className={open ? "app-sidebar open" : "app-sidebar"}>
        <div className="sidebar-brand">
          <img src="/logo-mark.png" alt="" className="brand-mark" width={36} height={36} />
          <span className="brand-name">Scanner</span>
          <span className="brand-tag">NSE strategy scanner</span>
        </div>
        <nav className="sidebar-nav" aria-label="Main">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => (isActive ? "sidebar-link active" : "sidebar-link")}
                style={{ "--tone": item.tone } as React.CSSProperties}
                onClick={(e) => {
                  onClose?.();
                  navigateSmoothly(e, navigate, item.to);
                }}
              >
                <span className="nav-tile">
                  <Icon />
                </span>
                <span className="nav-label">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <span className="sidebar-foot-dot" />
          NSE · BSE · MCX
        </div>
      </aside>
    </>
  );
}

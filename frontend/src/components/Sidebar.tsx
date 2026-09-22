import { NavLink } from "react-router-dom";
import {
  BellIcon,
  CalendarIcon,
  DashboardIcon,
  HistoryIcon,
  ListIcon,
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
      </aside>
    </>
  );
}

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

export function Sidebar() {
  return (
    <aside className="app-sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-brand-icon">
          <TrendIcon width={17} height={17} />
        </span>
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
            >
              <Icon />
              {item.label}
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}

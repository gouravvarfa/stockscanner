import { NavLink, useNavigate } from "react-router-dom";
import { navigateSmoothly } from "../services/pageTransition";
import { DashboardIcon, HistoryIcon, SettingsIcon, TargetIcon } from "./icons";

// Exactly the 4 primary destinations, per the mobile design spec — every
// other page (TradingView Signals, Top Bottom
// Backtesting, the raw A Group Scanner list) stays reachable through the
// hamburger menu / sidebar, not crowded into the bottom bar.
const BOTTOM_NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true, icon: DashboardIcon },
  { to: "/strategies", label: "Strategies", icon: TargetIcon },
  { to: "/history", label: "Scan History", icon: HistoryIcon },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

/** Mobile-only fixed bottom navigation (hidden on desktop via CSS). */
export function BottomNav() {
  const navigate = useNavigate();
  return (
    <nav className="bottom-nav" aria-label="Primary">
      {BOTTOM_NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => (isActive ? "bottom-nav-link active" : "bottom-nav-link")}
            onClick={(e) => navigateSmoothly(e, navigate, item.to)}
          >
            <Icon width={20} height={20} />
            <span>{item.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}

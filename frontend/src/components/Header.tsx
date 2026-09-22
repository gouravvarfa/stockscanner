import { useEffect, useState } from "react";
import { useScan } from "../context/ScanContext";
import { BellIcon, ListIcon, MenuIcon, MoonIcon, SunIcon, UserIcon } from "./icons";

const IST_OFFSET_MINUTES = 5.5 * 60;

function getIstNow(): Date {
  const now = new Date();
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
  return new Date(utcMs + IST_OFFSET_MINUTES * 60000);
}

// NSE cash-market hours: 09:15-15:30 IST, Monday-Friday. A simple, honest
// computation from the real current time — not a live feed of holidays, so
// it can be wrong on exchange holidays, but never fabricates a status.
function isMarketOpen(ist: Date): boolean {
  const day = ist.getDay();
  if (day === 0 || day === 6) return false;
  const minutes = ist.getHours() * 60 + ist.getMinutes();
  return minutes >= 9 * 60 + 15 && minutes <= 15 * 60 + 30;
}

function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    try {
      return (localStorage.getItem("scanner-theme") as "light" | "dark") ?? "light";
    } catch {
      return "light";
    }
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("scanner-theme", theme);
    } catch {
      /* private browsing / storage blocked — theme just won't persist */
    }
  }, [theme]);

  return { theme, toggle: () => setTheme((t) => (t === "light" ? "dark" : "light")) };
}

export function Header({
  onToggleLogs,
  logsOpen,
  onToggleSidebar,
}: {
  onToggleLogs: () => void;
  logsOpen: boolean;
  onToggleSidebar: () => void;
}) {
  const [ist, setIst] = useState(getIstNow());
  const { theme, toggle } = useTheme();
  const { scanning } = useScan();

  useEffect(() => {
    const id = setInterval(() => setIst(getIstNow()), 30_000);
    return () => clearInterval(id);
  }, []);

  const open = isMarketOpen(ist);
  const timeLabel = ist.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });

  return (
    <header className="app-header">
      <div className="header-left">
        <button className="icon-button hamburger-button" onClick={onToggleSidebar} title="Menu" aria-label="Open menu">
          <MenuIcon width={18} height={18} />
        </button>
        <span className="header-brand-mobile">A Group Scanner</span>
        {scanning && (
          <span className="scanning-indicator">
            <span className="spinner" />
            Scanning A Group…
          </span>
        )}
      </div>
      <div className="header-right">
        <div className="market-status">
          <span className={open ? "dot" : "dot closed"} />
          <span>{open ? "Market Open" : "Market Closed"}</span>
          <span className="time">{timeLabel} (IST)</span>
        </div>
        <button
          className={logsOpen ? "icon-button active header-desktop-only" : "icon-button header-desktop-only"}
          onClick={onToggleLogs}
          title="Live logs"
          aria-label="Toggle live logs panel"
        >
          <ListIcon width={16} height={16} />
        </button>
        <button
          className="icon-button header-desktop-only"
          onClick={toggle}
          title="Toggle theme"
          aria-label="Toggle theme"
        >
          {theme === "light" ? <MoonIcon width={16} height={16} /> : <SunIcon width={16} height={16} />}
        </button>
        <button className="icon-button header-desktop-only" title="Notifications" aria-label="Notifications">
          <BellIcon width={16} height={16} />
        </button>
        <button className="icon-button header-desktop-only" title="Account" aria-label="Account">
          <UserIcon width={16} height={16} />
        </button>
      </div>
    </header>
  );
}

import { NavLink, Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { SectorScanner } from "./pages/SectorScanner";
import { StockScanner } from "./pages/StockScanner";
import { Strategies } from "./pages/Strategies";
import { ExpiryLevel1 } from "./pages/ExpiryLevel1";
import { ExpiryLevel5 } from "./pages/ExpiryLevel5";
import { ScanHistoryPage } from "./pages/ScanHistoryPage";
import { Settings } from "./pages/Settings";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/strategies", label: "Strategies" },
  { to: "/expiry-level-1", label: "Expiry Level 1" },
  { to: "/expiry-level-5", label: "Expiry Level 5" },
  { to: "/sectors", label: "Sector Scanner" },
  { to: "/stocks", label: "NIFTY 200 Scanner" },
  { to: "/history", label: "Scan History" },
  { to: "/settings", label: "Settings" },
];

export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">NIFTY 200 Scanner</div>
        <nav>
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/strategies" element={<Strategies />} />
          <Route path="/expiry-level-1" element={<ExpiryLevel1 />} />
          <Route path="/expiry-level-5" element={<ExpiryLevel5 />} />
          <Route path="/sectors" element={<SectorScanner />} />
          <Route path="/stocks" element={<StockScanner />} />
          <Route path="/history" element={<ScanHistoryPage />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}

import { Route, Routes } from "react-router-dom";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { Dashboard } from "./pages/Dashboard";
import { SectorScanner } from "./pages/SectorScanner";
import { StockScanner } from "./pages/StockScanner";
import { Strategies } from "./pages/Strategies";
import { ExpiryLevel1 } from "./pages/ExpiryLevel1";
import { ExpiryLevel5 } from "./pages/ExpiryLevel5";
import { ScanHistoryPage } from "./pages/ScanHistoryPage";
import { Settings } from "./pages/Settings";
import { TradingViewSignals } from "./pages/TradingViewSignals";

export default function App() {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <Header />
        <main className="app-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/strategies" element={<Strategies />} />
            <Route path="/expiry-level-1" element={<ExpiryLevel1 />} />
            <Route path="/expiry-level-5" element={<ExpiryLevel5 />} />
            <Route path="/sectors" element={<SectorScanner />} />
            <Route path="/stocks" element={<StockScanner />} />
            <Route path="/history" element={<ScanHistoryPage />} />
            <Route path="/tradingview" element={<TradingViewSignals />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

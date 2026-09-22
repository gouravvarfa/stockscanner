import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { ChartDrawer } from "./chart/ChartDrawer";
import { useChart } from "./chart/ChartContext";
import { ActiveScansPanel } from "./components/ActiveScansPanel";
import { BottomNav } from "./components/BottomNav";
import { Header } from "./components/Header";
import { LogsPanel } from "./components/LogsPanel";
import { Sidebar } from "./components/Sidebar";
import { Dashboard } from "./pages/Dashboard";
import { StockScanner } from "./pages/StockScanner";
import { Strategies } from "./pages/Strategies";
import { ExpiryLevel1 } from "./pages/ExpiryLevel1";
import { ExpiryLevel5 } from "./pages/ExpiryLevel5";
import { ScanHistoryPage } from "./pages/ScanHistoryPage";
import { Settings } from "./pages/Settings";
import { TradingViewSignals } from "./pages/TradingViewSignals";
import { TopBottomBacktest } from "./pages/TopBottomBacktest";
import { TopBottomErrorBoundary } from "./pages/topBottom/TopBottomErrorBoundary";

export default function App() {
  const [logsOpen, setLogsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const chart = useChart();

  return (
    <div className="app-shell">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="app-main">
        <Header
          onToggleLogs={() => setLogsOpen((v) => !v)}
          logsOpen={logsOpen}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
        />
        <main className="app-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/strategies" element={<Strategies />} />
            <Route path="/expiry-level-1" element={<ExpiryLevel1 />} />
            <Route path="/expiry-level-5" element={<ExpiryLevel5 />} />
            <Route path="/stocks" element={<StockScanner />} />
            <Route path="/history" element={<ScanHistoryPage />} />
            <Route path="/tradingview" element={<TradingViewSignals />} />
            <Route
              path="/top-bottom"
              element={
                <TopBottomErrorBoundary>
                  <TopBottomBacktest />
                </TopBottomErrorBoundary>
              }
            />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
      <LogsPanel open={logsOpen} onClose={() => setLogsOpen(false)} />
      <ChartDrawer state={chart.state} onToggleMaximize={chart.toggleMaximize} onClose={chart.closeChart} />
      <ActiveScansPanel />
      <BottomNav />
    </div>
  );
}

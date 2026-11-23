import { useEffect, useState } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ChartDrawer } from "./chart/ChartDrawer";
import { useChart } from "./chart/ChartContext";
import { ActiveScansPanel } from "./components/ActiveScansPanel";
import { BottomNav } from "./components/BottomNav";
import { Header } from "./components/Header";
import { LogsPanel } from "./components/LogsPanel";
import { Sidebar } from "./components/Sidebar";
import { Dashboard } from "./pages/Dashboard";
import { GFSUniversePage } from "./pages/GFSUniversePage";
import { GannTimePage } from "./pages/GannTimePage";
import { GannAnglesPage } from "./pages/GannAnglesPage";
import { AnniversaryPage } from "./pages/AnniversaryPage";
import { ThrustCheckPage } from "./pages/ThrustCheckPage";
import { StockScanner } from "./pages/StockScanner";
import { Strategies } from "./pages/Strategies";
import { SystemOneBacktestPage } from "./pages/SystemOneBacktestPage";
import { GFSBacktestPage } from "./pages/GFSBacktestPage";
import { CupBreakoutPage } from "./pages/CupBreakoutPage";
import { Breakout15Page } from "./pages/Breakout15Page";
import { RangeAnalysisPage } from "./pages/RangeAnalysisPage";
import { WeeklySectorsPage } from "./pages/WeeklySectorsPage";
import { ValueBuyPage } from "./pages/ValueBuyPage";
import { HeatmapPage } from "./pages/HeatmapPage";
import { AstroWatchPage } from "./pages/AstroWatchPage";
import { ScanHistoryPage } from "./pages/ScanHistoryPage";
import { Settings } from "./pages/Settings";
import { TopBottomBacktest } from "./pages/TopBottomBacktest";
import { TopBottomErrorBoundary } from "./pages/topBottom/TopBottomErrorBoundary";
import { startAutoConnect } from "./services/angeloneAutoConnect";
import { useAutoUpdate } from "./hooks/useAutoUpdate";

export default function App() {
  const [logsOpen, setLogsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const chart = useChart();

  // A new deploy reloads the open app by itself (hooks/useAutoUpdate.ts).
  const updating = useAutoUpdate();

  // Wake the backend and reconnect Angel One as soon as the app opens (see angeloneAutoConnect.ts).
  useEffect(() => startAutoConnect(), []);

  // A link with ?chart=SYMBOL (the Weekly Sectors PDF's stock and sector links) opens that chart right here, in the
  // app's own chart drawer, with RSI, volume and Bollinger Bands on; the parameter is then removed from the address.
  const location = useLocation();
  const navigate = useNavigate();
  const { openChart } = chart;
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const symbol = params.get("chart")?.trim();
    if (!symbol) return;
    openChart(symbol.toUpperCase(), {
      strategy: "Weekly Sectors",
      daily_rsi: null,
      weekly_rsi: null,
      monthly_rsi: null,
      signal_date: null,
      indicators: { rsi: true, volume: true, bollinger: true },
    });
    params.delete("chart");
    const rest = params.toString();
    navigate({ pathname: location.pathname, search: rest ? `?${rest}` : "" }, { replace: true });
  }, [location.pathname, location.search, navigate, openChart]);

  return (
    <div className="app-shell">
      {updating && <div className="update-toast" role="status">Updating to the new version…</div>}
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
            <Route path="/strategies/system-one" element={<SystemOneBacktestPage />} />
            <Route path="/strategies/gfs" element={<GFSBacktestPage />} />
            <Route path="/strategies/advanced-gfs" element={<GFSBacktestPage variant="advanced" />} />
            <Route path="/strategies/gfs-50" element={<GFSBacktestPage variant="gfs50" />} />
            <Route path="/strategies/gfs/stocks" element={<GFSUniversePage variant="gfs" />} />
            <Route path="/strategies/advanced-gfs/stocks" element={<GFSUniversePage variant="advanced" />} />
            <Route path="/strategies/gfs-50/stocks" element={<GFSUniversePage variant="gfs50" />} />
            <Route path="/cup-breakout" element={<CupBreakoutPage />} />
            <Route path="/gann-time" element={<GannTimePage />} />
            <Route path="/gann-angles" element={<GannAnglesPage />} />
            <Route path="/anniversary-dates" element={<AnniversaryPage />} />
            <Route path="/thrust-check" element={<ThrustCheckPage />} />
            <Route path="/stocks" element={<StockScanner />} />
            <Route path="/breakout-15" element={<Breakout15Page />} />
            <Route path="/range-analysis" element={<RangeAnalysisPage />} />
            <Route path="/weekly-sectors" element={<WeeklySectorsPage />} />
            <Route path="/value-buy" element={<ValueBuyPage />} />
            <Route path="/heatmap" element={<HeatmapPage />} />
            <Route path="/astro-watch" element={<AstroWatchPage />} />
            <Route path="/history" element={<ScanHistoryPage />} />
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

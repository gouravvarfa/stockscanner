import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import './design.css'
import App from './App.tsx'
import { ScanProvider } from './context/ScanContext'
import { ChartProvider } from './chart/ChartContext'
import { WeeklyReportProvider } from './context/WeeklyReportContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ScanProvider>
        <WeeklyReportProvider>
          <ChartProvider>
            <App />
          </ChartProvider>
        </WeeklyReportProvider>
      </ScanProvider>
    </BrowserRouter>
  </StrictMode>,
)

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { ScanProvider } from './context/ScanContext'
import { ChartProvider } from './chart/ChartContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ScanProvider>
        <ChartProvider>
          <App />
        </ChartProvider>
      </ScanProvider>
    </BrowserRouter>
  </StrictMode>,
)

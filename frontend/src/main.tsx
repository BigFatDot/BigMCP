import React, { Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { queryClient } from './lib/queryClient'
import './index.css'
import './i18n' // i18n initialization — lazy loading via HTTP backend

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        {/* Suspense: holds render until active language JSON files are fetched */}
        <Suspense fallback={<div style={{ display: 'none' }} />}>
          <App />
        </Suspense>
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
)

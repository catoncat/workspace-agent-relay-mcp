import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import './index.css'
import { applyThemeSettings, loadThemeSettings } from '@/lib/themePresets'
import { AppProviders } from '@/providers/AppProviders'
import { router } from '@/router'

applyThemeSettings(loadThemeSettings())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
)

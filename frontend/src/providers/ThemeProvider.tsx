import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  applyThemeSettings,
  loadThemeSettings,
  resolveDark,
  type ColorMode,
  type ThemePreset,
  type ThemeSettings,
} from '@/lib/themePresets'

type ThemeContextValue = ThemeSettings & {
  resolvedTheme: 'light' | 'dark'
  setMode: (mode: ColorMode) => void
  setPreset: (preset: ThemePreset) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

const initialSettings = loadThemeSettings()

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<ThemeSettings>(initialSettings)
  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>(() =>
    resolveDark(initialSettings.mode) ? 'dark' : 'light',
  )

  useEffect(() => {
    applyThemeSettings(settings)
    setResolvedTheme(resolveDark(settings.mode) ? 'dark' : 'light')
  }, [settings])

  useEffect(() => {
    if (settings.mode !== 'system') return
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = () => {
      applyThemeSettings(settings)
      setResolvedTheme(media.matches ? 'dark' : 'light')
    }
    media.addEventListener('change', handleChange)
    return () => media.removeEventListener('change', handleChange)
  }, [settings])

  const setMode = useCallback((mode: ColorMode) => {
    setSettings((current) => ({ ...current, mode }))
  }, [])

  const setPreset = useCallback((preset: ThemePreset) => {
    setSettings((current) => ({ ...current, preset }))
  }, [])

  const value = useMemo(
    () => ({
      ...settings,
      resolvedTheme,
      setMode,
      setPreset,
    }),
    [settings, resolvedTheme, setMode, setPreset],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider')
  }
  return context
}

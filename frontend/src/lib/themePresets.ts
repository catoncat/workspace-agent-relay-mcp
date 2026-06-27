export type ThemePreset = 'default' | 'neutral' | 'blue' | 'green' | 'violet'

export type ColorMode = 'light' | 'dark' | 'system'

export type ThemeSettings = {
  mode: ColorMode
  preset: ThemePreset
}

export const THEME_STORAGE_KEY = 'relay-theme-settings'

export const THEME_PRESETS: Array<{
  id: ThemePreset
  label: string
  swatch: string
}> = [
  { id: 'default', label: 'Orange', swatch: 'oklch(0.553 0.195 38.402)' },
  { id: 'neutral', label: 'Neutral', swatch: 'oklch(0.45 0 0)' },
  { id: 'blue', label: 'Blue', swatch: 'oklch(0.55 0.18 250)' },
  { id: 'green', label: 'Green', swatch: 'oklch(0.55 0.15 145)' },
  { id: 'violet', label: 'Violet', swatch: 'oklch(0.55 0.18 290)' },
]

export const COLOR_MODES: Array<{ id: ColorMode; label: string }> = [
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
  { id: 'system', label: 'System' },
]

export function loadThemeSettings(): ThemeSettings {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ThemeSettings>
      const mode = parsed.mode
      const preset = parsed.preset
      if (
        (mode === 'light' || mode === 'dark' || mode === 'system') &&
        THEME_PRESETS.some((item) => item.id === preset)
      ) {
        return { mode, preset: preset as ThemePreset }
      }
    }
  } catch {
    // ignore malformed storage
  }

  const legacy = localStorage.getItem('relay-theme')
  if (legacy === 'light' || legacy === 'dark') {
    return { mode: legacy, preset: 'default' }
  }

  return {
    mode: window.matchMedia('(prefers-color-scheme: dark)').matches ? 'system' : 'system',
    preset: 'default',
  }
}

export function resolveDark(mode: ColorMode): boolean {
  if (mode === 'dark') return true
  if (mode === 'light') return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function applyThemeSettings({ mode, preset }: ThemeSettings): void {
  const root = document.documentElement
  root.classList.toggle('dark', resolveDark(mode))
  if (preset === 'default') {
    root.removeAttribute('data-preset')
  } else {
    root.dataset.preset = preset
  }
  localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify({ mode, preset }))
}

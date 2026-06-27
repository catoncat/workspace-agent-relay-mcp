import { Check, Monitor, Moon, Palette, Sun } from 'lucide-react'
import { buttonVariants } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { COLOR_MODES, THEME_PRESETS, type ColorMode } from '@/lib/themePresets'
import { useTheme } from '@/providers/ThemeProvider'
import { cn } from '@/lib/utils'

export const sidebarHeaderIconClass =
  'size-7 shrink-0 text-muted-foreground hover:text-foreground'

export function ThemeMenu() {
  const { mode, preset, setMode, setPreset } = useTheme()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(buttonVariants({ variant: 'ghost', size: 'icon-sm' }), sidebarHeaderIconClass)}
        title="Theme"
      >
        <Palette className="size-3.5" />
        <span className="sr-only">Theme settings</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <p className="px-2 py-1 text-[11px] font-medium text-muted-foreground">Appearance</p>
        {COLOR_MODES.map((item) => (
          <DropdownMenuItem key={item.id} onClick={() => setMode(item.id)}>
            <ModeIcon mode={item.id} />
            <span className="flex-1">{item.label}</span>
            {mode === item.id ? <Check className="size-3.5 opacity-70" /> : null}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <p className="px-2 py-1 text-[11px] font-medium text-muted-foreground">Accent</p>
        {THEME_PRESETS.map((item) => (
          <DropdownMenuItem key={item.id} onClick={() => setPreset(item.id)}>
            <span
              className="size-3.5 shrink-0 rounded-full ring-1 ring-border/60"
              style={{ backgroundColor: item.swatch }}
              aria-hidden
            />
            <span className="flex-1">{item.label}</span>
            {preset === item.id ? <Check className="size-3.5 opacity-70" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function ModeIcon({ mode }: { mode: ColorMode }) {
  if (mode === 'system') return <Monitor className="size-3.5 opacity-70" />
  if (mode === 'dark') return <Moon className="size-3.5 opacity-70" />
  return <Sun className="size-3.5 opacity-70" />
}

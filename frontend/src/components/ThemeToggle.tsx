import type { ComponentProps } from 'react'
import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTheme } from '@/hooks/useTheme'

type ThemeToggleProps = Pick<ComponentProps<typeof Button>, 'size'>

export function ThemeToggle({ size = 'icon' }: ThemeToggleProps = {}) {
  const { theme, toggleTheme } = useTheme()
  return (
    <Button variant="ghost" size={size} onClick={toggleTheme} title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
      {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  )
}

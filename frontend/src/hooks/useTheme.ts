import { useCallback, useSyncExternalStore } from 'react'
import { deriveTheme, isHex } from '../utils/colour'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'portal-theme'
const ACCENT_KEY = 'portal-accent'
const ACCENT_VARS_KEY = 'portal-accent-vars'
const CUSTOM_VARS = ['--brand', '--brand-hover', '--brand-rgb', '--brand-light', '--brand-2']

function stored(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null // storage can be blocked; the theme then simply isn't remembered
  }
}

function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#161c29' : '#ffffff')
}

// One shared value for the whole app, so the top-bar switch and the Profile
// settings always agree.
let current: Theme = stored() ?? systemTheme()
const listeners = new Set<() => void>()

function set(theme: Theme, remember: boolean) {
  current = theme
  apply(theme)
  if (remember) {
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // not remembered; still applies for this visit
    }
  }
  listeners.forEach((listener) => listener())
}

// Keep following the device while no explicit choice has been made.
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (!stored()) set(systemTheme(), false)
})

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/**
 * Light or dark appearance. Follows the device setting until the person chooses,
 * then remembers their choice on this device. (index.html applies the same rule
 * before the app loads, so there is no flash of the wrong theme.)
 */
export function useTheme() {
  const theme = useSyncExternalStore(subscribe, () => current)
  const setTheme = useCallback((next: Theme) => set(next, true), [])
  const toggle = useCallback(() => set(current === 'dark' ? 'light' : 'dark', true), [])
  return { theme, toggle, setTheme }
}

/**
 * Apply a colour theme ('' is the default). The choice is saved on the person's
 * account; it is also cached on this device so the next visit starts in the right
 * colours before the account has loaded.
 */
export function applyAccent(id: string) {
  const root = document.documentElement
  // A colour of the person's own ("#rrggbb"): the theme's colours are worked out from it.
  const custom = isHex(id) ? deriveTheme(id).vars : null
  for (const name of CUSTOM_VARS) {
    if (custom) root.style.setProperty(name, custom[name])
    else root.style.removeProperty(name)
  }
  if (id) root.dataset.accent = custom ? 'custom' : id
  else delete root.dataset.accent
  try {
    if (id) localStorage.setItem(ACCENT_KEY, id)
    else localStorage.removeItem(ACCENT_KEY)
    // index.html reads these before the app loads, so there is no flash of the default colours.
    if (custom) localStorage.setItem(ACCENT_VARS_KEY, JSON.stringify(custom))
    else localStorage.removeItem(ACCENT_VARS_KEY)
  } catch {
    // not cached; the account still remembers it
  }
}

/**
 * Apply the display settings a person chose: layout density and animations. Cached on
 * this device like the colour theme, so the next visit starts the right way.
 */
export function applyDisplay(density: string, motion: string) {
  const root = document.documentElement
  if (density === 'compact' || density === 'comfortable') root.dataset.density = density
  else delete root.dataset.density
  if (motion === 'off') root.dataset.motion = 'off'
  else delete root.dataset.motion
  try {
    localStorage.setItem('portal-density', density)
    localStorage.setItem('portal-motion', motion)
  } catch {
    // not cached; the account still remembers it
  }
}

/** Remove the colour theme from the page without forgetting it (used on the sign-in page). */
export function clearAccent() {
  delete document.documentElement.dataset.accent
  for (const name of CUSTOM_VARS) document.documentElement.style.removeProperty(name)
}

/** Colour arithmetic for a person's own theme colour (Settings → Appearance → Custom). */

export type Rgb = [number, number, number]

export const isHex = (value: string) => /^#[0-9a-f]{6}$/i.test(value)

export function hexToRgb(hex: string): Rgb {
  const n = parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

export function rgbToHex([r, g, b]: Rgb): string {
  return `#${[r, g, b].map((v) => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0')).join('')}`
}

/** h in degrees, s and v from 0 to 1. */
export function hsvToRgb(h: number, s: number, v: number): Rgb {
  const f = (n: number) => {
    const k = (n + h / 60) % 6
    return (v - v * s * Math.max(0, Math.min(k, 4 - k, 1))) * 255
  }
  return [f(5), f(3), f(1)]
}

export function rgbToHsv([r, g, b]: Rgb): [number, number, number] {
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const d = max - min
  let h = 0
  if (d) {
    if (max === r) h = ((g - b) / d) % 6
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
  }
  return [(h * 60 + 360) % 360, max ? d / max : 0, max / 255]
}

const mix = (a: Rgb, b: Rgb, amount: number): Rgb => [0, 1, 2].map((i) => a[i] + (b[i] - a[i]) * amount) as Rgb

function luminance(rgb: Rgb): number {
  const [r, g, b] = rgb.map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const WHITE: Rgb = [255, 255, 255]
const BLACK: Rgb = [0, 0, 0]
const DARK_SURFACE: Rgb = [22, 28, 41]

/** Darken until white text is readable on it (the WCAG 4.5:1 level, with a little margin). */
function readableUnderWhite(rgb: Rgb): Rgb {
  let colour = rgb
  for (let i = 0; i < 40 && contrast(colour, WHITE) < 4.6; i++) colour = mix(colour, BLACK, 0.06)
  return colour
}

/**
 * The five colours a theme needs (see styles/themes.css), worked out from one chosen colour.
 * `adjusted` says the colour had to be darkened so that button text stays readable.
 */
export function deriveTheme(hex: string) {
  const picked = hexToRgb(hex)
  const brand = readableUnderWhite(picked)
  let light = mix(brand, WHITE, 0.55)
  for (let i = 0; i < 20 && contrast(light, DARK_SURFACE) < 6; i++) light = mix(light, WHITE, 0.1)
  const [h, s, v] = rgbToHsv(brand)
  const second = readableUnderWhite(hsvToRgb((h + 38) % 360, Math.max(s, 0.45), Math.max(v, 0.55)))
  return {
    adjusted: rgbToHex(brand) !== rgbToHex(picked),
    vars: {
      '--brand': rgbToHex(brand),
      '--brand-hover': rgbToHex(mix(brand, BLACK, 0.14)),
      '--brand-rgb': brand.map(Math.round).join(', '),
      '--brand-light': rgbToHex(light),
      '--brand-2': rgbToHex(second),
    } as Record<string, string>,
  }
}

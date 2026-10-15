/**
 * Colour themes a person can choose under Profile → Settings. The colours themselves
 * live in styles/themes.css; the two given here only paint the picker's swatches.
 * The ids must match the list the server accepts (apps/users/models.py).
 */
export interface ColourTheme {
  /** '' is the default theme, which sets no attribute. */
  id: string
  name: string
  brand: string
  brand2: string
}

export const THEMES: ColourTheme[] = [
  { id: '', name: 'Ocean', brand: '#2160e0', brand2: '#14a391' },
  { id: 'indigo', name: 'Indigo', brand: '#4f46e5', brand2: '#7c3aed' },
  { id: 'violet', name: 'Violet', brand: '#7c3aed', brand2: '#db2777' },
  { id: 'plum', name: 'Plum', brand: '#9d2f9a', brand2: '#4f46e5' },
  { id: 'rose', name: 'Rose', brand: '#c01763', brand2: '#e0672a' },
  { id: 'crimson', name: 'Crimson', brand: '#c81e3a', brand2: '#d9631e' },
  { id: 'sunset', name: 'Sunset', brand: '#b23a0a', brand2: '#c01763' },
  { id: 'amber', name: 'Amber', brand: '#a34a07', brand2: '#b23a0a' },
  { id: 'olive', name: 'Olive', brand: '#44700c', brand2: '#0f766e' },
  { id: 'forest', name: 'Forest', brand: '#127237', brand2: '#0e7490' },
  { id: 'teal', name: 'Teal', brand: '#0f766e', brand2: '#2160e0' },
  { id: 'sky', name: 'Sky', brand: '#0369a1', brand2: '#0f766e' },
  { id: 'navy', name: 'Navy', brand: '#1e3a8a', brand2: '#2160e0' },
  { id: 'graphite', name: 'Graphite', brand: '#475569', brand2: '#0f766e' },
  { id: 'bronze', name: 'Bronze', brand: '#92562a', brand2: '#a34a07' },
]

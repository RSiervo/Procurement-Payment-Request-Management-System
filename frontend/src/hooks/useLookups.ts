import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { lookupsApi } from '../api/misc'
import { setCurrencySymbol } from '../utils/format'

/** Reference data (request types, departments, categories, config), cached for the session. */
export function useLookups() {
  const query = useQuery({ queryKey: ['lookups'], queryFn: lookupsApi.get, staleTime: 10 * 60_000 })
  useEffect(() => {
    if (query.data) setCurrencySymbol(query.data.config.currency_symbol)
  }, [query.data])
  return query.data
}

export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const media = window.matchMedia(query)
    const update = () => setMatches(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [query])
  return matches
}

export const useIsDesktop = () => useMediaQuery('(min-width: 900px)')

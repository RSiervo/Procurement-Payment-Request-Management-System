import { useEffect, useRef, useState } from 'react'

const DURATION_MS = 700

/**
 * A whole number that counts up to its value when it first appears, and glides to
 * the new value when it changes. Anything that is not a whole number (a placeholder
 * dash, formatted money) is shown as-is. No animation for people who prefer reduced motion.
 */
export function CountUp({ value }: { value: number | string }) {
  const target = typeof value === 'number' && Number.isInteger(value) ? value : null
  const [shown, setShown] = useState(0)
  const from = useRef(0)

  useEffect(() => {
    if (target === null) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.dataset.motion === 'off'
    if (reduce || target === from.current) {
      from.current = target
      setShown(target)
      return
    }
    const start = from.current
    const began = performance.now()
    let frame = 0
    const tick = (now: number) => {
      const progress = Math.min((now - began) / DURATION_MS, 1)
      const eased = 1 - Math.pow(1 - progress, 3) // fast at first, settling gently
      setShown(Math.round(start + (target - start) * eased))
      if (progress < 1) frame = requestAnimationFrame(tick)
      else from.current = target
    }
    frame = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(frame)
      from.current = target
    }
  }, [target])

  return <>{target === null ? value : shown}</>
}

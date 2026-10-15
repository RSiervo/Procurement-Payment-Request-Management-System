import { AlertCircle, CheckCircle2 } from 'lucide-react'
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '../api/client'

interface ToastItem {
  id: number
  message: string
  kind: 'success' | 'error'
}

interface ToastValue {
  success: (message: string) => void
  error: (error: unknown, fallback?: string) => void
}

const ToastContext = createContext<ToastValue | null>(null)

export function errorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (error instanceof ApiError) return error.message
  return fallback
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const push = useCallback((message: string, kind: ToastItem['kind']) => {
    const id = nextId.current++
    setItems((current) => [...current.slice(-2), { id, message, kind }])
    setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), kind === 'error' ? 7000 : 4000)
  }, [])

  const value = useMemo<ToastValue>(
    () => ({
      success: (message) => push(message, 'success'),
      error: (error, fallback) => push(errorMessage(error, fallback), 'error'),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((item) => (
          <div key={item.id} className={`toast ${item.kind === 'error' ? 'toast-error' : ''}`}>
            {item.kind === 'error' ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
            <span>{item.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastValue {
  const value = useContext(ToastContext)
  if (!value) throw new Error('useToast must be used inside ToastProvider')
  return value
}

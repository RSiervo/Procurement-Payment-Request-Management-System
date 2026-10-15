import { X } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Button } from './Button'

/** Shared behaviour: Escape closes, background scroll is locked, focus moves inside and returns after. */
function useOverlay(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    ref.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
      previous?.focus?.()
    }
    // Runs once: onClose may change identity every render, and the overlay only needs it while mounted.
  }, [])
  return ref
}

interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}

export function Modal({ title, onClose, children, footer, wide }: ModalProps) {
  const ref = useOverlay(onClose)
  return createPortal(
    <div className="overlay" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div ref={ref} className={`modal ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}>
        <div className="modal-header">
          <h2>{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}

export function Drawer({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  const ref = useOverlay(onClose)
  return createPortal(
    <div className="overlay drawer-overlay" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div ref={ref} className="drawer" role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}>
        {children}
      </div>
    </div>,
    document.body,
  )
}

interface ConfirmProps {
  title: string
  message: ReactNode
  confirmLabel: string
  danger?: boolean
  onConfirm: () => Promise<unknown> | void
  onClose: () => void
}

export function ConfirmationDialog({ title, message, confirmLabel, danger, onConfirm, onClose }: ConfirmProps) {
  const [busy, setBusy] = useState(false)
  const confirm = async () => {
    setBusy(true)
    try {
      await onConfirm()
      onClose()
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant={danger ? 'danger' : 'primary'} onClick={confirm} loading={busy}>{confirmLabel}</Button>
        </>
      }
    >
      <p className="secondary">{message}</p>
    </Modal>
  )
}

/** Button that toggles a small menu; closes on outside click, Escape, or choosing an item. */
export function Dropdown({ trigger, children, label, menuClassName = '', triggerClassName = 'icon-btn' }: {
  trigger: ReactNode
  children: ReactNode
  label: string
  menuClassName?: string
  triggerClassName?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent) => !ref.current?.contains(event.target as Node) && setOpen(false)
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <div className="dropdown" ref={ref}>
      <button type="button" className={triggerClassName} aria-haspopup="menu" aria-expanded={open} aria-label={label} onClick={() => setOpen((v) => !v)}>
        {trigger}
      </button>
      {open && (
        <div className={`dropdown-menu ${menuClassName}`} role="menu" onClick={() => setOpen(false)}>
          {children}
        </div>
      )}
    </div>
  )
}

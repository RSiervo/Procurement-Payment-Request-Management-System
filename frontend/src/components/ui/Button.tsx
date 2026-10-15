import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'

interface StyleProps {
  variant?: Variant
  size?: 'md' | 'sm'
  block?: boolean
  icon?: ReactNode
}

function classes({ variant = 'secondary', size = 'md', block }: StyleProps, extra = '') {
  return ['btn', `btn-${variant}`, size === 'sm' && 'btn-sm', block && 'btn-block', extra].filter(Boolean).join(' ')
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & StyleProps & { loading?: boolean }

export function Button({ variant, size, block, icon, loading, children, className, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      className={classes({ variant, size, block }, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className="spinner" aria-hidden /> : icon}
      {children}
    </button>
  )
}

export function ButtonLink({ variant, size, block, icon, children, className, ...rest }: LinkProps & StyleProps) {
  return (
    <Link className={classes({ variant, size, block }, className)} {...rest}>
      {icon}
      {children}
    </Link>
  )
}

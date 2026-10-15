import { useId } from 'react'

/**
 * The portal's own mark: a request form with its approval tick, on the system blue.
 * The form stands for the requisition or payment request; the tick for the sign-off
 * that moves it forward. Drawn inline so it stays sharp at any size.
 */
export function PortalLogo({ size = 56, className = '' }: { size?: number; className?: string }) {
  const id = useId()
  return (
    <svg className={`portal-logo ${className}`} width={size} height={size} viewBox="0 0 64 64" role="img"
         aria-label="Procurement & Payment Portal">
      <defs>
        <linearGradient id={`${id}-tile`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4a8bff" />
          <stop offset="0.55" stopColor="#2160e0" />
          <stop offset="1" stopColor="#143f9e" />
        </linearGradient>
        <linearGradient id={`${id}-sheen`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.28" />
          <stop offset="0.5" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`${id}-tick`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2ed3b5" />
          <stop offset="1" stopColor="#0d9488" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill={`url(#${id}-tile)`} />
      <rect width="64" height="64" rx="15" fill={`url(#${id}-sheen)`} />
      {/* the request form, with a folded corner */}
      <path d="M21 13h15.5L46 22.5V46a4 4 0 0 1-4 4H21a4 4 0 0 1-4-4V17a4 4 0 0 1 4-4z" fill="#fff" />
      <path d="M36.5 13v6a3.5 3.5 0 0 0 3.5 3.5h6z" fill="#c9dcff" />
      <rect className="portal-logo-line" x="22.5" y="28" width="15" height="3" rx="1.5" fill="#2160e0" />
      <rect className="portal-logo-line" x="22.5" y="34.5" width="15" height="3" rx="1.5" fill="#2160e0" opacity="0.7" />
      <rect className="portal-logo-line" x="22.5" y="41" width="8" height="3" rx="1.5" fill="#2160e0" opacity="0.45" />
      {/* the approval */}
      <g className="portal-logo-badge">
        <circle cx="45" cy="46" r="11.5" fill="#fff" />
        <circle cx="45" cy="46" r="9" fill={`url(#${id}-tick)`} />
        <path className="portal-logo-tick" pathLength={1} d="M40.6 46.2l3 3.1 5.8-6.3" fill="none" stroke="#fff"
              strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  )
}

import { Banknote, Check, ChevronRight, CornerUpLeft, FileText, Inbox, Minus, Receipt, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { CountUp } from './CountUp'
import type { NodeState, Priority, Status, TimelineNode } from '../../types'
import { formatDateTime, initials, PRIORITY_META, STATUS_META, type Tone } from '../../utils/format'

export function Card({ title, actions, children, flush, className = '' }: {
  title?: ReactNode
  actions?: ReactNode
  children: ReactNode
  flush?: boolean
  className?: string
}) {
  return (
    <section className={`card ${flush ? 'card-flush' : ''} ${className}`}>
      {(title || actions) && (
        <div className="card-header">
          <h2>{title}</h2>
          {actions}
        </div>
      )}
      <div className="card-body">{children}</div>
    </section>
  )
}

export function Badge({ tone = 'neutral', children, plain }: { tone?: Tone; children: ReactNode; plain?: boolean }) {
  return <span className={`badge badge-${tone} ${plain ? 'badge-plain' : ''}`}>{children}</span>
}

export function StatusBadge({ status }: { status: Status }) {
  const meta = STATUS_META[status]
  return <Badge tone={meta.tone} plain>{meta.label}</Badge>
}

export function PriorityBadge({ priority }: { priority: Priority }) {
  if (priority === 'NORMAL' || priority === 'LOW') return null
  const meta = PRIORITY_META[priority]
  return <Badge tone={meta.tone} plain>{meta.label}</Badge>
}

export function Avatar({ name }: { name: string }) {
  return <span className="avatar" aria-hidden>{initials(name)}</span>
}

export function EmptyState({ title, message, action, icon }: {
  title: string
  message?: string
  action?: ReactNode
  icon?: ReactNode
}) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon ?? <Inbox size={20} />}</div>
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action}
    </div>
  )
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" aria-hidden />
      {label}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <EmptyState
      title="Could not load this"
      message={message}
      action={onRetry && <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>Try again</button>}
    />
  )
}

const TYPE_SHORT: Record<string, string> = { PR: 'PR', RFP: 'RFP', REIM: 'Reim.', CA: 'Advance', LIQ: 'Liquid.' }

export type ChipTone = 'blue' | 'amber' | 'green' | 'purple' | 'red' | 'teal' | 'neutral'

/** Round tinted icon holder used on stat cards, quick actions and feeds. */
export function IconChip({ tone = 'blue', small, large, solid, children }: {
  tone?: ChipTone
  small?: boolean
  large?: boolean
  /** Filled with the tone colour and a white icon; used on headline cards. */
  solid?: boolean
  children: ReactNode
}) {
  const size = small ? 'icon-chip-sm' : large ? 'icon-chip-lg' : ''
  return <span className={`icon-chip ${size}`} data-tone={tone} data-solid={solid || undefined} aria-hidden>{children}</span>
}

const TYPE_ICON: Record<string, ReactNode> = {
  PR: <FileText size={16} />,
  RFP: <Banknote size={16} />,
  REIM: <Receipt size={16} />,
}

/** Request type as a small coloured tile with its short name, for tables. */
export function TypeTag({ code, name }: { code: string; name?: string }) {
  return (
    <span className="type-tag" data-type={code} title={name}>
      <span className="icon-chip">{TYPE_ICON[code] ?? <FileText size={16} />}</span>
      {TYPE_SHORT[code] ?? code}
    </span>
  )
}

export function TypePill({ code, name }: { code: string; name?: string }) {
  return <span className="type-pill" data-type={code} title={name}>{TYPE_SHORT[code] ?? code}</span>
}

interface StatProps {
  label: string
  value: number | string
  to?: string
  tone?: 'danger'
  icon?: ReactNode
  iconTone?: ChipTone
  pressed?: boolean
  onClick?: () => void
}

/** Summary number. Becomes a link or a filter toggle when given `to` or `onClick`. */
export function Stat({ label, value, to, tone, icon, iconTone, pressed, onClick }: StatProps) {
  const body = (
    <>
      {icon && <IconChip tone={iconTone}>{icon}</IconChip>}
      <span className="stat-body">
        <span className="stat-label">{label}</span>
        <span className="stat-value" data-tone={tone && Number(value) > 0 ? tone : undefined}><CountUp value={value} /></span>
      </span>
      {(to || onClick) && <ChevronRight className="stat-chevron" size={18} aria-hidden />}
    </>
  )
  if (to) return <Link className="stat" to={to}>{body}</Link>
  if (onClick) return <button type="button" className="stat" aria-pressed={pressed} onClick={onClick}>{body}</button>
  return <div className="stat">{body}</div>
}

export function Tabs<T extends string>({ tabs, value, onChange }: {
  tabs: { value: T; label: string; count?: number }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button key={tab.value} type="button" role="tab" className="tab" aria-selected={tab.value === value} onClick={() => onChange(tab.value)}>
          {tab.label}
          {tab.count !== undefined && tab.count > 0 && <span className="tab-count">{tab.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Stepper({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className="stepper" aria-label={`Step ${current + 1} of ${steps.length}: ${steps[current]}`}>
      {steps.map((step, index) => (
        <li key={step} className="stepper-step" data-state={index < current ? 'done' : index === current ? 'current' : 'upcoming'}>
          <span className="stepper-num">{index < current ? <Check size={14} strokeWidth={3} /> : index + 1}</span>
          <span className="stepper-label">{step}</span>
        </li>
      ))}
    </ol>
  )
}

const DOT_ICON: Partial<Record<NodeState, ReactNode>> = {
  done: <Check size={14} strokeWidth={3} />,
  rejected: <X size={14} strokeWidth={3} />,
  returned: <CornerUpLeft size={13} strokeWidth={3} />,
  skipped: <Minus size={14} />,
  cancelled: <Minus size={14} />,
}

export function Timeline({ nodes }: { nodes: TimelineNode[] }) {
  return (
    <ol className="timeline">
      {nodes.map((node) => (
        <li key={node.key} className="timeline-item" data-state={node.state}>
          <span className="timeline-dot" aria-hidden>
            {DOT_ICON[node.state] ?? (node.state === 'current' ? <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'currentColor' }} /> : null)}
          </span>
          <div>
            <div className="timeline-title">{node.label}</div>
            <div className="timeline-meta">
              {node.detail}
              {node.actor && ` · ${node.actor}`}
              {node.actor_position && `, ${node.actor_position}`}
            </div>
            {node.at && <div className="timeline-meta">{formatDateTime(node.at)}</div>}
            {node.notes.map((note) => (
              <div key={note.at} className="timeline-note">
                <span className="xs muted">{note.actor} asked · {formatDateTime(note.at)}</span>
                <div className="pre-wrap">{note.text}</div>
              </div>
            ))}
            {node.comments && <div className="timeline-note pre-wrap">{node.comments}</div>}
          </div>
        </li>
      ))}
    </ol>
  )
}

/** Horizontal bars for one measure across categories. Values are labelled, so colour is not the only cue. */
export function BarList({ rows, format = String }: {
  rows: { label: string; value: number; hint?: string }[]
  format?: (value: number) => string
}) {
  const max = Math.max(...rows.map((row) => row.value), 1)
  return (
    <div className="bar-list">
      {rows.map((row) => (
        <div key={row.label} className="bar-row" title={`${row.label}: ${format(row.value)}${row.hint ? ` (${row.hint})` : ''}`}>
          <span className="truncate">{row.label}</span>
          <span className="num strong">{format(row.value)}{row.hint && <span className="muted"> · {row.hint}</span>}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${(row.value / max) * 100}%` }} /></div>
        </div>
      ))}
    </div>
  )
}

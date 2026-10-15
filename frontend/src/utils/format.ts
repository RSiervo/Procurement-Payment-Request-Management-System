import type { Priority, Status } from '../types'

let currencySymbol = '₱'

export function setCurrencySymbol(symbol: string) {
  currencySymbol = symbol || '₱'
}

export function money(value: string | number | null | undefined): string {
  const amount = Number(value ?? 0)
  return `${currencySymbol}${amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** "2026-10-08" is a calendar date, not an instant: parse it as local so it never shifts a day. */
function toDate(value: string): Date {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value)
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  return toDate(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return toDate(value).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return ''
  return new Date(value).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

export function timeAgo(value: string | null | undefined): string {
  if (!value) return '—'
  const minutes = Math.round((Date.now() - new Date(value).getTime()) / 60_000)
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} hr ago`
  const days = Math.round(hours / 24)
  return days < 7 ? `${days} day${days === 1 ? '' : 's'} ago` : formatDate(value)
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function quantity(value: string | null | undefined): string {
  return value == null || value === '' ? '' : String(Number(value))
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}

export function todayIso(): string {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

export function greeting(): string {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
}

const TYPE_COLORS: Record<string, string> = {
  PR: 'var(--type-pr)', RFP: 'var(--type-rfp)', REIM: 'var(--type-reim)', CA: 'var(--type-ca)', LIQ: 'var(--type-liq)',
}

/** Identity colour of a request type, shared by the type pills and the dashboard charts. */
export function typeColor(code: string): string {
  return TYPE_COLORS[code] ?? 'var(--type-other)'
}

export type Tone ='neutral' | 'info' | 'warning' | 'success' | 'danger' | 'purple'

export const STATUS_META: Record<Status, { label: string; tone: Tone }> = {
  DRAFT: { label: 'Draft', tone: 'neutral' },
  PENDING_APPROVAL: { label: 'Pending Approval', tone: 'warning' },
  RETURNED: { label: 'Returned for Revision', tone: 'purple' },
  REJECTED: { label: 'Rejected', tone: 'danger' },
  APPROVED: { label: 'Approved', tone: 'info' },
  OPS_RECEIVED: { label: 'Received by OPS', tone: 'info' },
  PROCESSING: { label: 'Processing', tone: 'info' },
  INTERNAL_APPROVAL: { label: 'Internal Approval', tone: 'warning' },
  FOR_FINANCE: { label: 'For Finance', tone: 'warning' },
  COMPLETED: { label: 'Completed', tone: 'success' },
  CANCELLED: { label: 'Cancelled', tone: 'neutral' },
}

export const STATUS_OPTIONS = (Object.keys(STATUS_META) as Status[]).map((value) => ({
  value,
  label: STATUS_META[value].label,
}))

export const PRIORITY_META: Record<Priority, { label: string; tone: Tone }> = {
  LOW: { label: 'Low', tone: 'neutral' },
  NORMAL: { label: 'Normal', tone: 'neutral' },
  HIGH: { label: 'High', tone: 'warning' },
  URGENT: { label: 'Urgent', tone: 'danger' },
}

export const PRIORITY_OPTIONS = (Object.keys(PRIORITY_META) as Priority[]).map((value) => ({
  value,
  label: PRIORITY_META[value].label,
}))

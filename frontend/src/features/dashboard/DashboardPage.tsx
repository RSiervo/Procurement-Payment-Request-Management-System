import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, ArrowDown, CheckSquare, ArrowRight, ArrowUp, Banknote, Bell, Check, CheckCircle2, ChevronRight,
  Clock, CornerUpLeft, FileCheck2, FilePlus2, FileText, Inbox, Landmark, MoonStar, PackageCheck, Plus, Receipt, Send,
  Settings, ShoppingCart, Sun, Sunrise, XCircle, Zap,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { dashboardApi, notificationsApi } from '../../api/misc'
import { approvalsApi, requestsApi } from '../../api/requests'
import { BuildingArt } from '../../components/BuildingArt'
import { CountUp } from '../../components/ui/CountUp'
import {
  ButtonLink, Card, Donut, EmptyState, ErrorState, IconChip, LineChart, LoadingState, Stat, type ChipTone,
} from '../../components/ui'
import { useUser } from '../../hooks/useAuth'
import { useLookups } from '../../hooks/useLookups'
import { errorMessage } from '../../hooks/useToast'
import type { Dashboard, Notification } from '../../types'
import { formatDate, formatTime, greeting, typeColor } from '../../utils/format'
import { RequestTable } from '../requests/RequestTable'

const TYPE_ACTION: Record<string, { icon: ReactNode; tone: ChipTone; hint: string }> = {
  PR: { icon: <ShoppingCart size={20} />, tone: 'blue', hint: 'Request goods or services' },
  RFP: { icon: <Banknote size={20} />, tone: 'teal', hint: 'Process supplier payment' },
  REIM: { icon: <Receipt size={20} />, tone: 'amber', hint: 'Request expense reimbursement' },
}
const TYPE_SHORT: Record<string, string> = { PR: 'PR', RFP: 'RFP', REIM: 'Reimbursement' }

const EVENT_ICON: Record<string, { icon: ReactNode; tone: ChipTone }> = {
  REQUEST_SUBMITTED: { icon: <FilePlus2 size={18} />, tone: 'blue' },
  APPROVAL_REQUIRED: { icon: <FileCheck2 size={18} />, tone: 'blue' },
  REQUEST_APPROVED: { icon: <CheckCircle2 size={18} />, tone: 'green' },
  REQUEST_COMPLETED: { icon: <CheckCircle2 size={18} />, tone: 'green' },
  REQUEST_REJECTED: { icon: <XCircle size={18} />, tone: 'red' },
  REQUEST_RETURNED: { icon: <CornerUpLeft size={18} />, tone: 'amber' },
  CLARIFICATION_REQUESTED: { icon: <AlertTriangle size={18} />, tone: 'amber' },
  OPS_ACTION_REQUIRED: { icon: <PackageCheck size={18} />, tone: 'purple' },
  OPS_RECEIVED: { icon: <PackageCheck size={18} />, tone: 'purple' },
  STATUS_UPDATED: { icon: <Send size={18} />, tone: 'teal' },
}

type TimeOfDay = 'morning' | 'afternoon' | 'evening'

function timeOfDay(): TimeOfDay {
  const hour = new Date().getHours()
  return hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'
}

const TIME_ICON: Record<TimeOfDay, ReactNode> = {
  morning: <Sunrise size={15} />,
  afternoon: <Sun size={15} />,
  evening: <MoonStar size={15} />,
}

function todayLabel(): string {
  return new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date())
}

/** One sentence under the greeting saying what is actually on the person's plate today. */
function heroSummary({ requester, approver }: Dashboard): string {
  const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
  const parts: string[] = []
  if (approver?.pending) parts.push(`${count(approver.pending, 'request', 'requests')} waiting for your approval`)
  if (requester.pending) parts.push(`${count(requester.pending, 'request', 'requests')} of your own in approval`)
  if (requester.approved) parts.push(`${requester.approved} in processing`)
  if (requester.returned) parts.push(`${requester.returned} returned for revision`)
  if (parts.length === 0) return "You're all caught up. Nothing needs your attention right now."
  const list = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
  return `You have ${list}.`
}

interface KpiProps {
  label: string
  value: number
  to: string
  icon: ReactNode
  tone: ChipTone
  foot: ReactNode
  trend?: 'up' | 'down' | 'warn'
}

function Kpi({ label, value, to, icon, tone, foot, trend }: KpiProps) {
  return (
    <Link to={to} className="kpi">
      <div className="kpi-top">
        <IconChip tone={tone} solid large>{icon}</IconChip>
        <div>
          <div className="kpi-label">{label}</div>
          <div className="kpi-value"><CountUp value={value} /></div>
        </div>
      </div>
      <div className="kpi-foot" data-trend={trend}>{foot}</div>
    </Link>
  )
}

/** "↑ 20% from last month", or a plain count when there is nothing to compare against. */
function monthTrend(pair: { current: number; previous: number }, noun: string): Pick<KpiProps, 'foot' | 'trend'> {
  if (pair.previous === 0) {
    return { foot: <span><strong>{pair.current}</strong> {noun} this month</span> }
  }
  const change = Math.round(((pair.current - pair.previous) / pair.previous) * 100)
  if (change === 0) return { foot: <span>Same as last month</span> }
  return {
    trend: change > 0 ? 'up' : 'down',
    foot: <>{change > 0 ? <ArrowUp size={13} /> : <ArrowDown size={13} />}<span><strong>{Math.abs(change)}%</strong> from last month</span></>,
  }
}

function requesterKpis({ requester, insights }: Dashboard): KpiProps[] {
  const stale = insights.pending_over_3_days
  const overdue = insights.processing_overdue
  return [
    { label: 'Total Requests', value: requester.total, to: '/requests?scope=mine', icon: <FileText size={22} />, tone: 'blue',
      ...monthTrend(insights.created, 'created') },
    { label: 'Pending Approval', value: requester.pending, to: '/requests?scope=mine&status=PENDING_APPROVAL', icon: <Clock size={22} />, tone: 'amber',
      ...(stale > 0
        ? { trend: 'warn' as const, foot: <span><strong>{stale}</strong> waiting over 3 days</span> }
        : { foot: <span>{requester.pending ? 'All within 3 days' : 'Nothing waiting'}</span> }) },
    { label: 'In Processing (OPS)', value: requester.approved, to: '/requests?scope=mine&status=APPROVED,OPS_RECEIVED,PROCESSING,INTERNAL_APPROVAL,FOR_FINANCE', icon: <Settings size={22} />, tone: 'teal',
      ...(overdue > 0
        ? { trend: 'down' as const, foot: <span><strong>{overdue}</strong> overdue</span> }
        : { foot: <span>{requester.approved ? 'On schedule' : 'Nothing in process'}</span> }) },
    { label: 'Completed', value: requester.completed, to: '/requests?scope=mine&status=COMPLETED', icon: <Check size={22} strokeWidth={3} />, tone: 'purple',
      ...monthTrend(insights.completed, 'completed') },
  ]
}

export function DashboardPage() {
  const user = useUser()
  const lookups = useLookups()
  const navigate = useNavigate()
  const client = useQueryClient()
  const [days, setDays] = useState(7)
  const dashboard = useQuery({ queryKey: ['dashboard', days], queryFn: () => dashboardApi.get(days), placeholderData: keepPreviousData })
  const recent = useQuery({
    queryKey: ['requests', 'recent-mine'],
    queryFn: () => requestsApi.list({ scope: 'mine', page_size: 5, ordering: '-updated_at' }),
  })
  const notes = useQuery({ queryKey: ['notifications', 'recent'], queryFn: () => notificationsApi.list({ page_size: 6 }) })
  const data = dashboard.data
  const pending = useQuery({ queryKey: ['approvals', 'pending'], queryFn: approvalsApi.pending, enabled: !!data?.approver })

  if (dashboard.isLoading) return <LoadingState />
  if (dashboard.isError || !data) {
    return <div className="page"><ErrorState message={errorMessage(dashboard.error)} onRetry={() => void dashboard.refetch()} /></div>
  }
  const { requester, approver, ops } = data
  const types = lookups?.request_types ?? []
  const series = data.by_type.map((type) => ({ key: type.code, label: TYPE_SHORT[type.code] ?? type.name, color: typeColor(type.code) }))

  const openNote = async (note: Notification) => {
    if (!note.is_read) {
      await notificationsApi.read(note.id).catch(() => undefined)
      void client.invalidateQueries({ queryKey: ['notifications'] })
    }
    navigate(note.request ? `/requests/${note.request}` : '/notifications')
  }

  return (
    <div className="page">
      <div className="dashboard-grid">
        <div className="stack dash-main">
          <div className="hero">
            <span className="hero-orb hero-orb-a" aria-hidden />
            <span className="hero-orb hero-orb-b" aria-hidden />
            <BuildingArt className="hero-art" id="hero" />
            <div className="hero-text">
              <p className="hero-date">
                <span className="hero-date-icon" data-time={timeOfDay()} aria-hidden>{TIME_ICON[timeOfDay()]}</span>
                {todayLabel()}
              </p>
              <h1>{greeting()}, <span className="hero-name">{user.first_name || user.name}</span>!</h1>
              <p className="hero-summary">{heroSummary(data)}</p>
            </div>
          </div>

          {(requester.returned > 0 || (approver?.pending ?? 0) > 0) && (
            <div className="stack-sm">
              {!!approver?.pending && (
                <Link to="/approvals" className="callout callout-action" style={{ color: 'inherit', textDecoration: 'none' }}>
                  <div className="row between">
                    <strong>{approver.pending} request{approver.pending === 1 ? '' : 's'} waiting for your approval</strong>
                    <ArrowRight size={18} />
                  </div>
                </Link>
              )}
              {requester.returned > 0 && (
                <Link to="/requests?scope=mine&status=RETURNED" className="callout callout-warning" style={{ color: 'inherit', textDecoration: 'none' }}>
                  <div className="row between">
                    <strong>{requester.returned} of your requests {requester.returned === 1 ? 'was' : 'were'} returned for revision</strong>
                    <ArrowRight size={18} />
                  </div>
                </Link>
              )}
            </div>
          )}

          <div className="kpi-grid">
            {requesterKpis(data).map((kpi) => <Kpi key={kpi.label} {...kpi} />)}
          </div>

          <div className="chart-grid">
            <Card className="card-plain chart-card" title="Request Overview"
                  actions={
                    <select className="select-sm" aria-label="Period" value={days} onChange={(e) => setDays(Number(e.target.value))}>
                      <option value={7}>Last 7 days</option>
                      <option value={14}>Last 14 days</option>
                      <option value={30}>Last 30 days</option>
                    </select>
                  }>
              <LineChart unit="Requests submitted" series={series}
                         points={data.overview.map((day) => ({ label: day.label, values: day.counts }))} />
            </Card>
            <Card className="card-plain chart-card" title="Request Type Distribution">
              <Donut centerLabel="Total Requests"
                     slices={data.by_type.map((type) => ({ key: type.code, label: type.name, value: type.count, color: typeColor(type.code) }))} />
            </Card>
          </div>

          {approver && !!pending.data?.length && (
            <Card flush className="card-plain" title="Requests Requiring My Approval" actions={<Link to="/approvals" className="small">View all</Link>}>
              <RequestTable rows={pending.data.slice(0, 5)} showRequester compact hideHandler
                            extra={[{ header: 'Approval level', render: (row) => row.step_name }]} />
            </Card>
          )}

          <Card flush className="card-plain" title="Recent Requests" actions={<Link to="/requests?scope=mine" className="small">View all</Link>}>
            <RequestTable
              rows={recent.data?.results}
              loading={recent.isLoading}
              empty={
                <EmptyState title="You haven't created any requests yet"
                            message="Start a purchase requisition, payment request or reimbursement."
                            action={<ButtonLink to="/requests/new" variant="primary" icon={<Plus size={16} />}>Create Request</ButtonLink>} />
              }
            />
          </Card>

        </div>

        <div className="stack dash-side">
          <Card className="card-plain" title={<span className="card-heading"><Zap size={18} />Quick Actions</span>}>
            <div className="stack-sm" style={{ gap: 12 }}>
              {types.map((type) => {
                const meta = TYPE_ACTION[type.code] ?? { icon: <Plus size={20} />, tone: 'blue' as ChipTone, hint: type.description }
                return (
                  <Link key={type.code} to={`/requests/new?type=${type.code}`} className="quick-action">
                    <IconChip tone={meta.tone}>{meta.icon}</IconChip>
                    <span>
                      <span className="strong small" style={{ display: 'block' }}>Create {type.name}</span>
                      <span className="xs muted">{meta.hint}</span>
                    </span>
                    <ChevronRight size={18} />
                  </Link>
                )
              })}
            </div>
          </Card>

          <Card className="card-plain" title={<span className="card-heading"><Bell size={18} />Recent Notifications</span>}
                actions={<Link to="/notifications" className="small">View all</Link>}>
            {notes.isLoading ? <LoadingState /> : !notes.data?.results.length ? (
              <EmptyState icon={<Bell size={20} />} title="No notifications yet" />
            ) : (
              <div>
                {notes.data.results.slice(0, 5).map((note) => {
                  const meta = EVENT_ICON[note.event] ?? { icon: <Bell size={18} />, tone: 'blue' as ChipTone }
                  return (
                    <button key={note.id} type="button" className="feed-item" onClick={() => void openNote(note)}>
                      <IconChip tone={meta.tone} large>{meta.icon}</IconChip>
                      <span>
                        <span className={`feed-title small ${note.is_read ? '' : 'strong'}`} style={{ display: 'block' }}>{note.title}</span>
                        <span className="xs muted">{formatDate(note.created_at)} • {formatTime(note.created_at)}</span>
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </Card>

          {approver && (
            <Card className="card-plain" title={<span className="card-heading"><CheckSquare size={18} />My Approvals</span>}
                  actions={<Link to="/approvals" className="small">View all</Link>}>
              <div className="stat-grid stat-cards stat-tiles">
                <Stat label="Pending Approval" value={approver.pending} to="/approvals" icon={<Inbox size={18} />} iconTone="amber" />
                <Stat label="Approved Today" value={approver.approved_today} to="/approvals?tab=history" icon={<CheckCircle2 size={18} />} iconTone="green" />
                <Stat label="Returned" value={approver.returned} to="/approvals?tab=history" icon={<CornerUpLeft size={18} />} iconTone="blue" />
                <Stat label="Rejected" value={approver.rejected} to="/approvals?tab=history" icon={<XCircle size={18} />} iconTone="red" />
              </div>
            </Card>
          )}

          {ops && (
            <Card className="card-plain" title={<span className="card-heading"><PackageCheck size={18} />OPS Processing</span>}
                  actions={<Link to="/ops" className="small">View all</Link>}>
              <div className="stat-grid stat-cards stat-tiles">
                <Stat label="New Requests" value={ops.new} to="/ops?status=APPROVED" icon={<Inbox size={18} />} iconTone="blue" />
                <Stat label="Pending Processing" value={ops.pending_processing} to="/ops?status=OPS_RECEIVED" icon={<Clock size={18} />} iconTone="amber" />
                <Stat label="In Process" value={ops.in_process} to="/ops?status=PROCESSING" icon={<PackageCheck size={18} />} iconTone="teal" />
                <Stat label="Internal & Finance Approval" value={ops.waiting_finance} to="/ops?status=INTERNAL_APPROVAL,FOR_FINANCE" icon={<Landmark size={18} />} iconTone="purple" />
                <Stat label="Completed" value={ops.completed} to="/ops?status=COMPLETED" icon={<CheckCircle2 size={18} />} iconTone="green" />
                <Stat label="Overdue" value={ops.overdue} tone="danger" to="/ops?overdue=1" icon={<AlertTriangle size={18} />} iconTone="red" />
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

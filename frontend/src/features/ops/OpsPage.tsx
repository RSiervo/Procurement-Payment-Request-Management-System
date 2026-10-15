import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Clock, Inbox, Landmark, PackageCheck } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { dashboardApi } from '../../api/misc'
import { requestsApi, type RequestQuery } from '../../api/requests'
import { Button, ButtonLink, Card, DatePicker, EmptyState, Input, Pagination, Select, Stat, type ChipTone } from '../../components/ui'
import { useAuth } from '../../hooks/useAuth'
import { useDebounced, useLookups } from '../../hooks/useLookups'
import { useToast } from '../../hooks/useToast'
import type { RequestDetail, RequestSummary, Status } from '../../types'
import { PRIORITY_OPTIONS, STATUS_META } from '../../utils/format'
import { OpsStatusModal } from '../requests/detail/panels'
import { RequestTable } from '../requests/RequestTable'

const QUEUES: { key: string; label: string; status?: Status; overdue?: boolean; icon: ReactNode; tone: ChipTone; stat: 'new' | 'pending_processing' | 'in_process' | 'waiting_finance' | 'completed' | 'overdue' }[] = [
  { key: 'APPROVED', label: 'New Requests', status: 'APPROVED', stat: 'new', icon: <Inbox size={18} />, tone: 'blue' },
  { key: 'OPS_RECEIVED', label: 'Pending Processing', status: 'OPS_RECEIVED', stat: 'pending_processing', icon: <Clock size={18} />, tone: 'amber' },
  { key: 'PROCESSING', label: 'In Process', status: 'PROCESSING', stat: 'in_process', icon: <PackageCheck size={18} />, tone: 'teal' },
  { key: 'INTERNAL_APPROVAL,FOR_FINANCE', label: 'Internal & Finance Approval', stat: 'waiting_finance', icon: <Landmark size={18} />, tone: 'purple' },
  { key: 'COMPLETED', label: 'Completed', status: 'COMPLETED', stat: 'completed', icon: <CheckCircle2 size={18} />, tone: 'green' },
  { key: 'overdue', label: 'Overdue', overdue: true, stat: 'overdue', icon: <AlertTriangle size={18} />, tone: 'red' },
]
/** One-tap row action for the states OPS moves a request out of. */
const ROW_ACTION: Partial<Record<Status, string>> = { APPROVED: 'Receive Request', OPS_RECEIVED: 'Start Processing', PROCESSING: 'Finish Processing' }
const OPEN_STATUSES = 'APPROVED,OPS_RECEIVED,PROCESSING,INTERNAL_APPROVAL,FOR_FINANCE'

export function OpsPage() {
  const { hasRole, user } = useAuth()
  const PAGE_SIZE = user?.preferences.page_size ?? 20
  const lookups = useLookups()
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const term = useDebounced(search)
  const [moving, setMoving] = useState<{ request: RequestDetail; status: Status } | null>(null)
  const toast = useToast()
  const stats = useQuery({ queryKey: ['dashboard', 7], queryFn: () => dashboardApi.get() }).data?.ops

  const queue = params.get('overdue') ? 'overdue' : params.get('status') ?? ''
  const page = Number(params.get('page') ?? 1)
  const set = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params)
    next.delete('page')
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next, { replace: true })
  }
  const pickQueue = (key: string) => {
    if (key === queue) set({ status: '', overdue: '' })
    else if (key === 'overdue') set({ status: '', overdue: '1' })
    else set({ status: key, overdue: '' })
  }

  const assignee = params.get('assignee') ?? ''
  const query: RequestQuery = {
    status: params.get('status') || (queue === 'overdue' ? '' : OPEN_STATUSES),
    overdue: queue === 'overdue' ? true : undefined,
    type: params.get('type') ?? '',
    department: params.get('department') ?? '',
    priority: params.get('priority') ?? '',
    date_from: params.get('date_from') ?? '',
    date_to: params.get('date_to') ?? '',
    unassigned: assignee === 'none' ? true : undefined,
    ops_assignee: assignee && assignee !== 'none' ? assignee : '',
    search: term,
    page,
    page_size: PAGE_SIZE,
    ordering: 'approved_at',
  }
  const list = useQuery({ queryKey: ['requests', 'ops', query], queryFn: () => requestsApi.list(query), placeholderData: keepPreviousData })

  /** What "finish" means depends on the route, so ask the server which moves are open. */
  const advance = async (row: RequestSummary) => {
    try {
      const request = await requestsApi.get(row.id)
      const open = request.permissions.next_statuses.map((next) => next.status)
      const status = open.find((s) => s === 'INTERNAL_APPROVAL') ?? open.find((s) => s === 'COMPLETED') ?? open[0]
      if (status) setMoving({ request, status })
      else toast.error(new Error('This request has already moved on. Refresh the list.'))
    } catch (error) {
      toast.error(error)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>OPS Processing</h1>
          <p>Requests approved by the department head: receive, process, then send on for internal and Finance approval.</p>
        </div>
      </div>

      <div className="stat-grid">
        {QUEUES.map((q) => (
          <Stat key={q.key} label={q.label} value={stats?.[q.stat] ?? '–'} tone={q.overdue ? 'danger' : undefined} icon={q.icon} iconTone={q.tone}
                pressed={queue === q.key} onClick={() => pickQueue(q.key)} />
        ))}
      </div>

      <Card>
        <div className="filters">
          <div className="span-all">
            <Input label="Search" type="search" placeholder="Request number, requester…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select label="Request type" placeholder="All types" value={params.get('type') ?? ''} onChange={(e) => set({ type: e.target.value })}
                  options={(lookups?.request_types ?? []).map((t) => ({ value: t.code, label: t.name }))} />
          <Select label="Department" placeholder="All departments" value={params.get('department') ?? ''} onChange={(e) => set({ department: e.target.value })}
                  options={(lookups?.departments ?? []).map((d) => ({ value: d.id, label: d.name }))} />
          <Select label="Priority" placeholder="Any priority" value={params.get('priority') ?? ''} onChange={(e) => set({ priority: e.target.value })}
                  options={PRIORITY_OPTIONS} />
          <Select label="Processor" placeholder="Anyone" value={assignee} onChange={(e) => set({ assignee: e.target.value })}
                  options={[{ value: 'none', label: 'Unassigned' }, ...(lookups?.ops_users ?? []).map((u) => ({ value: u.id, label: u.name }))]} />
          <DatePicker label="Created from" value={params.get('date_from') ?? ''} onChange={(e) => set({ date_from: e.target.value })} />
          <DatePicker label="Created to" value={params.get('date_to') ?? ''} onChange={(e) => set({ date_to: e.target.value })} />
        </div>
      </Card>

      <Card flush title={queue ? QUEUES.find((q) => q.key === queue)?.label ?? STATUS_META[queue as Status]?.label : 'All Open Requests'}>
        <RequestTable
          rows={list.data?.results}
          loading={list.isLoading}
          showRequester
          compact
          extra={[{ header: 'Processor', render: (row) => row.ops_assignee_name || <span className="muted">Unassigned</span> }]}
          actions={(row) => (
            hasRole('OPS') && ROW_ACTION[row.status]
              ? <Button size="sm" variant="primary" onClick={() => void advance(row)}>{ROW_ACTION[row.status]}</Button>
              : <ButtonLink size="sm" to={`/requests/${row.id}`}>View</ButtonLink>
          )}
          empty={<EmptyState icon={<PackageCheck size={20} />} title="No requests in this queue" message="Requests appear here once the department head has approved them." />}
        />
        {list.data && <Pagination page={page} pageSize={PAGE_SIZE} count={list.data.count} onChange={(p) => { const n = new URLSearchParams(params); n.set('page', String(p)); setParams(n, { replace: true }) }} />}
      </Card>
      {moving && <OpsStatusModal request={moving.request} status={moving.status} onClose={() => setMoving(null)} />}
    </div>
  )
}

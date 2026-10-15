import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CheckCircle2, CheckSquare, CornerUpLeft, Inbox, X, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { approvalsApi, requestsApi, type Decision } from '../../api/requests'
import { ApiError } from '../../api/client'
import { Badge, Button, ButtonLink, Card, Checkbox, ConfirmationDialog, DataTable, EmptyState, Pagination, Stat, Tabs } from '../../components/ui'
import { useToast } from '../../hooks/useToast'
import { dashboardApi } from '../../api/misc'
import { useIsDesktop } from '../../hooks/useLookups'
import type { PendingApproval, RequestDetail } from '../../types'
import { formatDateTime, timeAgo, type Tone } from '../../utils/format'
import { DecisionModal } from '../requests/detail/panels'
import { RequestTable } from '../requests/RequestTable'

const ACTION_TONE: Record<string, Tone> = { APPROVE: 'success', REJECT: 'danger', RETURN: 'purple', CLARIFY: 'warning' }

export function ApprovalsPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'history' ? 'history' : 'pending'
  const [page, setPage] = useState(1)
  const [acting, setActing] = useState<{ request: RequestDetail; decision: Decision } | null>(null)
  const pending = useQuery({ queryKey: ['approvals', 'pending'], queryFn: approvalsApi.pending })
  const history = useQuery({ queryKey: ['approvals', 'history', page], queryFn: () => approvalsApi.history(page), enabled: tab === 'history' })
  const stats = useQuery({ queryKey: ['dashboard', 7], queryFn: () => dashboardApi.get() }).data?.approver
  const isDesktop = useIsDesktop()

  // Ticked rows can be approved together; each one is still decided and recorded on its own.
  const client = useQueryClient()
  const toast = useToast()
  const [selected, setSelected] = useState<string[]>([])
  const [confirmBulk, setConfirmBulk] = useState(false)
  const waiting = pending.data ?? []
  const chosen = selected.filter((id) => waiting.some((row) => row.id === id))
  const tick = (id: string) => setSelected((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id]))
  const approveChosen = async () => {
    try {
      const result = await approvalsApi.bulkApprove(chosen)
      setSelected([])
      if (result.approved.length) toast.success(`Approved ${result.approved.length} request${result.approved.length === 1 ? '' : 's'}: ${result.approved.join(', ')}.`)
      for (const failure of result.failed) toast.error(new ApiError(400, `${failure.number || 'A request'} was not approved: ${failure.detail}`))
    } catch (error) {
      toast.error(error)
    }
    void client.invalidateQueries({ queryKey: ['approvals'] })
    void client.invalidateQueries({ queryKey: ['requests'] })
    void client.invalidateQueries({ queryKey: ['dashboard'] })
  }

  // Quick actions need the full request (for the confirmation text); fetch it on demand.
  const start = async (row: PendingApproval, decision: Decision) => setActing({ request: await requestsApi.get(row.id), decision })

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Approvals</h1>
          <p>Requests requiring your approval, oldest first.</p>
        </div>
      </div>

      <div className="stat-grid stat-cards">
        <Stat label="Pending Approval" value={pending.data?.length ?? '–'} icon={<Inbox size={18} />} iconTone="amber" />
        <Stat label="Approved Today" value={stats?.approved_today ?? '–'} icon={<CheckCircle2 size={18} />} iconTone="green" />
        <Stat label="Returned" value={stats?.returned ?? '–'} icon={<CornerUpLeft size={18} />} iconTone="blue" />
        <Stat label="Rejected" value={stats?.rejected ?? '–'} icon={<XCircle size={18} />} iconTone="red" />
      </div>

      <Tabs value={tab} onChange={(value) => setParams(value === 'history' ? { tab: 'history' } : {}, { replace: true })}
            tabs={[{ value: 'pending', label: 'Requiring My Approval', count: pending.data?.length }, { value: 'history', label: 'My Decisions' }]} />

      {tab === 'pending' ? (
        <Card flush>
          {waiting.length > 1 && (
            <div className="bulk-bar">
              <Checkbox label={chosen.length ? `${chosen.length} selected` : 'Select all'} checked={chosen.length === waiting.length}
                        onChange={(e) => setSelected(e.target.checked ? waiting.map((row) => row.id) : [])} />
              <Button size="sm" variant="success" icon={<Check size={14} />} disabled={!chosen.length} onClick={() => setConfirmBulk(true)}>
                Approve selected{chosen.length ? ` (${chosen.length})` : ''}
              </Button>
            </div>
          )}
          <RequestTable
            rows={pending.data}
            loading={pending.isLoading}
            showRequester
            compact
            hideHandler
            extra={[{
              header: 'Approval level',
              render: (row) => (
                <span>
                  {row.step_name}
                  {row.needs_clarification && <> <Badge tone="warning" plain>Question asked</Badge></>}
                  <span className="xs muted" style={{ display: 'block' }}>Waiting {timeAgo(row.pending_since).replace(' ago', '')}</span>
                </span>
              ),
            }]}
            // Desktop rows open the request to review; phone cards keep one-tap decisions.
            actions={(row) => isDesktop ? (
              <>
                {waiting.length > 1 && (
                  <input type="checkbox" className="bulk-tick" aria-label={`Select ${row.number}`} checked={chosen.includes(row.id)}
                         onChange={() => tick(row.id)} />
                )}
                <ButtonLink size="sm" variant="primary" to={`/requests/${row.id}`}>Review</ButtonLink>
              </>
            ) : (
              <>
                {waiting.length > 1 && (
                  <input type="checkbox" className="bulk-tick" aria-label={`Select ${row.number}`} checked={chosen.includes(row.id)}
                         onChange={() => tick(row.id)} />
                )}
                <Button size="sm" variant="danger" icon={<X size={14} />} aria-label={`Reject ${row.number}`} onClick={() => void start(row, 'reject')}>Reject</Button>
                <Button size="sm" icon={<CornerUpLeft size={14} />} aria-label={`Return ${row.number}`} onClick={() => void start(row, 'return')}>Return</Button>
                <Button size="sm" variant="success" icon={<Check size={14} />} aria-label={`Approve ${row.number}`} onClick={() => void start(row, 'approve')}>Approve</Button>
              </>
            )}
            empty={<EmptyState icon={<CheckSquare size={20} />} title="Nothing is waiting for you" message="New requests that need your approval will appear here, and you'll be notified by email." />}
          />
        </Card>
      ) : (
        <Card flush>
          <DataTable
            rows={history.data?.results}
            loading={history.isLoading}
            rowKey={(row) => row.id}
            rowHref={(row) => `/requests/${row.request.id}`}
            empty={<EmptyState title="No decisions yet" message="Requests you approve, return or reject are listed here." />}
            columns={[
              { header: 'Request #', render: (row) => <Link className="strong num" to={`/requests/${row.request.id}`}>{row.request.number}</Link> },
              { header: 'Type', render: (row) => row.request.type_name },
              { header: 'Step', render: (row) => row.step_name },
              { header: 'Decision', render: (row) => <Badge tone={ACTION_TONE[row.action]}>{row.action_display}</Badge> },
              { header: 'Comments', render: (row) => row.comments || <span className="muted">—</span> },
              { header: 'Date', render: (row) => <span className="nowrap">{formatDateTime(row.created_at)}</span> },
            ]}
            card={(row) => (
              <>
                <div className="row between"><span className="strong num">{row.request.number}</span><Badge tone={ACTION_TONE[row.action]}>{row.action_display}</Badge></div>
                <div className="small secondary">{row.request.type_name} · {row.step_name}</div>
                {row.comments && <div className="small">{row.comments}</div>}
                <div className="xs muted">{formatDateTime(row.created_at)}</div>
              </>
            )}
          />
          {history.data && <Pagination page={page} pageSize={20} count={history.data.count} onChange={setPage} />}
        </Card>
      )}
      {acting && <DecisionModal request={acting.request} decision={acting.decision} onClose={() => setActing(null)} />}
      {confirmBulk && (
        <ConfirmationDialog title={`Approve ${chosen.length} request${chosen.length === 1 ? '' : 's'}?`} confirmLabel="Approve all"
                            message="Your e-signature is applied to each one, exactly as if you had approved them one by one. Requests you have not opened are approved without being reviewed."
                            onConfirm={approveChosen} onClose={() => setConfirmBulk(false)} />
      )}
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, Ban, Check, CornerUpLeft, Download, FilePlus2, HelpCircle, Pencil, Printer, Send, Trash2, X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, downloadFile, openFile, printFile } from '../../api/client'
import { requestsApi, type Decision } from '../../api/requests'
import {
  AttachmentList, Button, ButtonLink, Card, ConfirmationDialog, ErrorState, FileUpload, LoadingState,
  PriorityBadge, StatusBadge, Tabs,
} from '../../components/ui'
import { useLookups } from '../../hooks/useLookups'
import { errorMessage, useToast } from '../../hooks/useToast'
import type { RequestDetail, Status } from '../../types'
import { formatDate, formatDateTime, money, quantity } from '../../utils/format'
import {
  ActivityPanel, ApprovalTimeline, CommentsPanel, DecisionModal, NotificationsPanel, opsActionLabel, OpsPanel,
  OpsStatusModal, useRefreshRequest,
} from './detail/panels'
import { ChecksPanel } from './detail/ChecksPanel'
import { AdvanceCard, PurchaseOrderCard } from './detail/ExtraCards'
import { OverdueBadge } from './RequestTable'
import { LINE_NOUN } from './wizard/steps'

/** One sentence answering "what is happening to my request?" */
type DetailTab = 'overview' | 'items' | 'attachments' | 'timeline' | 'activity' | 'comments'

const LINKABLE: Status[] = ['APPROVED', 'OPS_RECEIVED', 'PROCESSING', 'INTERNAL_APPROVAL', 'FOR_FINANCE', 'COMPLETED']

function statusLine(req: RequestDetail): string {
  switch (req.status) {
    case 'DRAFT': return 'This draft has not been submitted yet.'
    case 'PENDING_APPROVAL': return `Waiting for approval — currently with ${req.current_handler}.`
    case 'RETURNED': return 'Returned for revision. Update the request and resubmit it.'
    case 'REJECTED': return 'This request was rejected and is closed.'
    case 'APPROVED': return 'Approved. Waiting for OPS to receive it.'
    case 'OPS_RECEIVED': return `OPS received this request on ${formatDate(req.ops_received_at)}.`
    case 'PROCESSING': return `OPS is processing this request${req.ops_assignee_name ? ` (${req.ops_assignee_name})` : ''}.`
    case 'INTERNAL_APPROVAL': return `Processed by OPS. Waiting for internal approval — currently with ${req.current_handler}.`
    case 'FOR_FINANCE': return 'Processed by OPS and now with Finance for the final sign-off.'
    case 'COMPLETED': return `Completed on ${formatDate(req.completed_at)}.`
    case 'CANCELLED': return 'This request was cancelled.'
  }
}

function LinesTable({ req }: { req: RequestDetail }) {
  const kind = req.form_kind
  return (
    <>
      <div className="record-list mobile-only">
        {req.lines.map((line) => (
          <div key={line.id} className="record-card">
            <div className="row between" style={{ alignItems: 'flex-start' }}>
              <span className="strong small">{kind === 'ITEMS' && `${quantity(line.quantity)} × `}{line.description}</span>
              {Number(line.amount) > 0 && <span className="num small nowrap">{money(line.amount)}</span>}
            </div>
            {kind === 'EXPENSE' && <div className="xs muted">{formatDate(line.expense_date)} · {line.category_name}</div>}
            {line.remarks && <div className="xs secondary">{kind === 'ITEMS' ? 'Purpose: ' : ''}{line.remarks}</div>}
          </div>
        ))}
      </div>
      <div className="table-wrap desktop-only">
        <table className="table">
          <thead>
            {kind === 'ITEMS' && <tr><th style={{ width: 70 }}>Qty</th><th>Description</th><th>Purpose / Remarks</th><th className="right">Est. unit cost</th><th className="right">Est. amount</th></tr>}
            {kind === 'PAYMENT' && <tr><th>Particulars</th><th>Remarks</th><th className="right">Amount</th></tr>}
            {kind === 'EXPENSE' && <tr><th>Date</th><th>Category</th><th>Description</th><th className="right">Amount</th></tr>}
          </thead>
          <tbody>
            {req.lines.map((line) => (
              <tr key={line.id}>
                {kind === 'ITEMS' && <><td className="num">{quantity(line.quantity)}</td><td>{line.description}</td><td>{line.remarks}</td>
                  <td className="right num">{line.unit_cost != null ? money(line.unit_cost) : '—'}</td>
                  <td className="right num">{line.unit_cost != null ? money(line.amount) : '—'}</td></>}
                {kind === 'PAYMENT' && <><td>{line.description}</td><td>{line.remarks}</td><td className="right num">{money(line.amount)}</td></>}
                {kind === 'EXPENSE' && <><td className="nowrap">{formatDate(line.expense_date)}</td><td>{line.category_name}</td><td>{line.description}</td><td className="right num">{money(line.amount)}</td></>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row between" style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', background: 'var(--surface-sunken)' }}>
        <span className="strong small">{kind === 'EXPENSE' ? 'Total Reimbursement' : kind === 'ITEMS' ? 'Estimated Total' : 'Total'}</span>
        <strong className="num">{money(req.total_amount)}</strong>
      </div>
    </>
  )
}

export function RequestDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const lookups = useLookups()
  const refresh = useRefreshRequest(id)
  const query = useQuery({ queryKey: ['requests', 'detail', id], queryFn: () => requestsApi.get(id) })
  const [decision, setDecision] = useState<Decision | null>(null)
  const [opsStatus, setOpsStatus] = useState<Status | null>(null)
  const [confirm, setConfirm] = useState<'cancel' | 'delete' | 'submit' | null>(null)
  const [tab, setTab] = useState<DetailTab>('overview')
  const [uploading, setUploading] = useState(false)
  const [busyFile, setBusyFile] = useState<'pdf' | 'print' | null>(null)

  // Arriving from an email's Approve or Return button: open that confirmation, once.
  const [searchParams, setSearchParams] = useSearchParams()
  const asked = searchParams.get('action')
  const loaded = query.data
  useEffect(() => {
    if (!asked || !loaded) return
    if (asked === 'approve' || asked === 'return') {
      if (loaded.permissions.can_decide) setDecision(asked)
      else toast.error(new ApiError(409, `${loaded.number} is no longer waiting for your decision.`))
    }
    setSearchParams({}, { replace: true })
    // `toast` and `setSearchParams` are stable enough; this must run once per arrival.
  }, [asked, loaded]) // oxlint-disable-line react-hooks/exhaustive-deps

  if (query.isLoading) return <LoadingState />
  if (query.isError || !query.data) {
    const notFound = query.error instanceof ApiError && query.error.status === 404
    return (
      <div className="page">
        <ErrorState message={notFound ? 'This request does not exist, or you do not have access to it.' : errorMessage(query.error)}
                    onRetry={notFound ? undefined : () => void query.refetch()} />
      </div>
    )
  }
  const req = query.data
  const can = req.permissions
  const isOwner = can.is_owner
  const canRaisePayment = req.type_code === 'PR' && isOwner && LINKABLE.includes(req.status)
  const attachmentPath = (attachmentId: string) => requestsApi.attachmentPath(req.id, attachmentId)

  const file = async (kind: 'pdf' | 'print') => {
    setBusyFile(kind)
    try {
      if (kind === 'pdf') await downloadFile(requestsApi.pdfPath(req.id), `${req.number}.pdf`)
      else await printFile(requestsApi.pdfPath(req.id))
    } catch (error) {
      toast.error(error)
    } finally {
      setBusyFile(null)
    }
  }

  const upload = async (files: File[]) => {
    setUploading(true)
    for (const item of files) {
      try {
        await requestsApi.upload(req.id, item, 'OTHER')
      } catch (error) {
        const message = error instanceof ApiError ? error.field('file') ?? error.message : 'Upload failed.'
        toast.error(new ApiError(400, `${item.name}: ${message}`))
      }
    }
    setUploading(false)
    refresh()
  }

  const resubmit = async () => {
    try {
      const fresh = await requestsApi.submit(req.id)
      refresh(fresh)
      toast.success(`${fresh.number} submitted for approval.`)
    } catch (error) {
      const issues = error instanceof ApiError ? Object.values(error.errors).flat() : []
      toast.error(issues.length ? new ApiError(400, `Cannot submit yet: ${issues.join(' ')}`) : error)
    }
  }

  const handOver = async () => {
    try {
      refresh(await requestsApi.handOver(req.id))
      toast.success(`Sent to ${req.requester_name}. They will review and submit it.`)
    } catch (error) {
      toast.error(error)
    }
  }

  const stickyActions = can.can_decide || can.next_statuses.length > 0 || can.can_edit

  return (
    <div className="page">
      <div className="card">
        <div className="card-body request-hero">
          <div className="row-wrap between" style={{ alignItems: 'flex-start' }}>
            <div className="row" style={{ alignItems: 'flex-start', gap: 4 }}>
              <Link to="/requests" className="icon-btn" aria-label="Back to requests" style={{ marginLeft: -10, marginTop: -6 }}><ArrowLeft size={20} /></Link>
              <div>
                <div className="row-wrap" style={{ gap: 10 }}>
                  <h1>{req.number}</h1>
                  <StatusBadge status={req.status} />
                  <PriorityBadge priority={req.priority} />
                  <OverdueBadge row={req} />
                </div>
                <div className="secondary small">{req.type_name}</div>
              </div>
            </div>
            <div className="row-wrap">
              {req.status !== 'DRAFT' && (
                <>
                  <Button icon={<Download size={16} />} loading={busyFile === 'pdf'} onClick={() => void file('pdf')}>Generate PDF</Button>
                  <Button icon={<Printer size={16} />} loading={busyFile === 'print'} onClick={() => void file('print')}>Print</Button>
                </>
              )}
              {can.can_cancel && <Button variant="danger" icon={<Ban size={16} />} onClick={() => setConfirm('cancel')}>Cancel Request</Button>}
              {can.can_delete && <Button variant="danger" icon={<Trash2 size={16} />} onClick={() => setConfirm('delete')}>Delete Draft</Button>}
            </div>
          </div>
          <dl className="dl dl-4">
            <div><dt>Requester</dt><dd>{req.requester_name}{req.requester_position && <span className="muted"> · {req.requester_position}</span>}</dd></div>
            <div><dt>Department</dt><dd>{req.department_name}</dd></div>
            <div><dt>Amount</dt><dd className="request-amount">{money(req.total_amount)}</dd></div>
            <div><dt>{req.status === 'DRAFT' ? 'Date Created' : 'Date Submitted'}</dt><dd>{formatDateTime(req.submitted_at ?? req.created_at)}</dd></div>
          </dl>
          <p className="small secondary">{statusLine(req)}</p>
        </div>
      </div>

      {can.can_decide && (
        <div className="callout callout-action">
          <strong>This request requires your approval</strong>
          <span className="small secondary">Step: {req.current_step?.name}. Review the details below, then approve, return or reject.</span>
        </div>
      )}
      {req.prepared_for_other && req.status === 'DRAFT' && (
        <div className="callout callout-action">
          <strong>{can.can_submit ? `${req.prepared_by_name} prepared this request for you` : `Prepared for ${req.requester_name}`}</strong>
          <span className="small secondary">
            {can.can_submit
              ? 'Review it, change anything that is wrong, then submit it. Submitting applies your e-signature.'
              : `Only ${req.requester_name} can submit it, because it carries their signature. Send it to them when it is ready.`}
          </span>
        </div>
      )}
      <ChecksPanel checks={req.checks} />
      {req.current_step?.needs_clarification && isOwner && (
        <div className="callout callout-warning">
          <strong>The approver asked a question</strong>
          <span className="small">See the Approval Timeline tab for the question and reply under Comments.</span>
        </div>
      )}
      {req.status === 'RETURNED' && can.can_edit && (
        <div className="callout callout-warning">
          <strong>Returned for revision</strong>
          <span className="small">The approver's comments are in the approval timeline. Edit the request, then resubmit.</span>
        </div>
      )}

      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'overview', label: 'Overview' },
        { value: 'items', label: LINE_NOUN[req.form_kind].title, count: req.lines.length },
        { value: 'attachments', label: 'Attachments', count: req.attachments.length },
        { value: 'timeline', label: 'Approval Timeline' },
        { value: 'activity', label: 'Activity' },
        { value: 'comments', label: 'Comments' },
      ]} />

      <div className={tab === 'overview' ? 'split' : 'stack'}>
        <div className="stack">
          {tab === 'overview' && <Card title="Request Details">
            <dl className="dl">
              {req.date_needed && <div><dt>Date needed</dt><dd>{formatDate(req.date_needed)}</dd></div>}
              {req.form_kind !== 'ITEMS' && <div><dt>Payable to</dt><dd>{req.payable_to || '—'}</dd></div>}
              <div><dt>Prepared by</dt><dd>{req.prepared_by_name}</dd></div>
              {req.form_kind !== 'ITEMS' && (
                <>
                  <div><dt>{req.type_code === 'LIQ' ? 'Cash advance' : 'PR #'}</dt><dd>{req.source_request ? <Link to={`/requests/${req.source_request.id}`}>{req.source_request.number}</Link> : req.pr_reference || '—'}</dd></div>
                  <div><dt>PO #</dt><dd>{req.po_number || '—'}</dd></div>
                  <div><dt>RR #</dt><dd>{req.rr_number || '—'}</dd></div>
                  <div><dt>Invoice #</dt><dd>{req.invoice_number || '—'}</dd></div>
                  {req.form_kind === 'PAYMENT' && <div><dt>Posted</dt><dd>{req.posted === null ? '—' : req.posted ? 'Yes' : 'No'}</dd></div>}
                </>
              )}
              {req.form_kind === 'ITEMS' && (req.po_number || req.rr_number || req.invoice_number) && (
                <>
                  <div><dt>PO #</dt><dd>{req.po_number || '—'}</dd></div>
                  <div><dt>RR #</dt><dd>{req.rr_number || '—'}</dd></div>
                  <div><dt>Invoice #</dt><dd>{req.invoice_number || '—'}</dd></div>
                </>
              )}
              {req.purpose && <div className="span-all"><dt>{req.form_kind === 'EXPENSE' ? 'Purpose / Business justification' : 'Purpose / Remarks'}</dt><dd className="pre-wrap">{req.purpose}</dd></div>}
            </dl>
          </Card>}

          {(tab === 'overview' || tab === 'items') && <Card title={LINE_NOUN[req.form_kind].title} flush><LinesTable req={req} /></Card>}

          {(tab === 'overview' || tab === 'attachments') && <Card title={`Attachments${req.attachments.length ? ` (${req.attachments.length})` : ''}`}>
            <div className="stack">
              <AttachmentList
                attachments={req.attachments}
                onOpen={(a) => void openFile(attachmentPath(a.id), { inline: 1 }).catch(toast.error)}
                onDownload={(a) => void downloadFile(attachmentPath(a.id), a.original_name).catch(toast.error)}
                onRemove={(a) => void requestsApi.removeAttachment(req.id, a.id).then(() => refresh()).catch(toast.error)}
              />
              {can.can_attach && lookups && <FileUpload onFiles={(files) => void upload(files)} busy={uploading} maxMb={lookups.config.max_upload_mb} />}
            </div>
          </Card>}

          {tab === 'timeline' && <ApprovalTimeline requestId={req.id} />}
          {tab === 'comments' && <Card title="Comments"><CommentsPanel requestId={req.id} /></Card>}
          {tab === 'activity' && (
            <>
              <Card title="Activity History"><ActivityPanel requestId={req.id} /></Card>
              <Card title="Notifications Sent"><NotificationsPanel requestId={req.id} /></Card>
            </>
          )}
        </div>

        {tab === 'overview' && <div className="stack">
          <ApprovalTimeline requestId={req.id} />
          {can.can_update_processing && lookups && <OpsPanel key={req.updated_at} request={req} lookups={lookups} />}
          <AdvanceCard request={req} />
          {req.type_code === 'PR' && <PurchaseOrderCard key={`po-${req.updated_at}`} request={req} lookups={lookups} onChanged={(fresh) => refresh(fresh)} />}
          <Card title="Recent Activity" actions={<button type="button" className="btn btn-ghost btn-sm" onClick={() => setTab('activity')}>View all</button>}>
            <ActivityPanel requestId={req.id} limit={4} />
          </Card>
          {(req.source_request || req.linked_requests.length > 0 || canRaisePayment) && (
            <Card title="Related Documents">
              <div className="stack-sm">
                {[...(req.source_request ? [req.source_request] : []), ...req.linked_requests].map((related) => (
                  <Link key={related.id} to={`/requests/${related.id}`} className="flow-node" style={{ color: 'inherit', textDecoration: 'none' }}>
                    <div className="row between"><strong className="num small">{related.number}</strong><span className="num small">{money(related.total_amount)}</span></div>
                    <div className="row between"><span className="xs muted">{related.type_name}</span><StatusBadge status={related.status} /></div>
                  </Link>
                ))}
                {canRaisePayment && (
                  <ButtonLink to={`/requests/new?type=RFP&pr=${encodeURIComponent(req.number)}`} icon={<FilePlus2 size={16} />}>
                    Create Request for Payment
                  </ButtonLink>
                )}
              </div>
            </Card>
          )}
        </div>}
      </div>

      {stickyActions && (
        <div className="action-bar">
          {can.can_decide && (
            <>
              <Button variant="ghost" className="btn-compact" icon={<HelpCircle size={18} />} aria-label="Ask the requester a question" onClick={() => setDecision('clarify')}><span className="desktop-only">Ask a question</span></Button>
              <Button variant="danger" icon={<X size={16} />} onClick={() => setDecision('reject')}>Reject</Button>
              <Button icon={<CornerUpLeft size={16} />} onClick={() => setDecision('return')}>Return</Button>
              <Button variant="success" icon={<Check size={16} />} onClick={() => setDecision('approve')}>Approve</Button>
            </>
          )}
          {can.next_statuses.map((next, index) => (
            <Button key={next.status} variant={index === can.next_statuses.length - 1 ? 'primary' : 'secondary'} onClick={() => setOpsStatus(next.status)}>
              {opsActionLabel(req.status, next.status)}
            </Button>
          ))}
          {can.can_edit && <ButtonLink to={`/requests/${req.id}/edit`} icon={<Pencil size={16} />}>Edit</ButtonLink>}
          {can.can_hand_over && (
            <Button variant="primary" icon={<Send size={16} />} onClick={() => void handOver()}>Send to {req.requester_name} to submit</Button>
          )}
          {can.can_submit && (
            <Button variant="primary" icon={<Send size={16} />} onClick={() => setConfirm('submit')}>
              {req.status === 'RETURNED' ? 'Resubmit' : 'Submit Request'}
            </Button>
          )}
        </div>
      )}

      {decision && <DecisionModal request={req} decision={decision} onClose={() => setDecision(null)} />}
      {opsStatus && <OpsStatusModal request={req} status={opsStatus} onClose={() => setOpsStatus(null)} />}
      {confirm === 'submit' && (
        <ConfirmationDialog title={req.status === 'RETURNED' ? 'Resubmit request?' : 'Submit request?'} confirmLabel="Submit"
                            message="The request will be sent for approval and can no longer be edited unless it is returned to you."
                            onConfirm={resubmit} onClose={() => setConfirm(null)} />
      )}
      {confirm === 'cancel' && (
        <ConfirmationDialog title="Cancel this request?" confirmLabel="Cancel Request" danger
                            message={`${req.number} will be withdrawn from approval. This cannot be undone.`}
                            onConfirm={async () => {
                              try {
                                refresh(await requestsApi.cancel(req.id, ''))
                                toast.success(`${req.number} cancelled.`)
                              } catch (error) { toast.error(error) }
                            }}
                            onClose={() => setConfirm(null)} />
      )}
      {confirm === 'delete' && (
        <ConfirmationDialog title="Delete this draft?" confirmLabel="Delete Draft" danger
                            message="The draft and its attachments will be permanently removed."
                            onConfirm={async () => {
                              try {
                                await requestsApi.remove(req.id)
                                toast.success('Draft deleted.')
                                navigate('/requests?scope=drafts')
                                refresh()
                              } catch (error) { toast.error(error) }
                            }}
                            onClose={() => setConfirm(null)} />
      )}
    </div>
  )
}

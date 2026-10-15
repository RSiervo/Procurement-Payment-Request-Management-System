import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Mail, MessageSquare, Send } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { ApiError } from '../../../api/client'
import { requestsApi, type Decision } from '../../../api/requests'
import {
  Avatar, Badge, Button, Card, EmptyState, Input, LoadingState, Modal, Segmented, Select, Textarea, Timeline,
} from '../../../components/ui'
import { SignatureField } from '../../../components/SignatureField'
import { useUser } from '../../../hooks/useAuth'
import { useToast } from '../../../hooks/useToast'
import type { Lookups, RequestDetail, Status } from '../../../types'
import { formatDateTime, PRIORITY_OPTIONS, STATUS_META, timeAgo, type Tone } from '../../../utils/format'

/** After any change to a request, refresh everything that shows it. */
export function useRefreshRequest(id: string) {
  const client = useQueryClient()
  return (fresh?: RequestDetail) => {
    if (fresh) client.setQueryData(['requests', 'detail', id], fresh)
    for (const key of [['requests'], ['approvals'], ['dashboard'], ['notifications']]) {
      void client.invalidateQueries({ queryKey: key })
    }
  }
}

// ------------------------------------------------------------ Decisions

const DECISIONS: Record<Decision, { title: string; confirm: string; variant: 'success' | 'danger' | 'primary'; label: string; hint: string; done: string }> = {
  approve: { title: 'Approve request', confirm: 'Approve', variant: 'success', label: 'Comments (optional)',
             hint: 'Your name, position and the time are recorded as an electronic approval.', done: 'approved' },
  return: { title: 'Return for revision', confirm: 'Return', variant: 'primary', label: 'What needs to change?',
            hint: 'The requester can edit and resubmit. Earlier approvals stay on record.', done: 'returned to the requester' },
  reject: { title: 'Reject request', confirm: 'Reject', variant: 'danger', label: 'Reason for rejection',
            hint: 'Rejection is final. The requester will need to raise a new request.', done: 'rejected' },
  clarify: { title: 'Request clarification', confirm: 'Send question', variant: 'primary', label: 'Your question',
             hint: 'The request stays with you. The requester replies in the comments.', done: 'sent a question on' },
}

export function DecisionModal({ request, decision, onClose }: { request: RequestDetail; decision: Decision; onClose: () => void }) {
  const meta = DECISIONS[decision]
  const toast = useToast()
  const refresh = useRefreshRequest(request.id)
  const [comments, setComments] = useState('')
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: () => requestsApi.decide(request.id, decision, comments.trim()),
    onSuccess: (fresh) => {
      refresh(fresh)
      toast.success(`You ${meta.done} ${request.number}.`)
      onClose()
    },
    onError: (err) => setError(err instanceof ApiError ? err.field('comments') ?? err.field('signature') ?? err.message : 'Something went wrong.'),
  })
  const required = decision !== 'approve'
  const user = useUser()
  // Approving puts the approver's e-signature on the form, so one must be on file.
  const needsSignature = decision === 'approve' && !user.has_signature

  return (
    <Modal
      title={meta.title}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
          <Button variant={meta.variant} loading={mutation.isPending} disabled={(required && !comments.trim()) || needsSignature} onClick={() => mutation.mutate()}>
            {meta.confirm}
          </Button>
        </>
      }
    >
      <div className="stack">
        <p className="small secondary"><strong className="num">{request.number}</strong> · {request.type_name} · {request.requester_name}</p>
        <Textarea label={meta.label} required={required} value={comments} error={error} hint={meta.hint} maxLength={2000} autoFocus
                  onChange={(e) => { setComments(e.target.value); setError('') }} />
        {decision === 'approve' && (
          <div className="stack-sm">
            <span className="field-label">Your e-signature</span>
            <SignatureField purpose="Approving applies this signature to the request and its printed form." />
          </div>
        )}
      </div>
    </Modal>
  )
}

// ------------------------------------------------------------ OPS processing

const STATUS_ACTION: Partial<Record<Status, string>> = {
  OPS_RECEIVED: 'Receive Request',
  PROCESSING: 'Start Processing',
  INTERNAL_APPROVAL: 'Send for Internal Approval',
  FOR_FINANCE: 'Send to Finance',
  COMPLETED: 'Mark Completed',
}

export function OpsStatusModal({ request, status, onClose }: { request: RequestDetail; status: Status; onClose: () => void }) {
  const toast = useToast()
  const refresh = useRefreshRequest(request.id)
  const [remarks, setRemarks] = useState('')
  const mutation = useMutation({
    mutationFn: () => requestsApi.opsStatus(request.id, status, remarks.trim()),
    onSuccess: (fresh) => {
      refresh(fresh)
      toast.success(`${request.number} is now ${STATUS_META[status].label}.`)
      onClose()
    },
    onError: (error) => toast.error(error),
  })
  const label = request.status === 'FOR_FINANCE' && status === 'PROCESSING' ? 'Return to Processing' : STATUS_ACTION[status] ?? STATUS_META[status].label
  return (
    <Modal title={label} onClose={onClose}
           footer={<>
             <Button onClick={onClose} disabled={mutation.isPending}>Cancel</Button>
             <Button variant="primary" loading={mutation.isPending} onClick={() => mutation.mutate()}>{label}</Button>
           </>}>
      <div className="stack">
        <p className="small secondary">
          {status === 'INTERNAL_APPROVAL'
            ? <><strong className="num">{request.number}</strong> is marked as processed and goes to the next approver. The last approval, by Finance, completes it.</>
            : <><strong className="num">{request.number}</strong> will move to <strong>{STATUS_META[status].label}</strong>. The requester is notified.</>}
        </p>
        <Textarea label="Remarks (optional)" value={remarks} maxLength={2000} onChange={(e) => setRemarks(e.target.value)} />
      </div>
    </Modal>
  )
}

export function opsActionLabel(current: Status, next: Status): string {
  return current === 'FOR_FINANCE' && next === 'PROCESSING' ? 'Return to Processing' : STATUS_ACTION[next] ?? STATUS_META[next].label
}

export function OpsPanel({ request, lookups }: { request: RequestDetail; lookups: Lookups }) {
  const toast = useToast()
  const refresh = useRefreshRequest(request.id)
  const [form, setForm] = useState({
    ops_assignee: request.ops_assignee ?? '', priority: request.priority, po_number: request.po_number,
    rr_number: request.rr_number, invoice_number: request.invoice_number, posted: request.posted,
  })
  const mutation = useMutation({
    mutationFn: () => requestsApi.opsUpdate(request.id, { ...form, ops_assignee: form.ops_assignee || null }),
    onSuccess: (fresh) => {
      refresh(fresh)
      toast.success('Processing details saved.')
    },
    onError: (error) => toast.error(error),
  })
  const save = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate()
  }
  return (
    <Card title="OPS Processing">
      <form className="stack" onSubmit={save}>
        <Select label="Assigned processor" placeholder="Unassigned" value={form.ops_assignee}
                onChange={(e) => setForm({ ...form, ops_assignee: e.target.value })}
                options={lookups.ops_users.map((u) => ({ value: u.id, label: u.name }))} />
        <Select label="Priority" value={form.priority} options={PRIORITY_OPTIONS}
                onChange={(e) => setForm({ ...form, priority: e.target.value as typeof form.priority })} />
        <Input label="PO Number" value={form.po_number} maxLength={40} onChange={(e) => setForm({ ...form, po_number: e.target.value })} />
        <Input label="RR Number" value={form.rr_number} maxLength={40} onChange={(e) => setForm({ ...form, rr_number: e.target.value })} />
        <Input label="Invoice Number" value={form.invoice_number} maxLength={40} onChange={(e) => setForm({ ...form, invoice_number: e.target.value })} />
        {request.form_kind === 'PAYMENT' && (
          <Segmented label="Posted" value={form.posted === null ? null : form.posted ? 'yes' : 'no'}
                     options={[{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }]}
                     onChange={(value) => setForm({ ...form, posted: value === 'yes' })} />
        )}
        <Button type="submit" loading={mutation.isPending}>Save processing details</Button>
      </form>
    </Card>
  )
}

// ------------------------------------------------------------ Timeline

export function ApprovalTimeline({ requestId }: { requestId: string }) {
  const { data, isLoading } = useQuery({ queryKey: ['requests', 'timeline', requestId], queryFn: () => requestsApi.timeline(requestId) })
  const [showPrevious, setShowPrevious] = useState(false)
  return (
    <Card title="Approval Timeline">
      {isLoading || !data ? <LoadingState /> : data.current.length === 0 ? (
        <EmptyState title="Not submitted yet" message="The approval route appears here once the request is submitted." />
      ) : (
        <div className="stack">
          <Timeline nodes={data.current} />
          {data.previous.length > 0 && (
            <div className="stack-sm">
              <Button size="sm" variant="ghost" onClick={() => setShowPrevious((v) => !v)}>
                {showPrevious ? 'Hide' : 'Show'} earlier submissions ({data.previous.length})
              </Button>
              {showPrevious && [...data.previous].reverse().map((cycle) => (
                <div key={cycle.cycle} className="stack-sm" style={{ paddingTop: 12, borderTop: '1px solid var(--border)' }}>
                  <span className="xs muted strong">Submission {cycle.cycle} · {cycle.outcome} {formatDateTime(cycle.ended_at)}</span>
                  <Timeline nodes={cycle.nodes} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ------------------------------------------------------------ Tabs content

export function CommentsPanel({ requestId }: { requestId: string }) {
  const client = useQueryClient()
  const toast = useToast()
  const [body, setBody] = useState('')
  const { data, isLoading } = useQuery({ queryKey: ['requests', 'comments', requestId], queryFn: () => requestsApi.comments(requestId) })
  const mutation = useMutation({
    mutationFn: () => requestsApi.addComment(requestId, body.trim()),
    onSuccess: () => {
      setBody('')
      void client.invalidateQueries({ queryKey: ['requests'] })
    },
    onError: (error) => toast.error(error),
  })
  if (isLoading) return <LoadingState />
  return (
    <div className="stack">
      {data?.length ? (
        <div>
          {data.map((comment) => (
            <div key={comment.id} className="comment">
              <Avatar name={comment.author_name} />
              <div>
                <div className="small"><strong>{comment.author_name}</strong> <span className="muted">· {timeAgo(comment.created_at)}</span></div>
                <div className="small pre-wrap">{comment.body}</div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState icon={<MessageSquare size={20} />} title="No comments yet" message="Ask a question or add context for the people handling this request." />
      )}
      <form className="stack-sm" onSubmit={(event) => { event.preventDefault(); if (body.trim()) mutation.mutate() }}>
        <Textarea label="Add a comment" hideLabel placeholder="Add a comment…" value={body} maxLength={4000} onChange={(e) => setBody(e.target.value)} />
        <div><Button type="submit" variant="primary" icon={<Send size={15} />} loading={mutation.isPending} disabled={!body.trim()}>Post comment</Button></div>
      </form>
    </div>
  )
}

/** Audit trail of the request, newest first. `limit` shows only the latest entries. */
export function ActivityPanel({ requestId, limit }: { requestId: string; limit?: number }) {
  const { data, isLoading } = useQuery({ queryKey: ['requests', 'audit', requestId], queryFn: () => requestsApi.auditLog(requestId) })
  if (isLoading || !data) return <LoadingState />
  if (!data.length) return <EmptyState title="No activity recorded" />
  return (
    <ol className="stack-sm">
      {(limit ? data.slice(0, limit) : data).map((entry) => (
        <li key={entry.id} style={{ paddingBottom: 10, borderBottom: '1px solid var(--border)' }}>
          <div className="xs muted num">{formatDateTime(entry.created_at)}</div>
          <div className="small">{entry.message}</div>
          {entry.previous_status && entry.new_status && entry.previous_status !== entry.new_status && (
            <div className="xs secondary">
              {STATUS_META[entry.previous_status as Status]?.label ?? entry.previous_status} → {STATUS_META[entry.new_status as Status]?.label ?? entry.new_status}
            </div>
          )}
          {entry.comments && <div className="timeline-note small pre-wrap">{entry.comments}</div>}
          {entry.ip_address && <div className="xs muted">{entry.ip_address} · {entry.user_agent}</div>}
        </li>
      ))}
    </ol>
  )
}

const EMAIL_TONE: Record<string, Tone> = { SENT: 'success', FAILED: 'danger', PENDING: 'warning', NOT_SENT: 'neutral' }
const EMAIL_LABEL: Record<string, string> = { SENT: 'Email sent', FAILED: 'Email failed', PENDING: 'Email pending', NOT_SENT: 'In-app only' }

export function NotificationsPanel({ requestId }: { requestId: string }) {
  const { data, isLoading } = useQuery({ queryKey: ['requests', 'notifications', requestId], queryFn: () => requestsApi.notifications(requestId) })
  if (isLoading || !data) return <LoadingState />
  if (!data.length) return <EmptyState icon={<Mail size={20} />} title="No notifications sent yet" />
  return (
    <ol className="stack-sm">
      {data.map((note) => (
        <li key={note.id} className="row between" style={{ paddingBottom: 10, borderBottom: '1px solid var(--border)', alignItems: 'flex-start' }}>
          <div>
            <div className="small">{note.title}</div>
            <div className="xs muted">To {note.recipient_name} · {formatDateTime(note.created_at)}</div>
          </div>
          <Badge tone={EMAIL_TONE[note.email_status]} plain>{EMAIL_LABEL[note.email_status]}</Badge>
        </li>
      ))}
    </ol>
  )
}

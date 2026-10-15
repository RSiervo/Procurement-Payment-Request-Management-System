import { useQuery } from '@tanstack/react-query'
import { Check, CircleDashed, ShieldAlert, ShieldCheck, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import { PortalLogo } from '../../components/PortalLogo'
import { LoadingState } from '../../components/ui'
import type { NodeState, Status } from '../../types'
import { formatDate, formatDateTime, STATUS_META } from '../../utils/format'

interface Verification {
  company_name: string
  currency_symbol: string
  number: string
  type_name: string
  status: Status
  status_display: string
  total_amount: string
  department_name: string
  requester_name: string
  submitted_at: string | null
  completed_at: string | null
  steps: { label: string; state: NodeState; detail: string; actor: string; at: string | null }[]
}

const STEP_ICON: Partial<Record<NodeState, ReactNode>> = {
  done: <Check size={13} strokeWidth={3} />,
  rejected: <X size={13} strokeWidth={3} />,
  returned: <X size={13} strokeWidth={3} />,
}

/**
 * Where a printed form's QR code leads. Open to anyone holding the paper: it confirms the
 * form matches a real request and shows who signed, without the request's contents.
 */
export function VerifyPage() {
  const { id = '' } = useParams()
  const query = useQuery({ queryKey: ['verify', id], queryFn: () => api.get<Verification>(`/verify/${id}/`), retry: false })
  const data = query.data

  if (query.isLoading) return <div className="verify-page"><LoadingState /></div>
  if (!data) {
    const missing = query.error instanceof ApiError && query.error.status === 404
    return (
      <div className="verify-page">
        <div className="verify-card">
          <div className="verify-banner" data-tone="danger"><ShieldAlert size={22} />
            <div>
              <strong>{missing ? 'No matching request' : 'Could not check this form'}</strong>
              <span>{missing ? 'This code does not match any submitted request. Treat the form as unverified.' : 'Check your connection to the office network and scan again.'}</span>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const amount = `${data.currency_symbol}${Number(data.total_amount).toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  const closed = data.status === 'REJECTED' || data.status === 'CANCELLED'
  return (
    <div className="verify-page">
      <div className="verify-card">
        <div className="verify-brand"><PortalLogo size={30} /><span>{data.company_name}</span></div>
        <div className="verify-banner" data-tone={closed ? 'danger' : 'success'}>
          {closed ? <ShieldAlert size={22} /> : <ShieldCheck size={22} />}
          <div>
            <strong>{closed ? `Genuine request, but ${data.status_display.toLowerCase()}` : 'Genuine request'}</strong>
            <span>This form matches a record in the Procurement &amp; Payment Portal. Compare the details below with the paper.</span>
          </div>
        </div>

        <dl className="verify-facts">
          <div><dt>Request</dt><dd className="strong">{data.number}</dd></div>
          <div><dt>Type</dt><dd>{data.type_name}</dd></div>
          <div><dt>Status</dt><dd><span className={`badge badge-${STATUS_META[data.status].tone} badge-plain`}>{data.status_display}</span></dd></div>
          <div><dt>Amount</dt><dd className="strong num">{amount}</dd></div>
          <div><dt>Requested by</dt><dd>{data.requester_name}</dd></div>
          <div><dt>Department</dt><dd>{data.department_name}</dd></div>
          <div><dt>Submitted</dt><dd>{data.submitted_at ? formatDate(data.submitted_at) : '—'}</dd></div>
          <div><dt>Completed</dt><dd>{data.completed_at ? formatDate(data.completed_at) : 'Not yet'}</dd></div>
        </dl>

        <h2 className="verify-heading">Sign-offs</h2>
        <ol className="verify-steps">
          {data.steps.map((step, index) => (
            <li key={`${step.label}-${index}`} data-state={step.state}>
              <span className="verify-step-mark">{STEP_ICON[step.state] ?? <CircleDashed size={13} />}</span>
              <div>
                <span className="strong">{step.label}</span>
                <span className="xs muted"> · {step.detail}</span>
                {(step.actor || step.at) && (
                  <div className="xs secondary">{step.actor}{step.actor && step.at ? ' · ' : ''}{step.at ? formatDateTime(step.at) : ''}</div>
                )}
              </div>
            </li>
          ))}
        </ol>

        <p className="verify-note">
          Checked {formatDateTime(new Date().toISOString())}. Items, attachments and comments are not shown here.{' '}
          <Link to={`/requests/${id}`}>Sign in to open the full request</Link> if you have access.
        </p>
      </div>
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ArrowDown, ArrowUp, Link2, Plus, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { authApi } from '../../../api/misc'
import { requestsApi } from '../../../api/requests'
import {
  Button, Card, DatePicker, EmptyState, Input, LoadingState, Modal, MoneyInput, Segmented, Select, StatusBadge, Textarea,
} from '../../../components/ui'
import { useDebounced } from '../../../hooks/useLookups'
import type { Colleague, FormKind, LinkablePr, Lookups, Me, RequestLine, RoutePreview } from '../../../types'
import { formatDate, money, PRIORITY_OPTIONS, quantity, todayIso } from '../../../utils/format'
import { emptyLine, lineAmount, totalAmount, type DraftForm, type FieldErrors } from '../../../utils/validation'
import { WorkflowFlow } from '../WorkflowFlow'

export const LINE_NOUN: Record<FormKind, { title: string; one: string; add: string }> = {
  ITEMS: { title: 'Items', one: 'Item', add: 'Add item' },
  PAYMENT: { title: 'Payment Particulars', one: 'Particular', add: 'Add particular' },
  EXPENSE: { title: 'Expenses', one: 'Expense', add: 'Add expense' },
}

type Update = (patch: Partial<DraftForm>) => void

// ---------------------------------------------------------------- Details

function PrPicker({ onPick, onClose, advance, requester }: {
  onPick: (pr: LinkablePr) => void
  onClose: () => void
  /** Choose a cash advance to liquidate instead of a PR to pay against. */
  advance?: boolean
  requester?: string | null
}) {
  const [search, setSearch] = useState('')
  const term = useDebounced(search)
  const { data, isLoading } = useQuery({
    queryKey: ['requests', 'linkable', term, advance ? 'advance' : 'pr', requester ?? ''],
    queryFn: () => requestsApi.linkable(term, advance ? 'advance' : undefined, requester),
  })
  const noun = advance ? 'cash advance' : 'PR'
  return (
    <Modal title={advance ? 'Choose the Cash Advance' : 'Link to Existing PR'} onClose={onClose} wide>
      <div className="stack">
        <Input label={`Search by ${noun} number`} hideLabel type="search" placeholder={`Search by ${noun} number`} value={search}
               onChange={(e) => setSearch(e.target.value)} />
        {isLoading ? <LoadingState /> : !data?.length ? (
          advance
            ? <EmptyState title="No cash advance to liquidate" message="Only approved cash advances that have no liquidation yet are listed." />
            : <EmptyState title="No approved purchase requisitions found" message="Only approved PRs you have access to can be linked." />
        ) : (
          <div className="stack-sm">
            {data.map((pr) => (
              <button key={pr.id} type="button" className="choice" style={{ flexDirection: 'column', gap: 4 }} onClick={() => onPick(pr)}>
                <div className="row between" style={{ width: '100%' }}>
                  <strong className="num">{pr.number}</strong>
                  <strong className="num">{money(pr.total_amount)}</strong>
                </div>
                <span className="small secondary">{pr.summary || 'No items'}</span>
                <div className="row-wrap">
                  <StatusBadge status={pr.status} />
                  <span className="xs muted">{pr.requester_name} · {pr.department_name}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}

/** Find a colleague with a portal account, to prepare a request in their name. */
function ColleaguePicker({ onPick, onClose }: { onPick: (person: Colleague) => void; onClose: () => void }) {
  const [search, setSearch] = useState('')
  const term = useDebounced(search).trim()
  const { data, isLoading } = useQuery({ queryKey: ['colleagues', term], queryFn: () => authApi.colleagues(term), enabled: term.length >= 2 })
  return (
    <Modal title="Request for Someone Else" onClose={onClose}>
      <div className="stack">
        <p className="small secondary">
          You fill in the request; they review and submit it, because it carries their e-signature. It follows their department's approval route.
        </p>
        <Input label="Colleague" type="search" placeholder="Type a name or email…" value={search} onChange={(e) => setSearch(e.target.value)} />
        {term.length < 2 ? null : isLoading ? <LoadingState /> : !data?.length ? (
          <EmptyState title="Nobody found" message="Only colleagues who have signed in to the portal can be chosen." />
        ) : (
          <div className="stack-sm">
            {data.map((person) => (
              <button key={person.id} type="button" className="choice" style={{ flexDirection: 'column', gap: 2 }} onClick={() => onPick(person)}>
                <strong>{person.name}</strong>
                <span className="xs muted">{[person.position, person.department_name].filter(Boolean).join(' · ') || person.email}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}

export function DetailsStep({ form, update, errors, lookups, user, linkedPr, onLink, onRequester, canChangeRequester }: {
  form: DraftForm
  update: Update
  errors: FieldErrors
  lookups: Lookups
  user: Me
  linkedPr: { number: string; total_amount: string } | null
  onLink: (pr: LinkablePr | null) => void
  onRequester: (person: Colleague | null) => void
  canChangeRequester: boolean
}) {
  const [picking, setPicking] = useState(false)
  const [choosing, setChoosing] = useState(false)
  const isPr = form.typeCode === 'PR'
  const isLiquidation = form.typeCode === 'LIQ'
  const paying = form.formKind !== 'ITEMS'
  const onBehalf = !!form.requesterId && form.requesterId !== user.id

  return (
    <div className="stack">
      <Card title="Request Information">
        <div className="stack">
          <dl className="dl">
            <div><dt>Request number</dt><dd className="muted">Assigned when submitted</dd></div>
            <div><dt>Request date</dt><dd>{formatDate(todayIso())}</dd></div>
            <div>
              <dt>{form.formKind === 'EXPENSE' ? 'Employee' : 'Requested by'}</dt>
              <dd>
                {onBehalf ? form.requesterName : user.name}
                {onBehalf && <span className="muted"> · prepared by you</span>}
                {canChangeRequester && (
                  <button type="button" className="link-button" onClick={() => (onBehalf ? onRequester(null) : setChoosing(true))}>
                    {onBehalf ? 'Change back to myself' : 'Request for someone else'}
                  </button>
                )}
              </dd>
            </div>
          </dl>
          <div className="form-grid">
            <Select label="Department" required value={form.department} error={errors.department}
                    onChange={(e) => update({ department: e.target.value })} placeholder="Select department"
                    options={lookups.departments.map((d) => ({ value: d.id, label: d.name }))} />
            <Select label="Priority" value={form.priority} onChange={(e) => update({ priority: e.target.value })}
                    options={PRIORITY_OPTIONS} />
            {isPr && (
              <DatePicker label="Date Needed" required min={todayIso()} value={form.dateNeeded} error={errors.dateNeeded}
                          onChange={(e) => update({ dateNeeded: e.target.value })} />
            )}
            {paying && (
              <Input label="Payable To" required value={form.payableTo} error={errors.payableTo} maxLength={200}
                     list={form.formKind === 'PAYMENT' ? 'vendor-names' : undefined}
                     hint={form.formKind === 'EXPENSE' ? 'Usually yourself.'
                       : lookups.vendors.length ? 'Start typing and pick the supplier from the list when it is there.' : 'Supplier or person to be paid.'}
                     onChange={(e) => update({ payableTo: e.target.value })} />
            )}
            {paying && <datalist id="vendor-names">{lookups.vendors.map((name) => <option key={name} value={name} />)}</datalist>}
            <Textarea label={form.formKind === 'EXPENSE' ? 'Purpose / Business Justification' : 'Purpose / Remarks'}
                      className="span-2" required={form.formKind === 'EXPENSE'} value={form.purpose} error={errors.purpose}
                      maxLength={4000} onChange={(e) => update({ purpose: e.target.value })} />
          </div>
        </div>
      </Card>

      {isLiquidation && (
        <Card title="Cash Advance Being Liquidated">
          <div className="stack-sm">
            {linkedPr ? (
              <div className="callout callout-action">
                <div className="row between">
                  <div>
                    <div className="xs muted">Cash advance</div>
                    <strong className="num">{linkedPr.number}</strong> · <span className="num">{money(linkedPr.total_amount)}</span> advanced
                  </div>
                  <Button size="sm" variant="ghost" icon={<X size={14} />} onClick={() => onLink(null)}>Change</Button>
                </div>
              </div>
            ) : (
              <div className="row-wrap">
                <Button variant="primary" icon={<Link2 size={16} />} onClick={() => setPicking(true)}>Choose the cash advance</Button>
                <span className="small muted">List your receipts in the next step; the balance is worked out for you.</span>
              </div>
            )}
            {errors.sourceRequest && <span className="field-error" role="alert">{errors.sourceRequest}</span>}
          </div>
        </Card>
      )}

      {paying && !isLiquidation && (
        <Card title="Reference Information">
          <div className="stack">
            {linkedPr ? (
              <div className="callout callout-action">
                <div className="row between">
                  <div>
                    <div className="xs muted">Linked purchase requisition</div>
                    <strong className="num">{linkedPr.number}</strong> · <span className="num">{money(linkedPr.total_amount)}</span>
                  </div>
                  <Button size="sm" variant="ghost" icon={<X size={14} />} onClick={() => onLink(null)}>Remove</Button>
                </div>
              </div>
            ) : (
              <div className="row-wrap">
                <Button icon={<Link2 size={16} />} onClick={() => setPicking(true)}>Link to Existing PR</Button>
                <span className="small muted">Fills in the department and particulars for you.</span>
              </div>
            )}
            <div className="form-grid">
              {!linkedPr && (
                <Input label="PR Number" value={form.prReference} maxLength={40} hint="Only if the PR is not in this system."
                       onChange={(e) => update({ prReference: e.target.value })} />
              )}
              <Input label="PO Number" value={form.poNumber} maxLength={40} onChange={(e) => update({ poNumber: e.target.value })} />
              <Input label="RR Number" value={form.rrNumber} maxLength={40} onChange={(e) => update({ rrNumber: e.target.value })} />
              <Input label="Invoice Number" value={form.invoiceNumber} maxLength={40}
                     onChange={(e) => update({ invoiceNumber: e.target.value })} />
              {form.formKind === 'PAYMENT' && (
                <Segmented label="Posted" value={form.posted === null ? null : form.posted ? 'yes' : 'no'}
                           options={[{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }]}
                           onChange={(value) => update({ posted: value === 'yes' })} />
              )}
            </div>
          </div>
        </Card>
      )}
      {picking && (
        <PrPicker advance={isLiquidation} requester={onBehalf ? form.requesterId : null} onClose={() => setPicking(false)}
                  onPick={(pr) => { onLink(pr); setPicking(false) }} />
      )}
      {choosing && <ColleaguePicker onClose={() => setChoosing(false)} onPick={(person) => { onRequester(person); setChoosing(false) }} />}
    </div>
  )
}

// ---------------------------------------------------------------- Lines

export function LinesStep({ form, update, errors, formError, lookups }: {
  form: DraftForm
  update: Update
  errors: FieldErrors[]
  formError?: string
  lookups: Lookups
}) {
  const kind = form.formKind
  const noun = LINE_NOUN[kind]
  const symbol = lookups.config.currency_symbol
  const setLine = (index: number, patch: Partial<RequestLine>) =>
    update({ lines: form.lines.map((line, i) => (i === index ? { ...line, ...patch } : line)) })
  const move = (index: number, by: number) => {
    const lines = [...form.lines]
    const [line] = lines.splice(index, 1)
    lines.splice(index + by, 0, line)
    update({ lines })
  }

  return (
    <div className="stack">
      {formError && <div className="alert alert-danger" role="alert"><AlertCircle size={16} />{formError}</div>}
      {form.lines.map((line, index) => {
        const e = errors[index] ?? {}
        return (
          <div key={index} className="line-card">
            <div className="line-head">
              <span>{noun.one} {index + 1}</span>
              <div className="row" style={{ gap: 0 }}>
                <button type="button" className="icon-btn" aria-label="Move up" disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={16} /></button>
                <button type="button" className="icon-btn" aria-label="Move down" disabled={index === form.lines.length - 1} onClick={() => move(index, 1)}><ArrowDown size={16} /></button>
                <button type="button" className="icon-btn" aria-label={`Remove ${noun.one.toLowerCase()} ${index + 1}`}
                        onClick={() => update({ lines: form.lines.filter((_, i) => i !== index) })}><Trash2 size={16} /></button>
              </div>
            </div>
            <div className="line-grid" data-kind={kind}>
              {kind === 'ITEMS' && (
                <>
                  <Input label="Quantity" type="number" inputMode="decimal" min="0" step="any" required value={line.quantity ?? ''}
                         error={e.quantity} onChange={(ev) => setLine(index, { quantity: ev.target.value })} />
                  <MoneyInput label="Est. unit cost" prefix={symbol} value={line.unit_cost ?? ''} error={e.unit_cost}
                              hint="Optional" onChange={(ev) => setLine(index, { unit_cost: ev.target.value })} />
                  <Input label="Description" className="wide" required maxLength={500} value={line.description} error={e.description}
                         placeholder="e.g. Laptop, 14-inch" onChange={(ev) => setLine(index, { description: ev.target.value })} />
                  <Input label="Purpose / Remarks" className="wide" maxLength={500} value={line.remarks}
                         placeholder="e.g. For new employee" onChange={(ev) => setLine(index, { remarks: ev.target.value })} />
                </>
              )}
              {kind === 'PAYMENT' && (
                <>
                  <Input label="Particulars" className="wide" required maxLength={500} value={line.description} error={e.description}
                         onChange={(ev) => setLine(index, { description: ev.target.value })} />
                  <Input label="Remarks" maxLength={500} value={line.remarks} onChange={(ev) => setLine(index, { remarks: ev.target.value })} />
                  <MoneyInput label="Amount" prefix={symbol} required value={line.amount ?? ''} error={e.amount}
                              onChange={(ev) => setLine(index, { amount: ev.target.value })} />
                </>
              )}
              {kind === 'EXPENSE' && (
                <>
                  <DatePicker label="Expense date" required max={todayIso()} value={line.expense_date ?? ''} error={e.expense_date}
                              onChange={(ev) => setLine(index, { expense_date: ev.target.value })} />
                  <Select label="Category" required placeholder="Select" value={line.category ?? ''} error={e.category}
                          onChange={(ev) => setLine(index, { category: ev.target.value })}
                          options={lookups.expense_categories.map((c) => ({ value: c.id, label: c.name }))} />
                  <Input label="Description" className="wide" required maxLength={500} value={line.description} error={e.description}
                         onChange={(ev) => setLine(index, { description: ev.target.value })} />
                  <MoneyInput label="Amount" prefix={symbol} className="wide" required value={line.amount ?? ''} error={e.amount}
                              onChange={(ev) => setLine(index, { amount: ev.target.value })} />
                </>
              )}
            </div>
            {kind === 'ITEMS' && lineAmount(kind, line) > 0 && (
              <div className="small secondary right" style={{ marginTop: 8 }}>Estimated: <strong className="num">{money(lineAmount(kind, line))}</strong></div>
            )}
          </div>
        )
      })}
      <Button icon={<Plus size={16} />} onClick={() => update({ lines: [...form.lines, emptyLine()] })}>
        {form.lines.length ? `Add another ${noun.one.toLowerCase()}` : noun.add}
      </Button>
      <div className="total-row">
        <span className="strong">{kind === 'EXPENSE' ? 'Total Reimbursement' : kind === 'ITEMS' ? 'Estimated Total' : 'Total'}</span>
        <strong>{money(totalAmount(kind, form.lines))}</strong>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- Review

export function ReviewStep({ form, lookups, user, attachmentCount, route, routeLoading, issues, advance }: {
  /** For a liquidation: the cash advance it accounts for. */
  advance?: { number: string; total_amount: string } | null
  form: DraftForm
  lookups: Lookups
  user: Me
  attachmentCount: number
  route: RoutePreview | null | undefined
  routeLoading: boolean
  issues: string[]
}) {
  const type = lookups.request_types.find((t) => t.code === form.typeCode)
  const department = lookups.departments.find((d) => d.id === form.department)
  const kind = form.formKind
  return (
    <div className="stack">
      {issues.length > 0 && (
        <div className="alert alert-danger" role="alert">
          <AlertCircle size={16} />
          <div>
            <strong>Please fix the following before submitting:</strong>
            <ul style={{ listStyle: 'disc', paddingLeft: 18, marginTop: 4 }}>{issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
          </div>
        </div>
      )}
      <Card title="Request Summary">
        <dl className="dl">
          <div><dt>Request type</dt><dd>{type?.name}</dd></div>
          <div><dt>Requester</dt><dd>{form.requesterName || user.name}</dd></div>
          <div><dt>Department</dt><dd>{department?.name ?? '—'}</dd></div>
          {form.typeCode === 'PR' && <div><dt>Date needed</dt><dd>{formatDate(form.dateNeeded)}</dd></div>}
          {kind !== 'ITEMS' && <div><dt>Payable to</dt><dd>{form.payableTo || '—'}</dd></div>}
          <div><dt>{LINE_NOUN[kind].title}</dt><dd>{form.lines.length}</dd></div>
          <div><dt>Amount</dt><dd className="strong num">{money(totalAmount(kind, form.lines))}</dd></div>
          {advance && (() => {
            const balance = Number(advance.total_amount) - totalAmount(kind, form.lines)
            return (
              <>
                <div><dt>Cash advance {advance.number}</dt><dd className="num">{money(advance.total_amount)}</dd></div>
                <div>
                  <dt>{balance > 0 ? 'To be returned' : balance < 0 ? 'To be reimbursed' : 'Balance'}</dt>
                  <dd className="strong num">{balance === 0 ? 'Fully accounted for' : money(Math.abs(balance))}</dd>
                </div>
              </>
            )
          })()}
          <div><dt>Attachments</dt><dd>{attachmentCount}</dd></div>
          {form.purpose && <div className="span-all"><dt>Purpose</dt><dd className="pre-wrap">{form.purpose}</dd></div>}
        </dl>
      </Card>
      <Card title={LINE_NOUN[kind].title} flush>
        <div className="record-list">
          {form.lines.map((line, index) => (
            <div key={index} className="record-card">
              <div className="row between">
                <span className="strong small">
                  {kind === 'ITEMS' && `${quantity(line.quantity) || '?'} × `}{line.description || 'No description'}
                </span>
                {lineAmount(kind, line) > 0 && <span className="num small">{money(lineAmount(kind, line))}</span>}
              </div>
              <div className="xs muted">
                {kind === 'EXPENSE'
                  ? `${formatDate(line.expense_date)} · ${lookups.expense_categories.find((c) => c.id === line.category)?.name ?? 'No category'}`
                  : line.remarks}
              </div>
            </div>
          ))}
        </div>
      </Card>
      <Card title="Approval Workflow">
        {routeLoading ? <LoadingState label="Working out the approval route…" /> : route ? (
          <div className="stack-sm">
            <p className="small secondary">Based on the type, department and amount, this request will follow <strong>{route.name}</strong>.</p>
            <WorkflowFlow steps={route.steps.map((s) => ({ name: s.name, detail: s.approver, afterOps: s.after_ops }))} ops={route.requires_ops_processing} />
          </div>
        ) : (
          <div className="alert alert-warning"><AlertCircle size={16} />No approval workflow is configured for this request yet. Please contact an administrator before submitting.</div>
        )}
      </Card>
    </div>
  )
}

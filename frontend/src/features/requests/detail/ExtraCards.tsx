import { Download, FilePlus2, FileText } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, downloadFile, openFile } from '../../../api/client'
import { requestsApi } from '../../../api/requests'
import { Badge, Button, ButtonLink, Card, Input } from '../../../components/ui'
import { useToast } from '../../../hooks/useToast'
import type { Lookups, RequestDetail } from '../../../types'
import { formatDate, money } from '../../../utils/format'

/** Purchase order for an approved requisition: OPS names the supplier and issues it; everyone can print it. */
export function PurchaseOrderCard({ request, lookups, onChanged }: {
  request: RequestDetail
  lookups: Lookups | undefined
  onChanged: (fresh: RequestDetail) => void
}) {
  const toast = useToast()
  const issued = !!request.po_date
  const canIssue = request.permissions.can_issue_po
  const [supplier, setSupplier] = useState(request.payable_to)
  const [terms, setTerms] = useState(request.po_terms)
  const [editing, setEditing] = useState(!issued)
  const [busy, setBusy] = useState<'save' | 'file' | null>(null)
  const [error, setError] = useState('')
  if (!issued && !canIssue) return null

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setBusy('save')
    setError('')
    try {
      const fresh = await requestsApi.issuePurchaseOrder(request.id, supplier, terms)
      onChanged(fresh)
      setEditing(false)
      toast.success(`Purchase order ${fresh.po_number} ${issued ? 'updated' : 'issued'}.`)
    } catch (err) {
      if (err instanceof ApiError && err.field('supplier')) setError(err.field('supplier')!)
      else toast.error(err)
    } finally {
      setBusy(null)
    }
  }

  const file = async (download: boolean) => {
    setBusy('file')
    try {
      if (download) await downloadFile(requestsApi.purchaseOrderPath(request.id), `${request.po_number}.pdf`)
      else await openFile(requestsApi.purchaseOrderPath(request.id))
    } catch (err) {
      toast.error(err)
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card title="Purchase Order" actions={issued && <Badge tone="success" plain>Issued</Badge>}>
      <div className="stack-sm">
        {issued && (
          <dl className="dl">
            <div><dt>PO number</dt><dd className="strong num">{request.po_number}</dd></div>
            <div><dt>Date</dt><dd>{formatDate(request.po_date)}</dd></div>
            <div className="span-all"><dt>Supplier</dt><dd>{request.payable_to}</dd></div>
            {request.po_terms && <div className="span-all"><dt>Terms</dt><dd>{request.po_terms}</dd></div>}
            {request.po_issued_by_name && <div className="span-all"><dt>Issued by</dt><dd>{request.po_issued_by_name}</dd></div>}
          </dl>
        )}
        {canIssue && editing && (
          <form className="stack-sm" onSubmit={save}>
            {!issued && <p className="small secondary">Name the supplier to turn this requisition into a numbered purchase order.</p>}
            <Input label="Supplier" required list="po-vendor-names" maxLength={200} value={supplier} error={error}
                   hint={lookups?.vendors.length ? 'Pick from the vendor list when the supplier is there.' : undefined}
                   onChange={(e) => setSupplier(e.target.value)} />
            <datalist id="po-vendor-names">{(lookups?.vendors ?? []).map((name) => <option key={name} value={name} />)}</datalist>
            <Input label="Terms" maxLength={300} placeholder="For example: 30 days, deliver to head office" value={terms}
                   onChange={(e) => setTerms(e.target.value)} />
            <div className="row-wrap">
              <Button type="submit" variant="primary" size="sm" loading={busy === 'save'}>{issued ? 'Save changes' : 'Issue purchase order'}</Button>
              {issued && <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>}
            </div>
          </form>
        )}
        {issued && !editing && (
          <div className="row-wrap">
            <Button size="sm" icon={<FileText size={15} />} loading={busy === 'file'} onClick={() => void file(false)}>Open</Button>
            <Button size="sm" icon={<Download size={15} />} disabled={busy === 'file'} onClick={() => void file(true)}>Download</Button>
            {canIssue && <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>Change supplier or terms</Button>}
          </div>
        )}
      </div>
    </Card>
  )
}

/** For a cash advance: whether it has been liquidated. For a liquidation: what was advanced, spent, and owed. */
export function AdvanceCard({ request }: { request: RequestDetail }) {
  const advance = request.advance
  if (!advance) return null

  if (advance.role === 'liquidation') {
    const settled = Number(advance.to_return) === 0 && Number(advance.to_reimburse) === 0
    return (
      <Card title="Liquidation of Cash Advance">
        <dl className="dl">
          <div><dt>Cash advance</dt><dd><Link className="num" to={`/requests/${advance.advance_id}`}>{advance.advance_number}</Link></dd></div>
          <div><dt>Advanced</dt><dd className="num">{money(advance.advance_amount)}</dd></div>
          <div><dt>Spent (this liquidation)</dt><dd className="num">{money(advance.spent)}</dd></div>
          <div>
            <dt>{settled ? 'Balance' : Number(advance.to_return) > 0 ? 'To be returned by the employee' : 'To be reimbursed to the employee'}</dt>
            <dd className="strong num" style={{ color: settled ? undefined : `var(--tone-${Number(advance.to_return) > 0 ? 'warning' : 'info'})` }}>
              {settled ? 'Fully accounted for' : money(Number(advance.to_return) > 0 ? advance.to_return : advance.to_reimburse)}
            </dd>
          </div>
        </dl>
      </Card>
    )
  }

  const canLiquidate = request.permissions.is_owner && !advance.liquidation
    && ['APPROVED', 'OPS_RECEIVED', 'PROCESSING', 'INTERNAL_APPROVAL', 'FOR_FINANCE', 'COMPLETED'].includes(request.status)
  return (
    <Card title="Liquidation" actions={<Badge tone={advance.liquidated ? 'success' : advance.released ? 'warning' : 'neutral'} plain>
      {advance.liquidated ? 'Liquidated' : advance.released ? 'Not yet liquidated' : 'Not released yet'}</Badge>}>
      <div className="stack-sm">
        {advance.liquidation ? (
          <Link to={`/requests/${advance.liquidation.id}`} className="flow-node" style={{ color: 'inherit', textDecoration: 'none' }}>
            <div className="row between"><strong className="num small">{advance.liquidation.number}</strong><span className="num small">{money(advance.liquidation.total_amount)}</span></div>
            <div className="xs muted">Liquidation · {advance.liquidation.status_display}</div>
          </Link>
        ) : (
          <p className="small secondary">
            A cash advance must be accounted for with receipts once the money has been spent.
            {advance.released ? ' This one has been released and is waiting for its liquidation.' : ''}
          </p>
        )}
        {canLiquidate && (
          <ButtonLink to={`/requests/new?type=LIQ&advance=${encodeURIComponent(request.number)}`} icon={<FilePlus2 size={16} />}>
            Liquidate this advance
          </ButtonLink>
        )}
      </div>
    </Card>
  )
}

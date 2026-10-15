import { Link } from 'react-router-dom'
import type { RequestChecks } from '../../../types'
import { formatDate, money } from '../../../utils/format'

/** What the automatic checks found: possible double payment, budget position, unknown payee. */
export function ChecksPanel({ checks }: { checks: RequestChecks }) {
  const { duplicates, budget, unlisted_payee: unlisted } = checks
  return (
    <>
      {duplicates.length > 0 && (
        <div className="callout callout-danger">
          <strong>Possible duplicate payment</strong>
          <span className="small">Check that this is not the same payment before it goes any further:</span>
          <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
            {duplicates.map((other) => (
              <li key={other.number}>
                {other.id ? <Link to={`/requests/${other.id}`}>{other.number}</Link> : <span className="strong">{other.number}</span>}
                {' · '}{money(other.total_amount)} · {other.status_display}
                {other.submitted_at ? ` · submitted ${formatDate(other.submitted_at)}` : ''} — {other.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {budget?.over && (
        <div className="callout callout-danger">
          <strong>Over the {budget.year} budget of {budget.department}</strong>
          {budget.amount !== undefined ? (
            <span className="small">
              {money(budget.used!)} committed against a budget of {money(budget.amount)}, including {money(budget.this_request!)} for
              this request: {money(String(-Number(budget.remaining)))} over.
            </span>
          ) : (
            <span className="small">This request takes the department past its budget for the year. The approvers are shown the figures.</span>
          )}
        </div>
      )}
      {budget && !budget.over && budget.amount !== undefined && (
        <div className="callout">
          <strong>Within the {budget.year} budget of {budget.department}</strong>
          <span className="small secondary">
            {money(budget.used!)} of {money(budget.amount)} committed, including this request. {money(budget.remaining!)} remains.
          </span>
        </div>
      )}
      {checks.open_advances.length > 0 && (
        <div className="callout callout-warning">
          <strong>Earlier cash advance{checks.open_advances.length === 1 ? '' : 's'} not yet liquidated</strong>
          <span className="small">
            The requester still has to account for {checks.open_advances.map((a) => `${a.number} (${money(a.total_amount)})`).join(', ')}.
          </span>
        </div>
      )}
      {unlisted && (
        <div className="callout callout-warning">
          <strong>Payee is not in the vendor list</strong>
          <span className="small">Confirm the payee is genuine. An administrator can add regular suppliers under Administration → Vendors.</span>
        </div>
      )}
    </>
  )
}

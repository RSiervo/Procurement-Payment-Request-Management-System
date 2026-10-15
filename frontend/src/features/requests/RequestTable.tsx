import { AlertTriangle } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Avatar, Badge, ButtonLink, DataTable, EmptyState, PriorityBadge, StatusBadge, TypeTag, type Column,
} from '../../components/ui'
import type { RequestSummary } from '../../types'
import { formatDate, formatTime, money, timeAgo } from '../../utils/format'

interface Props<T extends RequestSummary> {
  rows: T[] | undefined
  loading?: boolean
  empty?: ReactNode
  /** Show who raised each request (hide on "my requests" lists). */
  showRequester?: boolean
  /** Extra columns placed before the status column. */
  extra?: Column<T>[]
  /** Row-level buttons; rendered in the last column and at the bottom of each phone card. */
  actions?: (row: T) => ReactNode
  /** Drop the least important column when the table sits in a narrow card. */
  compact?: boolean
  /** Hide "Current Approver" where it would say the same thing on every row. */
  hideHandler?: boolean
}

/** "Department Head · Maria Santos" → the person with their step underneath; a bare role stays one line. */
function Handler({ value }: { value: string }) {
  if (!value) return <span className="muted">—</span>
  const [step, person] = value.split(' · ')
  return (
    <span className="row nowrap" style={{ gap: 10 }}>
      <Avatar name={person ?? step} />
      <span>
        {person ?? step}
        {person && <span className="cell-sub">{step}</span>}
      </span>
    </span>
  )
}

export function OverdueBadge({ row }: { row: RequestSummary }) {
  if (!row.is_overdue) return null
  return <Badge tone="danger" plain><AlertTriangle size={12} />Overdue</Badge>
}

export function RequestTable<T extends RequestSummary>({ rows, loading, empty, showRequester, extra = [], actions, compact, hideHandler }: Props<T>) {
  const columns: Column<T>[] = [
    { header: 'Request #', render: (row) => <Link className="strong num nowrap" to={`/requests/${row.id}`}>{row.number}</Link> },
    { header: 'Type', render: (row) => <TypeTag code={row.type_code} name={row.type_name} /> },
    ...(showRequester
      ? [{
          header: 'Requester',
          render: (row: T) => <span className="nowrap">{row.requester_name}<span className="cell-sub">{row.department_name}</span></span>,
        }]
      : []),
    {
      header: 'Description',
      dropWhenNarrow: 'second',
      render: (row) => <span className="truncate" style={{ display: 'block', maxWidth: 136 }} title={row.summary}>{row.summary || <span className="muted">—</span>}</span>,
    },
    { header: 'Amount', align: 'right', render: (row) => <span className="num nowrap">{money(row.total_amount)}</span> },
    ...extra,
    {
      header: 'Status',
      render: (row) => (
        <div className="row-wrap">
          <StatusBadge status={row.status} />
          <PriorityBadge priority={row.priority} />
          <OverdueBadge row={row} />
        </div>
      ),
    },
    ...(hideHandler ? [] : [{ header: 'Current Approver', render: (row: T) => <Handler value={row.current_handler} /> }]),
    ...(compact
      ? []
      : [{
          header: 'Last Updated',
          dropWhenNarrow: 'first' as const,
          render: (row: T) => <span className="nowrap secondary">{formatDate(row.updated_at)}<span className="cell-sub">{formatTime(row.updated_at)}</span></span>,
        }]),
    {
      header: 'Action',
      align: 'right' as const,
      render: (row: T) => (
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          {actions ? actions(row) : <ButtonLink size="sm" className="btn-outline" to={`/requests/${row.id}`}>View</ButtonLink>}
        </div>
      ),
    },
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      loading={loading}
      rowKey={(row) => row.id}
      rowHref={(row) => `/requests/${row.id}`}
      empty={empty ?? <EmptyState title="No requests found" message="Try changing the filters, or create a new request." />}
      card={(row) => (
        <>
          <div className="row between">
            <span className="strong num">{row.number}</span>
            <span className="strong num">{money(row.total_amount)}</span>
          </div>
          <div className="row" style={{ gap: 10 }}>
            <TypeTag code={row.type_code} name={row.type_name} />
            <span className="small secondary truncate">{row.summary || row.type_name}</span>
          </div>
          {showRequester && <div className="xs muted">{row.requester_name} · {row.department_name}</div>}
          <div className="row-wrap">
            <StatusBadge status={row.status} />
            <PriorityBadge priority={row.priority} />
            <OverdueBadge row={row} />
          </div>
          <div className="xs muted">
            {row.current_handler ? `With ${row.current_handler} · ` : ''}Updated {timeAgo(row.updated_at)}
          </div>
          {extra.map((column) => (
            <div key={column.header} className="xs secondary">{column.header}: {column.render(row)}</div>
          ))}
          {actions && (
            <div className="row" style={{ marginTop: 4 }} onClick={(event) => { event.preventDefault(); event.stopPropagation() }}>
              {actions(row)}
            </div>
          )}
        </>
      )}
    />
  )
}

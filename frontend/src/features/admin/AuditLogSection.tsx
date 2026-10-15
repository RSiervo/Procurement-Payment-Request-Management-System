import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { downloadFile } from '../../api/client'
import { adminApi } from '../../api/misc'
import { Badge, Button, Card, DataTable, DatePicker, EmptyState, Input, Pagination, Select } from '../../components/ui'
import { useDebounced } from '../../hooks/useLookups'
import { useToast } from '../../hooks/useToast'
import type { AuditRow } from '../../types'
import { formatDateTime } from '../../utils/format'

const label = (action: string) => action.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase())

/** Everything the portal has recorded: who did what, when, and from where. Read-only. */
export function AuditLogSection() {
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({ action: '', date_from: '', date_to: '' })
  const [page, setPage] = useState(1)
  const [exporting, setExporting] = useState(false)
  const term = useDebounced(search)
  const query = { search: term, ...filters }
  const log = useQuery({
    queryKey: ['admin', 'audit-log', query, page],
    queryFn: () => adminApi.auditLog({ ...query, page }),
    placeholderData: keepPreviousData,
  })
  const set = (patch: Partial<typeof filters>) => {
    setFilters((current) => ({ ...current, ...patch }))
    setPage(1)
  }

  const exportLog = async () => {
    setExporting(true)
    try {
      await downloadFile('/audit-log/export/', 'audit-log.xlsx', { ...query, file_format: 'xlsx' })
    } catch (error) {
      toast.error(error)
    } finally {
      setExporting(false)
    }
  }

  const what = (row: AuditRow) => (
    <div>
      <div>{row.message}</div>
      {row.comments && <div className="xs secondary pre-wrap">“{row.comments}”</div>}
    </div>
  )
  const request = (row: AuditRow) =>
    row.request_id && row.request_number ? <Link className="num nowrap" to={`/requests/${row.request_id}`}>{row.request_number}</Link> : <span className="muted">—</span>

  return (
    <Card flush title="Audit Log"
          actions={<Button size="sm" icon={<Download size={15} />} loading={exporting} onClick={() => void exportLog()}>Export to Excel</Button>}>
      <div className="stack-sm" style={{ padding: 16, borderBottom: '1px solid var(--border)' }}>
        <p className="small secondary">
          Every significant action is recorded here and can never be changed or deleted. Search by person, request number,
          wording or IP address.
        </p>
        <div className="filters">
          <Input label="Search" type="search" placeholder="Name, request number, text…" value={search}
                 onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
          <Select label="Action" placeholder="All actions" value={filters.action} onChange={(e) => set({ action: e.target.value })}
                  options={(log.data?.actions ?? []).map((action) => ({ value: action, label: label(action) }))} />
          <DatePicker label="From" value={filters.date_from} onChange={(e) => set({ date_from: e.target.value })} />
          <DatePicker label="To" value={filters.date_to} onChange={(e) => set({ date_to: e.target.value })} />
        </div>
      </div>
      <DataTable
        rows={log.data?.results}
        loading={log.isLoading}
        rowKey={(row) => row.id}
        empty={<EmptyState title="Nothing matches" message="Try a different search or a wider date range." />}
        columns={[
          { header: 'When', render: (row) => <span className="nowrap">{formatDateTime(row.created_at)}</span> },
          { header: 'Who', render: (row) => <span className="strong">{row.actor_name}</span> },
          { header: 'Action', render: (row) => <Badge plain>{label(row.action)}</Badge> },
          { header: 'Request', render: request },
          { header: 'What happened', render: what },
          { header: 'IP address', render: (row) => <span className="num xs muted">{row.ip_address ?? '—'}</span>, dropWhenNarrow: 'first' },
        ]}
        card={(row) => (
          <div className="stack-sm" style={{ gap: 4 }}>
            <div className="row between"><span className="strong">{row.actor_name}</span><Badge plain>{label(row.action)}</Badge></div>
            {what(row)}
            <div className="xs muted">{formatDateTime(row.created_at)}{row.request_number ? ` · ${row.request_number}` : ''}{row.ip_address ? ` · ${row.ip_address}` : ''}</div>
          </div>
        )}
      />
      {log.data && <Pagination page={page} pageSize={20} count={log.data.count} onChange={setPage} />}
    </Card>
  )
}

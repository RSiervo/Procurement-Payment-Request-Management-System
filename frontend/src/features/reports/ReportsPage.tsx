import { useQuery } from '@tanstack/react-query'
import { Banknote, CheckCircle2, Clock, Download, FileText, Hourglass, Sparkles, TrendingDown, TrendingUp, X, XCircle } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { downloadFile } from '../../api/client'
import { reportsApi, type ReportFilters } from '../../api/misc'
import { Button, Card, DatePicker, EmptyState, ErrorState, LoadingState, Select } from '../../components/ui'
import { CountUp } from '../../components/ui/CountUp'
import { useLookups } from '../../hooks/useLookups'
import { errorMessage, useToast } from '../../hooks/useToast'
import type { ReportSummary, Status } from '../../types'
import { money, STATUS_META, typeColor } from '../../utils/format'
import { ClickBars, Funnel, TrendChart, type Metric } from './charts'

const REPORTS = [
  ['all_requests', 'All Requests'], ['by_department', 'Requests by Department'], ['by_type', 'Requests by Type'],
  ['by_status', 'Requests by Status'], ['monthly', 'Monthly Requests'], ['pending_approvals', 'Pending Approvals'],
  ['processing_time', 'Processing Time'], ['completed', 'Completed Requests'], ['rejected', 'Rejected Requests'],
  ['reimbursements', 'Reimbursements'], ['by_payee', 'Spend by Payee'],
].map(([value, label]) => ({ value, label }))

const PERIODS = [
  { value: 'month', label: 'This month' },
  { value: '30', label: 'Last 30 days' },
  { value: 'quarter', label: 'This quarter' },
  { value: 'year', label: 'This year' },
  { value: 'all', label: 'All time' },
  { value: 'custom', label: 'Custom' },
] as const
type Period = (typeof PERIODS)[number]['value']

const iso = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`

function periodDates(period: Period, custom: { from: string; to: string }): { date_from?: string; date_to?: string } {
  const today = new Date()
  const from = (date: Date) => ({ date_from: iso(date), date_to: iso(today) })
  if (period === 'month') return from(new Date(today.getFullYear(), today.getMonth(), 1))
  if (period === '30') return from(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29))
  if (period === 'quarter') return from(new Date(today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1))
  if (period === 'year') return from(new Date(today.getFullYear(), 0, 1))
  if (period === 'custom') return { date_from: custom.from || undefined, date_to: custom.to || undefined }
  return {}
}

/** Change against the period just before, as a small coloured pill. `goodWhenUp` decides the colour. */
function Delta({ current, previous, goodWhenUp = true }: { current: number; previous: number | undefined; goodWhenUp?: boolean }) {
  if (previous === undefined) return null
  if (previous === 0) return current > 0 ? <span className="an-delta" data-tone="neutral">New</span> : null
  const change = Math.round(((current - previous) / previous) * 100)
  if (change === 0) return <span className="an-delta" data-tone="neutral">No change</span>
  const up = change > 0
  return (
    <span className="an-delta" data-tone={up === goodWhenUp ? 'good' : 'bad'} title={`Previous period: ${previous.toLocaleString()}`}>
      {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}{Math.abs(change)}%
    </span>
  )
}

function Kpi({ icon, tone, label, value, hint, delta }: {
  icon: ReactNode; tone: string; label: string; value: ReactNode; hint?: ReactNode; delta?: ReactNode
}) {
  return (
    <div className="an-kpi" data-tone={tone}>
      <span className="an-kpi-icon">{icon}</span>
      <div className="an-kpi-body">
        <span className="an-kpi-label">{label}</span>
        <span className="an-kpi-value">{value}</span>
        <span className="an-kpi-foot">{delta}{hint && <span className="muted">{hint}</span>}</span>
      </div>
    </div>
  )
}

/** A few plain sentences about what stands out in the numbers. */
function highlights(data: ReportSummary): string[] {
  const found: string[] = []
  const total = Number(data.totals.amount)
  const topDept = [...data.by_department].sort((a, b) => Number(b.amount) - Number(a.amount))[0]
  if (topDept && total > 0 && data.by_department.length > 1) {
    found.push(`${topDept.label} accounts for ${Math.round((Number(topDept.amount) / total) * 100)}% of the amount requested.`)
  }
  const peak = [...data.trend.points].sort((a, b) => b.count - a.count)[0]
  if (peak && peak.count > 0 && data.trend.points.length > 1) {
    found.push(`Busiest ${data.trend.unit}: ${peak.label}, with ${peak.count} request${peak.count === 1 ? '' : 's'}.`)
  }
  const slowest = [...data.processing_time].filter((row) => row.avg_days_to_complete !== null)
    .sort((a, b) => b.avg_days_to_complete! - a.avg_days_to_complete!)[0]
  if (slowest && slowest.avg_days_to_complete! >= 1) found.push(`${slowest.label} takes longest to complete: ${slowest.avg_days_to_complete} days on average.`)
  const requests = Number(data.totals.requests)
  if (requests > 0 && Number(data.totals.rejected) > 0) {
    found.push(`${Math.round((Number(data.totals.rejected) / requests) * 100)}% of requests were rejected.`)
  }
  const over = data.budgets.filter((b) => Number(b.used) > Number(b.amount))
  if (over.length) found.push(`${over.map((b) => b.label).join(', ')} ${over.length === 1 ? 'is' : 'are'} over budget for ${over[0].year}.`)
  return found.slice(0, 4)
}

export function ReportsPage() {
  const lookups = useLookups()
  const toast = useToast()
  const [period, setPeriod] = useState<Period>('year')
  const [custom, setCustom] = useState({ from: '', to: '' })
  const [pick, setPick] = useState<{ type?: string; department?: string; status?: Status }>({})
  const [metric, setMetric] = useState<Metric>('count')
  const [report, setReport] = useState('all_requests')
  const [exporting, setExporting] = useState<string | null>(null)

  const filters: ReportFilters = useMemo(() => ({ ...periodDates(period, custom), ...pick }), [period, custom, pick])
  const summary = useQuery({ queryKey: ['reports', filters], queryFn: () => reportsApi.summary(filters), placeholderData: (previous) => previous })
  // Choosing the value that is already chosen clears it.
  const toggle = <K extends keyof typeof pick>(key: K, value: (typeof pick)[K]) =>
    setPick((current) => ({ ...current, [key]: current[key] === value ? undefined : value }))

  const exportAs = async (format: 'csv' | 'xlsx' | 'pdf') => {
    setExporting(format)
    try {
      await downloadFile('/reports/export/', `${report}.${format}`, { ...filters, report, file_format: format })
    } catch (error) {
      toast.error(error)
    } finally {
      setExporting(null)
    }
  }

  const data = summary.data
  const requests = Number(data?.totals.requests ?? 0)
  const completed = Number(data?.totals.completed ?? 0)
  const done = data?.processing_time.filter((row) => row.avg_days_to_complete !== null && row.completed > 0) ?? []
  const doneCount = done.reduce((sum, row) => sum + row.completed, 0)
  const avgDays = doneCount ? (done.reduce((sum, row) => sum + row.avg_days_to_complete! * row.completed, 0) / doneCount).toFixed(1) : '—'
  const typeName = (code: string) => lookups?.request_types.find((t) => t.code === code)?.name ?? code
  const departmentName = (id: string) => lookups?.departments.find((d) => d.id === id)?.name ?? 'Department'
  const chips = [
    pick.type && { key: 'type' as const, label: typeName(pick.type) },
    pick.department && { key: 'department' as const, label: departmentName(pick.department) },
    pick.status && { key: 'status' as const, label: STATUS_META[pick.status].label },
  ].filter((chip): chip is { key: 'type' | 'department' | 'status'; label: string } => !!chip)
  const maxDays = Math.max(1, ...(data?.processing_time ?? []).map((row) => row.avg_days_to_complete ?? row.avg_days_to_approve ?? 0))

  return (
    <div className="page reports-page analytics">
      <div className="page-header">
        <div>
          <h1>Reports</h1>
          <p>Submitted requests for the chosen period. Click any bar to narrow everything to it.</p>
        </div>
        <div className="an-controls">
          {/* On phones the period is a dropdown beside the measure switch; the row of buttons below is for wider screens. */}
          <Select label="Period" hideLabel className="an-period-select" value={period} options={[...PERIODS]}
                  onChange={(e) => setPeriod(e.target.value as Period)} />
          <div className="segmented an-metric" role="group" aria-label="Measure by">
            <button type="button" aria-pressed={metric === 'count'} onClick={() => setMetric('count')}>Requests</button>
            <button type="button" aria-pressed={metric === 'amount'} onClick={() => setMetric('amount')}>Amount</button>
          </div>
        </div>
      </div>

      <div className="an-toolbar">
        <div className="segmented an-periods" role="group" aria-label="Period">
          {PERIODS.map((option) => (
            <button key={option.value} type="button" aria-pressed={period === option.value} onClick={() => setPeriod(option.value)}>{option.label}</button>
          ))}
        </div>
        {period === 'custom' && (
          <div className="an-custom">
            <DatePicker label="From" value={custom.from} onChange={(e) => setCustom({ ...custom, from: e.target.value })} />
            <DatePicker label="To" value={custom.to} onChange={(e) => setCustom({ ...custom, to: e.target.value })} />
          </div>
        )}
        {chips.length > 0 && (
          <div className="an-chips">
            <span className="xs muted">Showing only</span>
            {chips.map((chip) => (
              <button key={chip.key} type="button" className="an-chip" onClick={() => setPick((current) => ({ ...current, [chip.key]: undefined }))}
                      aria-label={`Remove filter ${chip.label}`}>{chip.label}<X size={12} /></button>
            ))}
            {chips.length > 1 && <button type="button" className="an-chip-clear" onClick={() => setPick({})}>Clear all</button>}
          </div>
        )}
      </div>

      {summary.isLoading ? <LoadingState /> : summary.isError || !data ? (
        <ErrorState message={errorMessage(summary.error)} onRetry={() => void summary.refetch()} />
      ) : (
        <div className="an-body" data-refreshing={summary.isFetching || undefined}>
          <div className="an-kpis">
            <Kpi tone="info" icon={<FileText size={18} />} label="Requests" value={<CountUp value={requests} />}
                 delta={<Delta current={requests} previous={data.previous?.requests} />} hint={data.previous ? 'vs previous period' : undefined} />
            <Kpi tone="purple" icon={<Banknote size={18} />} label="Total amount" value={money(data.totals.amount)}
                 delta={<Delta current={Number(data.totals.amount)} previous={data.previous ? Number(data.previous.amount) : undefined} />}
                 hint={requests ? `${money(Number(data.totals.amount) / requests)} average` : undefined} />
            <Kpi tone="success" icon={<CheckCircle2 size={18} />} label="Completed" value={<CountUp value={completed} />}
                 delta={<Delta current={completed} previous={data.previous?.completed} />}
                 hint={requests ? `${Math.round((completed / requests) * 100)}% of requests` : undefined} />
            <Kpi tone="warning" icon={<Hourglass size={18} />} label="Pending approval" value={<CountUp value={Number(data.totals.pending_approval)} />}
                 hint="waiting on an approver" />
            <Kpi tone="danger" icon={<XCircle size={18} />} label="Rejected" value={<CountUp value={Number(data.totals.rejected)} />}
                 hint={requests ? `${Math.round((Number(data.totals.rejected) / requests) * 100)}% of requests` : undefined} />
            <Kpi tone="neutral" icon={<Clock size={18} />} label="Avg. days to complete" value={avgDays} hint="submission to completion" />
          </div>

          {requests === 0 ? (
            <Card>
              <EmptyState title="No requests in this period"
                          action={period !== 'all' || chips.length ? <Button onClick={() => { setPeriod('all'); setPick({}) }}>Show all time</Button> : undefined} />
            </Card>
          ) : (
            <>
              {highlights(data).length > 0 && (
                <div className="an-highlights">
                  {highlights(data).map((text) => <span key={text} className="an-highlight"><Sparkles size={13} />{text}</span>)}
                </div>
              )}

              <div className="an-grid an-grid-wide">
                <Card title={metric === 'count' ? `Requests per ${data.trend.unit}` : `Amount per ${data.trend.unit}`}>
                  <TrendChart trend={data.trend} metric={metric} />
                </Card>
                <Card title="How far requests got">
                  <Funnel funnel={data.funnel} />
                  <p className="field-hint" style={{ marginTop: 10 }}>Each stage as a share of everything submitted in the period.</p>
                </Card>
              </div>

              <div className="an-grid an-grid-3">
                <Card title="By department">
                  <ClickBars noun="department" metric={metric} selected={pick.department} onSelect={(key) => toggle('department', key)}
                             rows={data.by_department.map((row) => ({ ...row, key: row.key! }))} />
                </Card>
                <Card title="By type">
                  <ClickBars noun="type" metric={metric} selected={pick.type} onSelect={(key) => toggle('type', key)}
                             rows={data.by_type.map((row) => ({ ...row, key: row.key!, color: typeColor(row.key!) }))} />
                </Card>
                <Card title="By status">
                  <ClickBars noun="status" metric={metric} selected={pick.status} onSelect={(key) => toggle('status', key as Status)}
                             rows={data.by_status.map((row) => ({ ...row, key: row.status, color: `var(--tone-${STATUS_META[row.status].tone})` }))} />
                </Card>
              </div>

              <div className="an-grid an-grid-3">
                <Card title="Top payees">
                  {data.by_payee.length === 0 ? <EmptyState title="No payments in this period" /> : (
                    <ClickBars noun="payee" metric="amount" color="var(--type-rfp)"
                               rows={data.by_payee.slice(0, 8).map((row) => ({ ...row, key: row.label, note: row.listed ? undefined : 'not listed' }))} />
                  )}
                </Card>
                <Card title="Processing time (days)">
                  <div className="an-times">
                    {data.processing_time.map((row) => (
                      <div key={row.label} className="an-time">
                        <span className="an-bar-head"><span className="truncate">{row.label}</span><span className="xs muted">{row.completed} completed</span></span>
                        {([['To approve', row.avg_days_to_approve, 'var(--tone-info)'], ['To complete', row.avg_days_to_complete, 'var(--tone-success)']] as const).map(([label, days, color]) => (
                          <span key={label} className="an-time-row" title={`${label}: ${days ?? 'no data'}`}>
                            <span className="xs muted">{label}</span>
                            <span className="an-bar-track"><span className="an-bar-fill" style={{ width: `${((days ?? 0) / maxDays) * 100}%`, background: color }} /></span>
                            <span className="num strong">{days ?? '—'}</span>
                          </span>
                        ))}
                      </div>
                    ))}
                  </div>
                </Card>
                <Card title={data.budgets.length ? `Budget use ${data.budgets[0].year}` : 'Budget use'}>
                  {data.budgets.length === 0 ? (
                    <EmptyState title="No budgets to show" message="Budgets are set under Administration → Budgets and are visible to administrators and Finance." />
                  ) : (
                    <div className="an-bars">
                      {data.budgets.map((budget) => {
                        const percent = Number(budget.amount) > 0 ? Math.round((Number(budget.used) / Number(budget.amount)) * 100) : 0
                        const tone = percent > 100 ? 'danger' : percent >= 80 ? 'warning' : 'success'
                        return (
                          <button key={budget.key} type="button" className="an-bar" aria-pressed={pick.department === budget.key}
                                  title={`${budget.label}: ${money(budget.used)} of ${money(budget.amount)}`} onClick={() => toggle('department', budget.key)}>
                            <span className="an-bar-head">
                              <span className="truncate">{budget.label}</span>
                              <span className="num strong" style={{ color: `var(--tone-${tone})` }}>{percent}%</span>
                            </span>
                            <span className="an-bar-track"><span className="an-bar-fill" style={{ width: `${Math.min(percent, 100)}%`, background: `var(--tone-${tone})` }} /></span>
                            <span className="xs muted">{money(budget.used)} of {money(budget.amount)}</span>
                          </button>
                        )
                      })}
                    </div>
                  )}
                </Card>
              </div>
            </>
          )}
        </div>
      )}

      <Card title="Export">
        <div className="an-export">
          <Select label="Report" value={report} onChange={(e) => setReport(e.target.value)} options={REPORTS} />
          <div className="row-wrap">
            {(['csv', 'xlsx', 'pdf'] as const).map((format) => (
              <Button key={format} icon={<Download size={16} />} loading={exporting === format} disabled={!!exporting} onClick={() => void exportAs(format)}>
                {format === 'xlsx' ? 'Excel' : format.toUpperCase()}
              </Button>
            ))}
          </div>
          <p className="xs muted">Exports use the period and filters chosen above.</p>
        </div>
      </Card>
    </div>
  )
}

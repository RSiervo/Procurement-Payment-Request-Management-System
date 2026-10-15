import { useId, useState } from 'react'
import type { ReportSummary } from '../../types'
import { money } from '../../utils/format'

export type Metric = 'count' | 'amount'

const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 })
const W = 640
const H = 230
const PAD = { top: 12, right: 14, bottom: 26, left: 44 }
const TICKS = 4

function niceMax(value: number): number {
  for (let magnitude = 1; ; magnitude *= 10) {
    for (const step of [1, 2, 5]) {
      if (step * magnitude * TICKS >= value) return step * magnitude * TICKS
    }
  }
}

/** Requests or amount over the period, as a filled line. Hover or focus a point for both figures. */
export function TrendChart({ trend, metric }: { trend: ReportSummary['trend']; metric: Metric }) {
  const id = useId()
  const [active, setActive] = useState<number | null>(null)
  const points = trend.points
  const value = (index: number) => Number(points[index][metric])
  const max = niceMax(Math.max(1, ...points.map((_, index) => value(index))))
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const x = (index: number) => PAD.left + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW)
  const y = (amount: number) => PAD.top + innerH - (amount / max) * innerH
  const line = points.map((_, index) => `${index ? 'L' : 'M'}${x(index)},${y(value(index))}`).join(' ')
  const area = `${line} L${x(points.length - 1)},${PAD.top + innerH} L${x(0)},${PAD.top + innerH} Z`
  const band = innerW / Math.max(points.length - 1, 1)
  const labelEvery = Math.ceil(points.length / 7)

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`${metric === 'count' ? 'Requests' : 'Amount'} per ${trend.unit}, ${points.length} ${trend.unit}s`}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--accent)" stopOpacity="0.28" />
            <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {Array.from({ length: TICKS + 1 }, (_, i) => (max / TICKS) * i).map((tick) => (
          <g key={tick}>
            <line className="chart-grid-line" x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} />
            <text className="chart-axis-text" x={PAD.left - 8} y={y(tick) + 4} textAnchor="end">{compact.format(tick)}</text>
          </g>
        ))}
        {points.map((point, index) => (points.length - 1 - index) % labelEvery === 0 && (
          <text key={point.date} className="chart-axis-text" x={x(index)} y={H - 6} textAnchor="middle">{point.label}</text>
        ))}
        <path key={`a-${metric}`} className="an-area" d={area} fill={`url(#${id})`} />
        <path key={`l-${metric}`} className="chart-line" pathLength={1} d={line} fill="none" stroke="var(--accent)" strokeWidth={2.2}
              strokeLinecap="round" strokeLinejoin="round" />
        {active !== null && (
          <>
            <line className="chart-crosshair" x1={x(active)} x2={x(active)} y1={PAD.top} y2={PAD.top + innerH} />
            <circle cx={x(active)} cy={y(value(active))} r={5} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />
          </>
        )}
        {points.map((point, index) => (
          <rect key={point.date} x={x(index) - band / 2} y={0} width={band} height={H} fill="transparent" tabIndex={0}
                aria-label={`${point.label}: ${point.count} requests, ${money(point.amount)}`}
                onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(index)} onBlur={() => setActive(null)} />
        ))}
      </svg>
      {active !== null && (
        <div className="chart-tooltip" data-side={active >= points.length / 2 ? 'left' : 'right'} style={{ left: `${(x(active) / W) * 100}%` }}>
          <strong>{points[active].label}</strong>
          <div className="chart-tooltip-row"><span>Requests</span><span className="num strong">{points[active].count}</span></div>
          <div className="chart-tooltip-row"><span>Amount</span><span className="num strong">{money(points[active].amount)}</span></div>
        </div>
      )}
    </div>
  )
}

export interface BarRow {
  key: string
  label: string
  count: number
  amount: string | number
  color?: string
  note?: string
}

/** A ranked list whose rows are buttons: choosing one narrows the whole page to it, choosing it again clears it. */
export function ClickBars({ rows, metric, selected, onSelect, color = 'var(--accent)', noun }: {
  rows: BarRow[]
  metric: Metric
  selected?: string
  onSelect?: (key: string) => void
  color?: string
  noun: string
}) {
  const number = (row: BarRow) => (metric === 'count' ? row.count : Number(row.amount))
  const max = Math.max(...rows.map(number), 1)
  const total = rows.reduce((sum, row) => sum + number(row), 0)
  return (
    <div className="an-bars">
      {rows.map((row, index) => {
        const share = total ? Math.round((number(row) / total) * 100) : 0
        const body = (
          <>
            <span className="an-bar-head">
              <span className="truncate">{row.label}{row.note && <span className="muted"> · {row.note}</span>}</span>
              <span className="num strong">{metric === 'count' ? row.count : money(row.amount)}<span className="muted an-bar-share"> {share}%</span></span>
            </span>
            <span className="an-bar-track">
              <span className="an-bar-fill" style={{ width: `${(number(row) / max) * 100}%`, background: row.color ?? color, animationDelay: `${index * 40}ms` }} />
            </span>
          </>
        )
        const title = `${row.label}: ${row.count} request${row.count === 1 ? '' : 's'}, ${money(row.amount)}`
        return onSelect ? (
          <button key={row.key} type="button" className="an-bar" aria-pressed={selected === row.key} title={title}
                  aria-label={`${title}. ${selected === row.key ? 'Clear this filter' : `Show only this ${noun}`}`}
                  onClick={() => onSelect(row.key)}>{body}</button>
        ) : (
          <div key={row.key} className="an-bar" title={title}>{body}</div>
        )
      })}
    </div>
  )
}

/** How far the period's requests have travelled: each stage as a share of everything submitted. */
export function Funnel({ funnel }: { funnel: ReportSummary['funnel'] }) {
  const stages = [
    { label: 'Submitted', value: funnel.submitted },
    { label: 'Approved', value: funnel.approved },
    { label: 'Processed by OPS', value: funnel.processed },
    { label: 'Completed', value: funnel.completed },
  ]
  return (
    <div className="an-funnel">
      {stages.map((stage, index) => {
        const share = funnel.submitted ? (stage.value / funnel.submitted) * 100 : 0
        return (
          <div key={stage.label} className="an-funnel-row" title={`${stage.label}: ${stage.value} of ${funnel.submitted} submitted`}>
            <span className="an-funnel-label">{stage.label}</span>
            <span className="an-funnel-track">
              <span className="an-funnel-fill" style={{ width: `${Math.max(share, stage.value ? 4 : 0)}%`, opacity: 1 - index * 0.17, animationDelay: `${index * 90}ms` }} />
            </span>
            <span className="num strong">{stage.value}</span>
            <span className="xs muted num">{Math.round(share)}%</span>
          </div>
        )
      })}
    </div>
  )
}

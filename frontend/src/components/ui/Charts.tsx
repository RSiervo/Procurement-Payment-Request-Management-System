import { useState } from 'react'
import { CountUp } from './CountUp'

export interface Series {
  key: string
  label: string
  color: string
}

interface LineChartProps {
  /** One entry per x position; `values` is keyed by series key. */
  points: { label: string; values: Record<string, number> }[]
  series: Series[]
  unit: string
}

const W = 600
const H = 250
const PAD = { top: 14, right: 16, bottom: 28, left: 30 }
const TICKS = 5

/** Smallest "round" axis maximum that is at least `value` and divides evenly into TICKS steps. */
function niceMax(value: number): number {
  const steps = [1, 2, 5]
  for (let magnitude = 1; ; magnitude *= 10) {
    for (const step of steps) {
      if (step * magnitude * TICKS >= value) return step * magnitude * TICKS
    }
  }
}

/**
 * Smooth path through the points (monotone cubic), so the curve never overshoots a
 * value or dips below zero the way a plain spline can.
 */
function smoothPath(xs: number[], ys: number[]): string {
  const n = xs.length
  if (n < 3) return xs.map((x, i) => `${i ? 'L' : 'M'}${x},${ys[i]}`).join(' ')
  const slope = xs.slice(1).map((x, i) => (ys[i + 1] - ys[i]) / (x - xs[i]))
  const tangent = xs.map((_, i) => {
    if (i === 0) return slope[0]
    if (i === n - 1) return slope[n - 2]
    return slope[i - 1] * slope[i] <= 0 ? 0 : (2 * slope[i - 1] * slope[i]) / (slope[i - 1] + slope[i])
  })
  let path = `M${xs[0]},${ys[0]}`
  for (let i = 0; i < n - 1; i++) {
    const dx = (xs[i + 1] - xs[i]) / 3
    path += ` C${xs[i] + dx},${ys[i] + tangent[i] * dx} ${xs[i + 1] - dx},${ys[i + 1] - tangent[i + 1] * dx} ${xs[i + 1]},${ys[i + 1]}`
  }
  return path
}

/**
 * Multi-series line chart on one shared axis. Identity is never colour-alone: a legend
 * is always shown, and hovering (or focusing) a column lists every series by name.
 */
export function LineChart({ points, series, unit }: LineChartProps) {
  const [active, setActive] = useState<number | null>(null)
  const max = niceMax(Math.max(1, ...points.flatMap((p) => series.map((s) => p.values[s.key] ?? 0))))
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const x = (index: number) => PAD.left + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW)
  const y = (value: number) => PAD.top + innerH - (value / max) * innerH
  const ticks = Array.from({ length: TICKS + 1 }, (_, i) => (max / TICKS) * i)
  const band = innerW / Math.max(points.length - 1, 1)
  // Long ranges: label roughly seven positions so dates never collide.
  const labelEvery = Math.ceil(points.length / 7)
  const showMarkers = points.length <= 14
  const xs = points.map((_, index) => x(index))

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${unit} per day by type, last ${points.length} days`}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="chart-grid-line" x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} />
            <text className="chart-axis-text" x={PAD.left - 10} y={y(tick) + 4} textAnchor="end">{tick}</text>
          </g>
        ))}
        {points.map((point, index) => (
          (points.length - 1 - index) % labelEvery === 0 && (
            <text key={point.label} className="chart-axis-text" x={x(index)} y={H - 6} textAnchor="middle">{point.label}</text>
          )
        ))}
        {active !== null && <line className="chart-crosshair" x1={x(active)} x2={x(active)} y1={PAD.top} y2={PAD.top + innerH} />}
        {series.map((s) => {
          const ys = points.map((p) => y(p.values[s.key] ?? 0))
          return (
            <g key={s.key}>
              <path className="chart-line" pathLength={1} d={smoothPath(xs, ys)} fill="none" stroke={s.color} strokeWidth={2} strokeLinecap="round" />
              {points.map((_, index) => (showMarkers || active === index) && (
                <circle key={index} className="chart-marker" cx={xs[index]} cy={ys[index]} r={active === index ? 5 : 3.5}
                        fill={s.color} stroke="var(--surface)" strokeWidth={2} />
              ))}
            </g>
          )
        })}
        {/* Hit targets: a full-height band per day, much larger than the marks. */}
        {points.map((point, index) => (
          <rect key={point.label} x={x(index) - band / 2} y={0} width={band} height={H} fill="transparent" tabIndex={0}
                aria-label={`${point.label}: ${series.map((s) => `${s.label} ${point.values[s.key] ?? 0}`).join(', ')}`}
                onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(index)} onBlur={() => setActive(null)} />
        ))}
      </svg>
      {active !== null && (
        <div className="chart-tooltip" data-side={active >= points.length / 2 ? 'left' : 'right'}
             style={{ left: `${(x(active) / W) * 100}%` }}>
          <strong>{points[active].label}</strong>
          {series.map((s) => (
            <div key={s.key} className="chart-tooltip-row">
              <span className="legend-item"><span className="swatch" style={{ background: s.color }} />{s.label}</span>
              <span className="num strong">{points[active].values[s.key] ?? 0}</span>
            </div>
          ))}
        </div>
      )}
      <div className="legend">
        {series.map((s) => (
          <span key={s.key} className="legend-item"><span className="swatch" style={{ background: s.color }} />{s.label}</span>
        ))}
      </div>
    </div>
  )
}

interface DonutProps {
  slices: { key: string; label: string; value: number; color: string }[]
  centerLabel: string
}

/** Share of a total across a few categories. Every slice is also listed with its count and percentage. */
export function Donut({ slices, centerLabel }: DonutProps) {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0)
  const radius = 62
  const stroke = 24
  const circumference = 2 * Math.PI * radius
  const gap = slices.filter((s) => s.value > 0).length > 1 ? 3 : 0 // surface gap between segments
  const percent = (value: number) => (total ? ((value / total) * 100).toFixed(1) : '0.0')
  let offset = 0

  return (
    <div className="donut-layout">
      <div className="donut">
        <svg viewBox="0 0 168 168" width="100%" height="100%" role="img" aria-label={`${centerLabel}: ${slices.map((s) => `${s.label} ${s.value}`).join(', ')}`}>
          <circle cx="84" cy="84" r={radius} fill="none" stroke="var(--tone-neutral-bg)" strokeWidth={stroke} />
          {total > 0 && slices.map((slice) => {
            const length = (slice.value / total) * circumference
            const dash = Math.max(length - gap, 0)
            const node = slice.value > 0 && (
              <circle key={slice.key} cx="84" cy="84" r={radius} fill="none" stroke={slice.color} strokeWidth={stroke}
                      strokeDasharray={`${dash} ${circumference - dash}`} strokeDashoffset={-offset}
                      transform="rotate(-90 84 84)">
                <title>{`${slice.label}: ${slice.value} (${percent(slice.value)}%)`}</title>
              </circle>
            )
            offset += length
            return node
          })}
        </svg>
        <div className="donut-center">
          <strong><CountUp value={total} /></strong>
          <span className="xs secondary">{centerLabel}</span>
        </div>
      </div>
      <div className="donut-legend">
        {slices.map((slice) => (
          <div key={slice.key} className="donut-legend-row">
            <span className="swatch" style={{ background: slice.color }} />
            <span>{slice.label}</span>
            <span className="xs muted"><strong className="secondary">{slice.value}</strong>&nbsp; ({percent(slice.value)}%)</span>
          </div>
        ))}
      </div>
    </div>
  )
}

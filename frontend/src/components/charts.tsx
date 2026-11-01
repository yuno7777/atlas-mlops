import type { ReactNode } from 'react'
import type { FeatureDrift } from '../api/types'
import { formatNumber } from '../lib/format'

const WIDTH = 720
const MARGIN = { top: 14, right: 14, bottom: 26, left: 40 }

function emptySvg(height: number) {
  return (
    <svg viewBox={`0 0 ${WIDTH} ${height}`} className="chart-svg" role="img" aria-label="No data">
      <line
        x1={MARGIN.left}
        y1={height - MARGIN.bottom}
        x2={WIDTH - MARGIN.right}
        y2={height - MARGIN.bottom}
        stroke="var(--grid)"
      />
      <text
        x={WIDTH / 2}
        y={height / 2 - 4}
        textAnchor="middle"
        className="chart-empty-text"
      >
        No activity in this window
      </text>
    </svg>
  )
}

function formatAxisDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(date)
}

function formatBucket(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-US', { hour: 'numeric' }).format(date)
}

function chooseTicks(length: number, max = 6): number[] {
  if (length <= max) return Array.from({ length }, (_, index) => index)
  const step = Math.ceil(length / max)
  const result: number[] = []
  for (let index = 0; index < length; index += step) result.push(index)
  if (result[result.length - 1] !== length - 1) result.push(length - 1)
  return result
}

export function ChartLegend({
  items,
}: {
  items: { label: string; tone: 'accent' | 'negative' | 'amber' | 'muted'; dashed?: boolean }[]
}) {
  return (
    <div className="chart-legend">
      {items.map((item) => (
        <span className="legend-item" key={item.label}>
          <span className={`legend-dot legend-${item.tone} ${item.dashed ? 'legend-dashed' : ''}`} />
          {item.label}
        </span>
      ))}
    </div>
  )
}

interface TrainingPoint {
  date: string
  completed: number
  failed: number
  running: number
  total: number
}

export function TrainingActivityChart({ data, height = 196 }: { data: TrainingPoint[]; height?: number }) {
  if (!data.length || data.every((point) => point.total === 0)) return emptySvg(height)
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right
  const plotHeight = height - MARGIN.top - MARGIN.bottom
  const max = Math.max(1, ...data.map((point) => point.completed + point.failed + point.running))
  const step = plotWidth / data.length
  const barWidth = Math.max(3, Math.min(22, step * 0.56))
  const ticks = [0, 0.5, 1].map((fraction) => Math.round(max * fraction))
  const xTicks = chooseTicks(data.length)

  return (
    <svg viewBox={`0 0 ${WIDTH} ${height}`} className="chart-svg" role="img" aria-label="Training runs by day">
      {ticks.map((tick, index) => {
        const y = MARGIN.top + plotHeight - (tick / max) * plotHeight
        return (
          <g key={`${index}-${tick}`}>
            <line
              x1={MARGIN.left}
              x2={WIDTH - MARGIN.right}
              y1={y}
              y2={y}
              stroke="var(--grid)"
              vectorEffect="non-scaling-stroke"
            />
            <text x={MARGIN.left - 8} y={y + 3.5} textAnchor="end" className="chart-tick">
              {tick}
            </text>
          </g>
        )
      })}
      {data.map((point, index) => {
        const x = MARGIN.left + index * step + (step - barWidth) / 2
        const runningHeight = (point.running / max) * plotHeight
        const completedHeight = (point.completed / max) * plotHeight
        const failedHeight = (point.failed / max) * plotHeight
        let cursor = MARGIN.top + plotHeight
        return (
          <g key={point.date}>
            <title>
              {formatAxisDate(point.date)}: {point.completed} completed, {point.failed} failed,{' '}
              {point.running} running
            </title>
            {completedHeight > 0 ? (
              <rect
                x={x}
                y={(cursor -= completedHeight)}
                width={barWidth}
                height={completedHeight}
                rx="1.5"
                fill="var(--chart-1)"
              />
            ) : null}
            {failedHeight > 0 ? (
              <rect
                x={x}
                y={(cursor -= failedHeight)}
                width={barWidth}
                height={failedHeight}
                rx="1.5"
                fill="var(--negative)"
              />
            ) : null}
            {runningHeight > 0 ? (
              <rect
                x={x}
                y={(cursor -= runningHeight)}
                width={barWidth}
                height={runningHeight}
                rx="1.5"
                fill="var(--chart-3)"
              />
            ) : null}
            {xTicks.includes(index) ? (
              <text
                x={MARGIN.left + index * step + step / 2}
                y={height - 8}
                textAnchor="middle"
                className="chart-tick"
              >
                {formatAxisDate(point.date)}
              </text>
            ) : null}
          </g>
        )
      })}
    </svg>
  )
}

interface TrendPoint {
  label: string
  value: number
  title?: string
}

export function LineTrend({
  data,
  height = 196,
  formatValue = (value: number) => value.toFixed(2),
  ariaLabel = 'Trend',
}: {
  data: TrendPoint[]
  height?: number
  formatValue?: (value: number) => string
  ariaLabel?: string
}) {
  if (!data.length) return emptySvg(height)
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right
  const plotHeight = height - MARGIN.top - MARGIN.bottom
  const values = data.map((point) => point.value)
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const span = rawMax - rawMin || Math.abs(rawMax) * 0.1 || 1
  const min = rawMin - span * 0.18
  const max = rawMax + span * 0.18
  const x = (index: number) =>
    data.length === 1 ? MARGIN.left + plotWidth / 2 : MARGIN.left + (index / (data.length - 1)) * plotWidth
  const y = (value: number) => MARGIN.top + plotHeight - ((value - min) / (max - min)) * plotHeight
  const path = data.map((point, index) => `${index === 0 ? 'M' : 'L'}${x(index)},${y(point.value)}`).join(' ')
  const ticks = [min + span * 0.2, min + span * 0.6, max - span * 0.2]
  const xTicks = chooseTicks(data.length)

  return (
    <svg viewBox={`0 0 ${WIDTH} ${height}`} className="chart-svg" role="img" aria-label={ariaLabel}>
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={MARGIN.left}
            x2={WIDTH - MARGIN.right}
            y1={y(tick)}
            y2={y(tick)}
            stroke="var(--grid)"
            vectorEffect="non-scaling-stroke"
          />
          <text x={MARGIN.left - 8} y={y(tick) + 3.5} textAnchor="end" className="chart-tick">
            {formatValue(tick)}
          </text>
        </g>
      ))}
      <path d={path} fill="none" stroke="var(--chart-1)" strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
      {data.map((point, index) => (
        <g key={`${point.label}-${index}`}>
          <title>{point.title ?? `${point.label}: ${formatValue(point.value)}`}</title>
          <circle cx={x(index)} cy={y(point.value)} r="3.2" fill="var(--surface)" stroke="var(--chart-1)" strokeWidth="1.6" />
          {xTicks.includes(index) ? (
            <text x={x(index)} y={height - 8} textAnchor="middle" className="chart-tick">
              {point.label}
            </text>
          ) : null}
        </g>
      ))}
    </svg>
  )
}

export function VolumeChart({ points, height = 180 }: { points: { bucket: string; predictions: number; failures: number }[]; height?: number }) {
  if (!points.length || points.every((point) => point.predictions === 0)) return emptySvg(height)
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right
  const plotHeight = height - MARGIN.top - MARGIN.bottom
  const max = Math.max(1, ...points.map((point) => point.predictions))
  const step = plotWidth / points.length
  const barWidth = Math.max(2, Math.min(18, step * 0.58))
  const xTicks = chooseTicks(points.length, 6)
  const ticks = [0, 0.5, 1].map((fraction) => Math.round(max * fraction))

  return (
    <svg viewBox={`0 0 ${WIDTH} ${height}`} className="chart-svg" role="img" aria-label="Prediction volume">
      {ticks.map((tick, index) => {
        const y = MARGIN.top + plotHeight - (tick / max) * plotHeight
        return (
          <g key={`${index}-${tick}`}>
            <line x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y} y2={y} stroke="var(--grid)" vectorEffect="non-scaling-stroke" />
            <text x={MARGIN.left - 8} y={y + 3.5} textAnchor="end" className="chart-tick">
              {formatNumber(tick)}
            </text>
          </g>
        )
      })}
      {points.map((point, index) => {
        const totalHeight = (point.predictions / max) * plotHeight
        const failureHeight = (point.failures / max) * plotHeight
        const x = MARGIN.left + index * step + (step - barWidth) / 2
        return (
          <g key={point.bucket}>
            <title>
              {formatBucket(point.bucket)}: {point.predictions} requests, {point.failures} failed
            </title>
            <rect
              x={x}
              y={MARGIN.top + plotHeight - totalHeight}
              width={barWidth}
              height={Math.max(totalHeight, point.predictions > 0 ? 2 : 0)}
              rx="1.5"
              fill="var(--chart-1)"
            />
            {failureHeight > 0 ? (
              <rect
                x={x}
                y={MARGIN.top + plotHeight - failureHeight}
                width={barWidth}
                height={failureHeight}
                rx="1.5"
                fill="var(--negative)"
              />
            ) : null}
            {xTicks.includes(index) ? (
              <text x={MARGIN.left + index * step + step / 2} y={height - 8} textAnchor="middle" className="chart-tick">
                {formatBucket(point.bucket)}
              </text>
            ) : null}
          </g>
        )
      })}
    </svg>
  )
}

export function LatencyChart({
  points,
  height = 160,
}: {
  points: { bucket: string; p95_latency_ms: number }[]
  height?: number
}) {
  return (
    <LineTrend
      data={points.map((point) => ({
        label: formatBucket(point.bucket),
        value: point.p95_latency_ms,
        title: `${formatBucket(point.bucket)}: p95 ${point.p95_latency_ms.toFixed(1)} ms`,
      }))}
      height={height}
      formatValue={(value) => `${value.toFixed(0)} ms`}
      ariaLabel="p95 prediction latency"
    />
  )
}

export function FeatureDriftList({
  features,
  threshold,
}: {
  features: FeatureDrift[]
  threshold: number
}) {
  const sorted = [...features].sort((a, b) => b.psi - a.psi)
  const max = Math.max(threshold * 1.35, ...sorted.map((feature) => feature.psi), 0.01)
  return (
    <div className="drift-list">
      {sorted.map((feature) => (
        <div className="drift-row" key={feature.feature}>
          <div className="drift-label">
            <span className="mono">{feature.feature}</span>
            <span className="drift-meta">
              {feature.kind}
              {feature.ks_pvalue !== null && feature.ks_pvalue !== undefined
                ? ` · KS p=${feature.ks_pvalue.toFixed(3)}`
                : ''}
            </span>
          </div>
          <div className="drift-track" aria-hidden="true">
            <span
              className={`drift-bar ${feature.drifted ? 'is-drifted' : ''}`}
              style={{ width: `${Math.min(100, (feature.psi / max) * 100)}%` }}
            />
            <span className="drift-threshold" style={{ left: `${Math.min(100, (threshold / max) * 100)}%` }} />
          </div>
          <span className="drift-value num">{feature.psi.toFixed(3)}</span>
        </div>
      ))}
    </div>
  )
}

export function BarList({
  items,
  formatValue = (value: number) => value.toFixed(2),
  tone = 'accent',
}: {
  items: { label: string; value: number; hint?: ReactNode }[]
  formatValue?: (value: number) => string
  tone?: 'accent' | 'muted'
}) {
  if (!items.length) return <p className="chart-empty">No data yet.</p>
  const max = Math.max(...items.map((item) => item.value), 0.0001)
  return (
    <div className="bar-list">
      {items.map((item) => (
        <div className="bar-row" key={item.label}>
          <div className="bar-row-head">
            <span className="bar-label">{item.label}</span>
            <span className="bar-value num">{formatValue(item.value)}</span>
          </div>
          <div className="bar-track">
            <span className={`bar-fill bar-${tone}`} style={{ width: `${Math.max(3, (item.value / max) * 100)}%` }} />
          </div>
          {item.hint ? <span className="bar-hint">{item.hint}</span> : null}
        </div>
      ))}
    </div>
  )
}

const METRIC_LABELS: Record<string, string> = {
  accuracy: 'Accuracy',
  precision_weighted: 'Precision',
  recall_weighted: 'Recall',
  f1_weighted: 'F1 score',
  roc_auc: 'ROC AUC',
  rmse: 'RMSE',
  mae: 'MAE',
  r2: 'R²',
  silhouette: 'Silhouette',
  davies_bouldin: 'Davies–Bouldin',
  calinski_harabasz: 'Calinski–Harabasz',
  training_duration_seconds: 'Training duration',
  loss: 'Loss',
  mse: 'MSE',
  self_accuracy: 'Self accuracy',
}

const RATIO_METRICS = new Set([
  'accuracy',
  'precision_weighted',
  'recall_weighted',
  'f1_weighted',
  'roc_auc',
])

export const PRIMARY_METRIC: Record<string, string> = {
  classification: 'accuracy',
  regression: 'r2',
  clustering: 'silhouette',
}

export function primaryMetric(problemType: string | null | undefined): string {
  return PRIMARY_METRIC[problemType ?? ''] ?? 'accuracy'
}

export function inferPrimaryMetric(metrics: Record<string, number | null | undefined>): string {
  if ('accuracy' in metrics) return 'accuracy'
  if ('r2' in metrics) return 'r2'
  if ('silhouette' in metrics) return 'silhouette'
  return Object.keys(metrics).find((key) => metrics[key] !== null && metrics[key] !== undefined) ?? 'accuracy'
}

export function metricLabel(key: string): string {
  return METRIC_LABELS[key] ?? titleCase(key.replaceAll('_', ' '))
}

export function formatMetric(key: string, value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (RATIO_METRICS.has(key)) return `${(value * 100).toFixed(1)}%`
  if (key === 'r2') return value.toFixed(3)
  if (key === 'silhouette') return value.toFixed(3)
  if (key === 'davies_bouldin' || key === 'calinski_harabasz') return value.toFixed(2)
  if (key === 'training_duration_seconds') return formatDuration(value)
  const magnitude = Math.abs(value)
  if (magnitude >= 1000) return formatNumber(value, 0)
  if (magnitude >= 100) return value.toFixed(1)
  if (magnitude >= 1) return value.toFixed(2)
  if (magnitude === 0) return '0'
  return value.toFixed(4)
}

export function formatMetricDelta(key: string, value: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  const magnitude = Math.abs(value)
  if (RATIO_METRICS.has(key)) return `${sign}${(magnitude * 100).toFixed(1)} pts`
  if (magnitude >= 1000) return `${sign}${formatNumber(magnitude, 0)}`
  if (magnitude >= 100) return `${sign}${magnitude.toFixed(1)}`
  if (magnitude >= 1) return `${sign}${magnitude.toFixed(2)}`
  return `${sign}${magnitude.toFixed(4)}`
}

export function formatNumber(value: number, digits = 0): string {
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  }).format(value)
}

export function formatCompact(value: number): string {
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(
    value,
  )
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatShare(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${value.toFixed(digits)}%`
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2)} ${units[index]}`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—'
  if (seconds < 1) return '<1s'
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  const minutes = Math.floor(seconds / 60)
  const remainder = Math.round(seconds % 60)
  if (minutes < 60) return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours}h ${rest}m` : `${hours}h`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(value))
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

export function formatClock(value: string | null | undefined): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value))
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  const delta = date.getTime() - Date.now()
  const abs = Math.abs(delta)
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 365 * 24 * 3600 * 1000],
    ['month', 30 * 24 * 3600 * 1000],
    ['week', 7 * 24 * 3600 * 1000],
    ['day', 24 * 3600 * 1000],
    ['hour', 3600 * 1000],
    ['minute', 60 * 1000],
  ]
  if (abs < 45 * 1000) return 'just now'
  const formatter = new Intl.RelativeTimeFormat('en-US', { numeric: 'auto' })
  for (const [unit, ms] of units) {
    if (abs >= ms) return formatter.format(Math.round(delta / ms), unit)
  }
  return formatter.format(Math.round(delta / 1000), 'second')
}

export function titleCase(value: string): string {
  return value
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

export function statusLabel(status: string | null | undefined): string {
  if (!status) return 'Not run'
  if (status === 'insufficient_data') return 'Insufficient data'
  if (status === 'none') return 'Unstaged'
  return titleCase(status)
}

export type PillTone = 'positive' | 'negative' | 'warning' | 'info' | 'neutral'

export function statusTone(status: string | null | undefined): PillTone {
  switch (status) {
    case 'active':
    case 'healthy':
    case 'completed':
    case 'passed':
    case 'ready':
    case 'production':
      return 'positive'
    case 'failed':
    case 'critical':
    case 'error':
      return 'negative'
    case 'warning':
    case 'staging':
      return 'warning'
    case 'running':
    case 'queued':
    case 'processing':
      return 'info'
    default:
      return 'neutral'
  }
}

export function monitoringTone(status: string | null | undefined): PillTone {
  if (status === 'healthy') return 'positive'
  if (status === 'warning') return 'warning'
  if (status === 'critical') return 'negative'
  return 'neutral'
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

export function shortId(value: string | null | undefined): string {
  if (!value) return '—'
  return value.length > 10 ? value.slice(0, 8) : value
}

export function sizeLabel(rows: number | null | undefined, columns: number | null | undefined): string {
  if (rows === null || rows === undefined) return '—'
  return `${formatNumber(rows)} × ${columns ?? '—'}`
}

export function truncate(value: string, length = 48): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value
}

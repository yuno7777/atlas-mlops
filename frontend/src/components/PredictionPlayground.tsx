import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useApi } from '../api/hooks'
import type {
  DatasetColumn,
  ExperimentDetail,
  ModelVersion,
  PredictionResponse,
  ReferenceFeature,
  ReferenceProfile,
} from '../api/types'
import { Icon } from './Icon'
import { useToast } from './ToastProvider'
import {
  CopyButton,
  EmptyState,
  ErrorBlock,
  Field,
  Input,
  LoadingBlock,
  Panel,
  SectionHeader,
  Select,
} from './ui'
import { formatNumber, formatShare } from '../lib/format'

function defaultValue(feature: DatasetColumn, reference: ReferenceFeature | undefined): string {
  if (!reference) return ''
  if (feature.kind === 'numeric') {
    return reference.mean === null || reference.mean === undefined ? '' : String(reference.mean)
  }
  const ranked = Object.entries(reference.categories ?? {}).sort((a, b) => b[1] - a[1])
  return ranked[0]?.[0] ?? ''
}

function buildDefaults(profile: ReferenceProfile): Record<string, string> {
  const next: Record<string, string> = {}
  for (const feature of profile.schema.features) {
    next[feature.name] = defaultValue(feature, profile.features[feature.name])
  }
  return next
}

export function PredictionPlayground({
  deploymentId,
  modelVersionId,
  targetColumn,
}: {
  deploymentId: string
  modelVersionId: string
  targetColumn: string | null
}) {
  const toast = useToast()
  const version = useApi<ModelVersion>(`/model-versions/${modelVersionId}`)
  const experiment = useApi<ExperimentDetail>(
    version.data ? `/experiments/${version.data.experiment_id}` : null,
  )
  const profile = experiment.data?.reference_profile ?? null
  const features = useMemo(
    () => (profile ? [...profile.schema.features] : []),
    [profile],
  )

  const [values, setValues] = useState<Record<string, string>>({})
  const [result, setResult] = useState<PredictionResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (profile) {
      setValues(buildDefaults(profile))
      setResult(null)
    }
  }, [profile])

  const setValue = (name: string, value: string) => {
    setValues((current) => ({ ...current, [name]: value }))
  }

  const reset = () => {
    if (profile) setValues(buildDefaults(profile))
    setResult(null)
    setError(null)
  }

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const record: Record<string, unknown> = {}
      for (const feature of features) {
        const raw = values[feature.name] ?? ''
        if (feature.kind === 'numeric') {
          record[feature.name] = raw.trim() === '' ? null : Number(raw)
        } else {
          record[feature.name] = raw.trim() === '' ? null : raw
        }
      }
      const response = await api.post<PredictionResponse>(
        `/predictions/${deploymentId}`,
        { records: [record] },
      )
      setResult(response)
      toast.success('Prediction returned and logged.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Prediction failed.')
    } finally {
      setSubmitting(false)
    }
  }

  if (version.error || experiment.error) {
    return (
      <ErrorBlock
        message={version.error ?? experiment.error ?? 'Could not load the model schema.'}
        onRetry={() => {
          version.reload()
          experiment.reload()
        }}
      />
    )
  }

  if (version.loading || experiment.loading) {
    return <LoadingBlock rows={6} />
  }

  if (!profile) {
    return (
      <Panel>
        <EmptyState
          compact
          icon="beaker"
          title="No reference profile"
          description="This model version has no stored training schema, so the playground cannot build an input form."
        />
      </Panel>
    )
  }

  return (
    <div className="playground-layout">
      <Panel>
        <SectionHeader
          title="Test input"
          description={
            <>
              Values start from training reference statistics. All{' '}
              <span className="num">{features.length}</span> model features are required.
            </>
          }
          action={
            <button type="button" className="btn btn-ghost btn-sm" onClick={reset}>
              <Icon name="refresh" size={14} />
              Reset defaults
            </button>
          }
        />
        <form
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <div className="playground-fields">
            {features.map((feature) => {
              const reference = profile.features[feature.name]
              if (feature.kind === 'numeric') {
                return (
                  <Field
                    key={feature.name}
                    label={<span className="mono">{feature.name}</span>}
                    htmlFor={`feature-${feature.name}`}
                    hint={
                      reference?.mean !== null && reference?.mean !== undefined
                        ? `Training mean ${formatNumber(reference.mean, 3)}`
                        : 'Numeric feature'
                    }
                  >
                    <Input
                      id={`feature-${feature.name}`}
                      type="number"
                      step="any"
                      value={values[feature.name] ?? ''}
                      onChange={(event) => setValue(feature.name, event.target.value)}
                    />
                  </Field>
                )
              }
              const categories = Object.entries(reference?.categories ?? {}).sort(
                (a, b) => b[1] - a[1],
              )
              return (
                <Field
                  key={feature.name}
                  label={<span className="mono">{feature.name}</span>}
                  htmlFor={`feature-${feature.name}`}
                  hint={`${categories.length} observed categor${categories.length === 1 ? 'y' : 'ies'}`}
                >
                  <Select
                    id={`feature-${feature.name}`}
                    value={values[feature.name] ?? ''}
                    onChange={(event) => setValue(feature.name, event.target.value)}
                  >
                    <option value="">Choose a value</option>
                    {categories.map(([category, share]) => (
                      <option key={category} value={category}>
                        {category} ({formatShare(share)})
                      </option>
                    ))}
                  </Select>
                </Field>
              )
            })}
          </div>
          <div className="playground-actions">
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              <Icon name="play" size={15} />
              {submitting ? 'Scoring…' : 'Run prediction'}
            </button>
            <span className="muted">
              Requests are logged for monitoring and can receive feedback
              {targetColumn ? ` on ${targetColumn}` : ''}.
            </span>
          </div>
        </form>
      </Panel>

      <div className="stack-gap-16">
        {error ? <div className="error-block">{error}</div> : null}

        {result ? (
          <>
            <Panel className="prediction-result-card">
              <div className="eyebrow-label">Prediction</div>
              <div className="prediction-value">{String(result.predictions[0]?.prediction)}</div>
              <div className="prediction-meta">
                <span>v{result.model_version}</span>
                <span className="meta-separator">/</span>
                <span>{formatNumber(result.latency_ms, 1)} ms</span>
                <span className="meta-separator">/</span>
                <span className="mono">{result.request_id.slice(0, 8)}</span>
                <CopyButton value={result.request_id} iconOnly />
              </div>
              {result.predictions[0]?.probabilities ? (
                <div className="probability-list">
                  {Object.entries(result.predictions[0].probabilities)
                    .sort((a, b) => b[1] - a[1])
                    .map(([label, probability]) => (
                      <div className="probability-row" key={label}>
                        <span className="probability-label">{label}</span>
                        <span className="probability-track">
                          <span
                            className="probability-fill"
                            style={{ width: `${Math.max(1, probability * 100)}%` }}
                          />
                        </span>
                        <span className="probability-value num">{formatShare(probability, 1)}</span>
                      </div>
                    ))}
                </div>
              ) : null}
              {result.warnings.length ? (
                <div className="inline-notice inline-notice-warning">
                  <Icon name="alert-triangle" size={15} />
                  <span>{result.warnings.join(' ')}</span>
                </div>
              ) : null}
            </Panel>
            <Panel>
              <SectionHeader title="How to use this response" />
              <p className="panel-note">
                Send the target value to <code className="mono">POST /api/v1/predictions/feedback</code>{' '}
                with the request ID. Labelled predictions feed concept-drift and performance checks.
              </p>
              <div className="definition-list compact">
                <div>
                  <span>Model version ID</span>
                  <code className="mono">{result.model_version_id}</code>
                </div>
                <div>
                  <span>Deployment ID</span>
                  <code className="mono">{result.deployment_id}</code>
                </div>
              </div>
            </Panel>
          </>
        ) : (
          <Panel>
            <EmptyState
              compact
              icon="play"
              title="Run a test prediction"
              description="The form is prefilled with reference values. Adjust features and submit to exercise the same authenticated endpoint your applications use."
            />
          </Panel>
        )}
      </div>
    </div>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type {
  DeploymentCreated,
  ModelDetail,
  ModelSummary,
  MonitoringConfig,
  Page,
} from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { ApiKeyDialog } from '../components/ApiKeyDialog'
import { Icon } from '../components/Icon'
import { MonitoringConfigForm } from '../components/MonitoringConfigForm'
import {
  EmptyState,
  ErrorBlock,
  Field,
  Input,
  LinkButton,
  LoadingBlock,
  PageHeader,
  Panel,
  SectionHeader,
  Select,
  StatusPill,
  Textarea,
} from '../components/ui'
import {
  formatMetric,
  primaryMetric,
  relativeTime,
  statusLabel,
  statusTone,
} from '../lib/format'

const DEFAULT_CONFIG: MonitoringConfig = {
  psi_threshold: 0.2,
  drift_share_threshold: 0.3,
  performance_degradation_threshold: 0.15,
  min_samples: 30,
  window_hours: 24,
  auto_retrain_on_drift: true,
  auto_retrain_cooldown_hours: 12,
}

export function NewDeploymentPage() {
  useDocumentTitle('New deployment')
  const navigate = useNavigate()
  const { project } = useWorkspace()

  const models = useApi<Page<ModelSummary>>(
    project ? '/models' : null,
    { project_id: project?.id, page: 1, page_size: 100 },
  )

  const [modelId, setModelId] = useState('')
  const [versionId, setVersionId] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [config, setConfig] = useState<MonitoringConfig>(DEFAULT_CONFIG)
  const [nameTouched, setNameTouched] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<DeploymentCreated | null>(null)

  const modelDetail = useApi<ModelDetail>(modelId ? `/models/${modelId}` : null)
  const versions = useMemo(() => modelDetail.data?.versions ?? [], [modelDetail.data])

  useEffect(() => {
    if (!models.data?.items.length) return
    if (!modelId) {
      setModelId(models.data.items[0].id)
    }
  }, [models.data, modelId])

  useEffect(() => {
    if (!versions.length) return
    if (!versionId || !versions.some((version) => version.id === versionId)) {
      setVersionId(versions[0].id)
    }
  }, [versions, versionId])

  useEffect(() => {
    if (nameTouched || !modelDetail.data) return
    setName(`${modelDetail.data.name} endpoint`)
  }, [modelDetail.data, nameTouched])

  const version = versions.find((item) => item.id === versionId)
  const metricKey = version?.problem_type ? primaryMetric(version.problem_type) : null

  const submit = async () => {
    if (!project || !versionId || !name.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const result = await api.post<DeploymentCreated>('/deployments', {
        project_id: project.id,
        model_version_id: versionId,
        name: name.trim(),
        description: description.trim() || null,
        config,
      })
      setCreated(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the deployment.')
    } finally {
      setSubmitting(false)
    }
  }

  const endpoint = created
    ? `${window.location.origin}/api/v1/predictions/${created.id}`
    : ''

  return (
    <>
      <PageHeader
        title="New deployment"
        backTo="/deployments"
        backLabel="Deployments"
        description="Pin a registered model version behind an authenticated prediction endpoint and configure drift monitoring."
      />

      {!project ? (
        <LoadingBlock />
      ) : models.error ? (
        <ErrorBlock message={models.error} onRetry={models.reload} />
      ) : models.data && !models.data.items.length ? (
        <div className="table-card" style={{ padding: 20 }}>
          <EmptyState
            icon="cube"
            title="Register a model first"
            description="Deployments serve a specific registered model version. Register an experiment, then return here."
            action={
              <LinkButton to="/models" variant="secondary" icon="cube">
                Open model registry
              </LinkButton>
            }
          />
        </div>
      ) : (
        <div className="wizard-layout">
          <div className="wizard-main">
            <div className="stack-gap-20">
              <Panel>
                <SectionHeader
                  title="Model"
                  description="Only registered versions can be deployed. The selected version is pinned for scoring."
                />
                <div className="form-grid-2">
                  <Field label="Registered model" htmlFor="deployment-model">
                    <Select
                      id="deployment-model"
                      value={modelId}
                      onChange={(event) => {
                        setModelId(event.target.value)
                        setVersionId('')
                        setNameTouched(false)
                      }}
                      disabled={!models.data}
                    >
                      {!models.data ? <option value="">Loading models…</option> : null}
                      {models.data?.items.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field
                    label="Model version"
                    htmlFor="deployment-version"
                    hint="Monitor the deployed version’s training reference for drift."
                  >
                    <Select
                      id="deployment-version"
                      value={versionId}
                      onChange={(event) => setVersionId(event.target.value)}
                      disabled={!versions.length}
                    >
                      {!versions.length ? <option value="">Loading versions…</option> : null}
                      {versions.map((item) => (
                        <option key={item.id} value={item.id}>
                          v{item.version} · {item.algorithm.replaceAll('_', ' ')} ·{' '}
                          {item.stage === 'none' ? 'unassigned' : item.stage}
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>

                {modelDetail.error ? (
                  <div style={{ marginTop: 12 }}>
                    <ErrorBlock message={modelDetail.error} onRetry={modelDetail.reload} />
                  </div>
                ) : modelDetail.loading ? (
                  <LoadingBlock rows={2} />
                ) : version ? (
                  <div className="selection-meta deployment-version-preview">
                    <span className="mono">{version.id.slice(0, 8)}</span>
                    <span className="meta-separator">/</span>
                    <StatusPill
                      status={version.stage}
                      label={statusLabel(version.stage)}
                      tone={statusTone(version.stage)}
                    />
                    <span className="muted">
                      {version.reference_feature_count} reference feature
                      {version.reference_feature_count === 1 ? '' : 's'}
                    </span>
                    <span className="muted">trained {relativeTime(version.created_at)}</span>
                  </div>
                ) : null}
              </Panel>

              <Panel>
                <SectionHeader
                  title="Endpoint details"
                  description="Give this endpoint a clear name. API keys are generated after creation."
                />
                <div className="stack-gap-16">
                  <Field label="Name" htmlFor="deployment-name">
                    <Input
                      id="deployment-name"
                      value={name}
                      maxLength={140}
                      placeholder="Customer churn production"
                      onChange={(event) => {
                        setNameTouched(true)
                        setName(event.target.value)
                      }}
                    />
                  </Field>
                  <Field
                    label="Description"
                    htmlFor="deployment-description"
                    hint={`${description.length}/2000 characters`}
                  >
                    <Textarea
                      id="deployment-description"
                      rows={3}
                      maxLength={2000}
                      value={description}
                      placeholder="What this endpoint serves and who consumes it."
                      onChange={(event) => setDescription(event.target.value)}
                    />
                  </Field>
                </div>
              </Panel>

              <Panel>
                <SectionHeader
                  title="Monitoring thresholds"
                  description="Compare live prediction traffic with the deployed version’s training reference."
                />
                <MonitoringConfigForm value={config} onChange={setConfig} />
              </Panel>

              {error ? <div className="error-block">{error}</div> : null}
            </div>
          </div>

          <aside className="wizard-aside">
            <div className="wizard-summary">
              <div className="eyebrow-label">Deployment summary</div>
              <div className="wizard-summary-block">
                <span className="summary-label">Model</span>
                <strong>{modelDetail.data?.name ?? 'Select a model'}</strong>
                <span className="muted">
                  {version ? `v${version.version} · ${version.algorithm.replaceAll('_', ' ')}` : '—'}
                </span>
              </div>
              <div className="wizard-summary-block">
                <span className="summary-label">
                  {metricKey ? 'Primary metric' : 'Reference features'}
                </span>
                <strong className="num">
                  {metricKey && version
                    ? formatMetric(metricKey, version.metrics[metricKey])
                    : version
                      ? version.reference_feature_count
                      : '—'}
                </strong>
                <span className="muted">
                  {metricKey ? `${metricKey.replaceAll('_', ' ')} on training data` : 'from training reference'}
                </span>
              </div>
              <div className="wizard-summary-block">
                <span className="summary-label">Schedule</span>
                <span>Hourly monitoring</span>
                <span className="muted">
                  {config.auto_retrain_on_drift
                    ? 'Auto-retrain queues a job on drift'
                    : 'Manual retraining only'}
                </span>
              </div>
              <div className="wizard-summary-block">
                <span className="summary-label">API key</span>
                <span>{created ? created.api_key_prefix : 'Generated on creation'}</span>
                <span className="muted">Shown once; rotate any time</span>
              </div>
              <div className="wizard-actions">
                <button
                  type="button"
                  className="btn btn-primary btn-block"
                  disabled={!versionId || !name.trim() || submitting}
                  onClick={submit}
                >
                  <Icon name="rocket" size={15} />
                  {submitting ? 'Creating…' : 'Create deployment'}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-block"
                  onClick={() => navigate('/deployments')}
                >
                  Cancel
                </button>
              </div>
            </div>
          </aside>
        </div>
      )}

      {created ? (
        <ApiKeyDialog
          open
          apiKey={created.api_key}
          deploymentName={created.name}
          endpoint={endpoint}
          onClose={() => navigate(`/deployments/${created.id}`)}
        />
      ) : null}
    </>
  )
}

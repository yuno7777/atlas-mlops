import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { ExperimentDetail, MetricMap, ModelVersion } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { useToast } from '../components/ToastProvider'
import {
  Button,
  DefinitionGrid,
  EmptyState,
  ErrorBlock,
  Field,
  InlineNotice,
  Input,
  JsonBlock,
  KpiStrip,
  LinkButton,
  LoadingBlock,
  Modal,
  PageHeader,
  Panel,
  Pill,
  SectionHeader,
  StatusPill,
  Textarea,
} from '../components/ui'
import {
  formatDateTime,
  formatDuration,
  formatMetric,
  formatNumber,
  metricLabel,
  primaryMetric,
  relativeTime,
  shortId,
  statusLabel,
  statusTone,
  titleCase,
} from '../lib/format'

const METRIC_ORDER: Record<string, string[]> = {
  classification: [
    'accuracy',
    'f1_weighted',
    'roc_auc',
    'precision_weighted',
    'recall_weighted',
    'log_loss',
  ],
  regression: ['r2', 'rmse', 'mae', 'mse'],
  clustering: ['silhouette', 'davies_bouldin', 'calinski_harabasz'],
}

function orderedMetrics(metrics: MetricMap, problemType: string): [string, number][] {
  const preferred = METRIC_ORDER[problemType] ?? []
  const keys = Object.keys(metrics).filter((key) => {
    const value = metrics[key]
    return value !== null && Number.isFinite(value)
  })
  keys.sort((a, b) => {
    const indexA = preferred.indexOf(a)
    const indexB = preferred.indexOf(b)
    if (indexA === -1 && indexB === -1) return a.localeCompare(b)
    if (indexA === -1) return 1
    if (indexB === -1) return -1
    return indexA - indexB
  })
  return keys.map((key) => [key, metrics[key] as number])
}

export function ExperimentDetailPage() {
  const { experimentId } = useParams<{ experimentId: string }>()
  const { project } = useWorkspace()
  const navigate = useNavigate()
  const toast = useToast()
  const [registerOpen, setRegisterOpen] = useState(false)
  const [modelName, setModelName] = useState('')
  const [description, setDescription] = useState('')
  const [registerPending, setRegisterPending] = useState(false)
  const [registerError, setRegisterError] = useState<string | null>(null)

  const experiment = useApi<ExperimentDetail>(
    experimentId ? `/experiments/${experimentId}` : null,
  )
  useDocumentTitle(experiment.data?.name ?? 'Experiment')

  const metrics = useMemo(
    () =>
      experiment.data
        ? orderedMetrics(experiment.data.metrics, experiment.data.problem_type)
        : [],
    [experiment.data],
  )

  useEffect(() => {
    if (!experiment.data) return
    setModelName(experiment.data.name.slice(0, 120))
  }, [experiment.data])

  const register = async () => {
    if (!experiment.data || !project) return
    if (!modelName.trim()) {
      setRegisterError('Enter a model name.')
      return
    }
    setRegisterPending(true)
    setRegisterError(null)
    try {
      const version = await api.post<ModelVersion>('/models', {
        project_id: project.id,
        experiment_id: experiment.data.id,
        name: modelName.trim(),
        description: description.trim() || undefined,
      })
      toast.success(`Registered as ${version.registered_model_name ?? modelName} v${version.version}.`)
      setRegisterOpen(false)
      navigate(`/models/${version.registered_model_id}`)
    } catch (caught) {
      setRegisterError(errorMessage(caught))
    } finally {
      setRegisterPending(false)
    }
  }

  if (experiment.error && !experiment.data) {
    return (
      <>
        <PageHeader backTo="/experiments" backLabel="Experiments" title="Experiment unavailable" />
        <ErrorBlock message={experiment.error} onRetry={experiment.reload} />
      </>
    )
  }

  if (!experiment.data) {
    return (
      <>
        <PageHeader backTo="/experiments" backLabel="Experiments" title="Experiment" />
        <LoadingBlock rows={8} />
      </>
    )
  }

  const current = experiment.data
  const primary = primaryMetric(current.problem_type)
  const registered = Boolean(current.registered_model_id)
  const canRegister = current.status === 'completed' && !registered
  const kpiMetrics = metrics.slice(0, 4)
  const fairnessReport = (current.metrics as Record<string, unknown>).fairness

  return (
    <>
      <PageHeader
        backTo="/experiments"
        backLabel="Experiments"
        eyebrow="Experiment"
        title={current.name}
        description={
          <>
            {current.algorithm_label} · {current.dataset_name ?? 'Dataset'} v
            {current.dataset_version ?? '—'} · {titleCase(current.problem_type)}
          </>
        }
        actions={
          <>
            <LinkButton
              to={`/training/${current.training_job_id}`}
              variant="secondary"
              icon="flask"
            >
              Training run
            </LinkButton>
            {registered && current.registered_model_id ? (
              <LinkButton
                to={`/models/${current.registered_model_id}`}
                variant="secondary"
                icon="cube"
              >
                {current.registered_model_name ?? 'Model'} v{current.registered_version}
              </LinkButton>
            ) : null}
            {canRegister ? (
              <Button variant="primary" icon="cube" onClick={() => setRegisterOpen(true)}>
                Register model
              </Button>
            ) : null}
          </>
        }
      />

      {current.status === 'failed' && current.error_message ? (
        <InlineNotice tone="negative" title="Experiment failed">
          {current.error_message}
        </InlineNotice>
      ) : null}

      {current.tracking_warning ? (
        <InlineNotice tone="warning" title="Tracking warning">
          {current.tracking_warning}
        </InlineNotice>
      ) : null}

      {kpiMetrics.length ? (
        <KpiStrip
          items={kpiMetrics.map(([key, value]) => ({
            label: metricLabel(key),
            value: formatMetric(key, value),
            sub: key === primary ? 'Primary metric' : undefined,
          }))}
        />
      ) : null}

      <div className="detail-layout">
        <div className="stack-gap-20">
          <Panel>
            <SectionHeader
              title="Metrics"
              description="Evaluation results on the held-out test split."
              action={
                <StatusPill
                  status={current.status}
                  label={statusLabel(current.status)}
                  tone={statusTone(current.status)}
                />
              }
            />
            {metrics.length ? (
              <div className="metric-table">
                {metrics.map(([key, value]) => (
                  <div className={`metric-row ${key === primary ? 'is-primary' : ''}`} key={key}>
                    <span>
                      {metricLabel(key)}
                      {key === primary ? <span className="primary-mark">Primary</span> : null}
                    </span>
                    <strong className="num">{formatMetric(key, value)}</strong>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                compact
                icon="chart"
                title="No metrics recorded"
                description="This experiment did not produce evaluation metrics."
              />
            )}
          </Panel>

          <Panel>
            <SectionHeader
              title="Hyperparameters"
              description="Parameters used for this run."
              action={
                <Pill tone="neutral">
                  {Object.keys(current.params).length} parameter
                  {Object.keys(current.params).length === 1 ? '' : 's'}
                </Pill>
              }
            />
            {Object.keys(current.params).length ? (
              <div className="param-chips">
                {Object.entries(current.params).map(([key, value]) => (
                  <span className="param-chip" key={key}>
                    {key}=<strong>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</strong>
                  </span>
                ))}
              </div>
            ) : (
              <p className="chart-empty">No hyperparameters were recorded.</p>
            )}
          </Panel>

          {current.cv_metrics ? (
            <Panel>
              <SectionHeader
                title="Cross-validation"
                description="Mean and spread across folds for this algorithm."
              />
              <JsonBlock value={current.cv_metrics} />
            </Panel>
          ) : null}

          {fairnessReport ? (
            <Panel>
              <SectionHeader
                title="Fairness assessment"
                description="Held-out subgroup metrics for audit columns kept out of model features. Interpret alongside group sample counts and domain context."
              />
              <JsonBlock value={fairnessReport} />
            </Panel>
          ) : null}

          {current.reference_profile ? (
            <Panel>
              <SectionHeader
                title="Training reference"
                description="The profile captured for drift monitoring and prediction defaults."
              />
              <DefinitionGrid
                items={[
                  {
                    label: 'Trained rows',
                    value: formatNumber(current.reference_profile.trained_rows),
                  },
                  {
                    label: 'Features',
                    value: formatNumber(current.reference_profile.schema.features.length),
                  },
                  {
                    label: 'Dropped columns',
                    value:
                      current.reference_profile.dropped_columns.length > 0
                        ? current.reference_profile.dropped_columns.join(', ')
                        : 'None',
                  },
                  {
                    label: 'Reference version',
                    value: <span className="num">v{current.reference_profile.version}</span>,
                  },
                ]}
              />
              {current.reference_profile.schema.features.length ? (
                <div className="table-wrap" style={{ marginTop: 16 }}>
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Feature</th>
                        <th>Kind</th>
                        <th>Training type</th>
                        <th className="num">Missing rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {current.reference_profile.schema.features.map((feature) => {
                        const reference = current.reference_profile?.features[feature.name]
                        return (
                          <tr key={feature.name}>
                            <td className="mono">{feature.name}</td>
                            <td>{feature.kind}</td>
                            <td className="muted mono">{feature.dtype}</td>
                            <td className="num muted">
                              {reference?.missing_rate !== undefined
                                ? `${(reference.missing_rate * 100).toFixed(1)}%`
                                : '—'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </Panel>
          ) : null}
        </div>

        <aside className="detail-aside">
          <Panel>
            <SectionHeader title="Run details" />
            <DefinitionGrid
              items={[
                { label: 'Algorithm', value: current.algorithm_label },
                { label: 'Problem', value: titleCase(current.problem_type) },
                { label: 'Dataset', value: `${current.dataset_name ?? 'Dataset'} v${current.dataset_version ?? '—'}` },
                { label: 'Duration', value: formatDuration(current.training_duration_seconds) },
                { label: 'Created', value: formatDateTime(current.created_at) },
                { label: 'Completed', value: formatDateTime(current.completed_at) },
                {
                  label: 'Training job',
                  value: (
                    <Link to={`/training/${current.training_job_id}`} className="inline-link">
                      {current.job_name ?? shortId(current.training_job_id)}
                    </Link>
                  ),
                },
                {
                  label: 'MLflow run',
                  value: (
                    <span className="mono" title={current.mlflow_run_id ?? ''}>
                      {shortId(current.mlflow_run_id)}
                    </span>
                  ),
                },
              ]}
            />
          </Panel>

          <Panel>
            <SectionHeader title="Registry" />
            {registered && current.registered_model_id ? (
              <div className="registry-state">
                <StatusPill status="production" label="Registered" tone="info" />
                <div>
                  <Link
                    to={`/models/${current.registered_model_id}`}
                    className="cell-link"
                    style={{ fontSize: 14 }}
                  >
                    {current.registered_model_name}
                  </Link>
                  <div className="cell-sub">
                    Version {current.registered_version} ·{' '}
                    {statusLabel(current.registered_stage ?? 'none')}
                  </div>
                </div>
              </div>
            ) : canRegister ? (
              <>
                <p className="panel-note" style={{ marginTop: 0 }}>
                  Package this experiment as a model version so it can be promoted, downloaded and
                  deployed.
                </p>
                <Button variant="secondary" icon="cube" onClick={() => setRegisterOpen(true)}>
                  Register model
                </Button>
              </>
            ) : (
              <p className="chart-empty">Only completed experiments can be registered.</p>
            )}
          </Panel>

          <Panel>
            <SectionHeader title="Artifact" />
            <DefinitionGrid
              items={[
                {
                  label: 'Available',
                  value: (
                    <StatusPill
                      status={current.artifact_available ? 'ready' : 'warning'}
                      label={current.artifact_available ? 'Yes' : 'Not reported'}
                      tone={current.artifact_available ? 'positive' : 'neutral'}
                    />
                  ),
                },
                {
                  label: 'Registered',
                  value: relativeTime(current.created_at),
                },
              ]}
            />
            <p className="panel-note">
              Register a model to download the fitted pipeline and deploy it behind the prediction
              API.
            </p>
          </Panel>
        </aside>
      </div>

      <Modal
        open={registerOpen}
        onClose={() => setRegisterOpen(false)}
        title="Register model"
        description="Create a model version from this experiment. Reusing an existing name adds a new version."
        footer={
          <>
            <Button variant="secondary" onClick={() => setRegisterOpen(false)} disabled={registerPending}>
              Cancel
            </Button>
            <Button variant="primary" loading={registerPending} onClick={() => void register()}>
              Register version
            </Button>
          </>
        }
      >
        <div className="form-stack">
          <Field label="Model name" htmlFor="register-model-name">
            <Input
              id="register-model-name"
              value={modelName}
              onChange={(event) => setModelName(event.target.value)}
              maxLength={120}
              placeholder="customer-churn"
            />
          </Field>
          <Field
            label="Description"
            htmlFor="register-model-description"
            hint="Optional. Stored on the model, not just this version."
          >
            <Textarea
              id="register-model-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="What does this model predict and where is it used?"
            />
          </Field>
          {registerError ? <div className="error-block is-compact">{registerError}</div> : null}
        </div>
      </Modal>
    </>
  )
}

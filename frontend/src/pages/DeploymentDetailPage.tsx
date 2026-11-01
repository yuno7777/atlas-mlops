import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type {
  DeploymentDetail,
  DeploymentHealth,
  FeedbackResponse,
  ModelDetail,
  MonitoringConfig,
  MonitoringResult,
  Page,
  PredictionLog,
  RotateKeyResponse,
  Timeseries,
} from '../api/types'
import { ApiKeyDialog } from '../components/ApiKeyDialog'
import {
  ChartLegend,
  FeatureDriftList,
  LatencyChart,
  VolumeChart,
} from '../components/charts'
import { Icon } from '../components/Icon'
import { MonitoringConfigForm } from '../components/MonitoringConfigForm'
import { PredictionPlayground } from '../components/PredictionPlayground'
import { RetrainDialog } from '../components/RetrainDialog'
import { useToast } from '../components/ToastProvider'
import {
  Button,
  ConfirmDialog,
  CopyButton,
  EmptyState,
  ErrorBlock,
  Field,
  Input,
  LoadingBlock,
  Modal,
  PageHeader,
  Pagination,
  Panel,
  SectionHeader,
  Select,
  StatusPill,
  TableSkeleton,
} from '../components/ui'
import {
  formatDate,
  formatNumber,
  formatShare,
  monitoringTone,
  relativeTime,
  statusLabel,
  statusTone,
  titleCase,
} from '../lib/format'

type TabKey = 'overview' | 'test' | 'predictions' | 'revisions' | 'settings'

export function DeploymentDetailPage() {
  const { deploymentId } = useParams<{ deploymentId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()

  const currentTab = (searchParams.get('tab') as TabKey) || 'overview'
  const setTab = (tab: TabKey) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('tab', tab)
      return next
    })
  }

  const deployment = useApi<DeploymentDetail>(
    deploymentId ? `/deployments/${deploymentId}` : null,
    undefined,
    { pollMs: 15000 },
  )

  useDocumentTitle(deployment.data?.name ?? 'Deployment')

  const health = useApi<DeploymentHealth>(
    deploymentId ? `/deployments/${deploymentId}/health` : null,
    undefined,
    { pollMs: 30000 },
  )

  const [hours, setHours] = useState(24)
  const timeseries = useApi<Timeseries>(
    deploymentId ? `/deployments/${deploymentId}/monitoring/timeseries` : null,
    { hours },
    { pollMs: 30000 },
  )

  const latestMonitoring = useApi<MonitoringResult>(
    deploymentId ? `/deployments/${deploymentId}/monitoring/latest` : null,
    undefined,
    { pollMs: 30000 },
  )

  // Predictions tab state
  const [predStatus, setPredStatus] = useState('')
  const [predPage, setPredPage] = useState(1)
  const predictions = useApi<Page<PredictionLog>>(
    deploymentId && currentTab === 'predictions'
      ? `/deployments/${deploymentId}/predictions`
      : null,
    {
      status: predStatus || undefined,
      page: predPage,
      page_size: 20,
    },
  )

  // Feedback dialog state
  const [feedbackLog, setFeedbackLog] = useState<PredictionLog | null>(null)
  const [feedbackActual, setFeedbackActual] = useState('')
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)

  // Retrain dialog
  const [retrainOpen, setRetrainOpen] = useState(false)

  // API key dialog
  const [rotatedKey, setRotatedKey] = useState<{ apiKey: string } | null>(null)
  const [rotatePending, setRotatePending] = useState(false)

  // Lifecycle action state
  const [lifecyclePending, setLifecyclePending] = useState(false)
  const [rollbackOpen, setRollbackOpen] = useState(false)
  const [rollbackPending, setRollbackPending] = useState(false)

  // Monitoring scan state
  const [scanPending, setScanPending] = useState(false)

  // Settings tab form state
  const [settingsName, setSettingsName] = useState('')
  const [settingsDesc, setSettingsDesc] = useState('')
  const [settingsConfig, setSettingsConfig] = useState<MonitoringConfig | null>(null)
  const [settingsVersionId, setSettingsVersionId] = useState('')
  const [settingsPending, setSettingsPending] = useState(false)
  const [versionSwitchOpen, setVersionSwitchOpen] = useState(false)

  // Model versions for settings tab
  const model = useApi<ModelDetail>(
    deployment.data?.registered_model_id
      ? `/models/${deployment.data.registered_model_id}`
      : null,
  )

  useEffect(() => {
    if (deployment.data) {
      setSettingsName(deployment.data.name)
      setSettingsDesc(deployment.data.description ?? '')
      setSettingsConfig(deployment.data.config)
      setSettingsVersionId(deployment.data.model_version_id)
    }
  }, [deployment.data?.id, deployment.data?.updated_at])

  const toggleLifecycle = async () => {
    if (!deploymentId || !deployment.data) return
    const isStopping = deployment.data.status === 'active'
    setLifecyclePending(true)
    try {
      const endpoint = isStopping
        ? `/deployments/${deploymentId}/stop`
        : `/deployments/${deploymentId}/start`
      await api.post<DeploymentDetail>(endpoint)
      toast.success(isStopping ? 'Deployment stopped.' : 'Deployment started.')
      deployment.reload()
      health.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLifecyclePending(false)
    }
  }

  const runMonitoringScan = async () => {
    if (!deploymentId) return
    setScanPending(true)
    try {
      const res = await api.post<MonitoringResult>(
        `/deployments/${deploymentId}/monitoring/run`,
      )
      toast.success(`Monitoring analysis completed (${statusLabel(res.status)}).`)
      latestMonitoring.reload()
      deployment.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setScanPending(false)
    }
  }

  const rotateKey = async () => {
    if (!deploymentId || !deployment.data) return
    setRotatePending(true)
    try {
      const res = await api.post<RotateKeyResponse>(
        `/deployments/${deploymentId}/rotate-key`,
      )
      setRotatedKey({ apiKey: res.api_key })
      toast.success('API key rotated.')
      deployment.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setRotatePending(false)
    }
  }

  const rollback = async () => {
    if (!deploymentId) return
    setRollbackPending(true)
    try {
      await api.post<DeploymentDetail>(`/deployments/${deploymentId}/rollback`)
      toast.success('Deployment rolled back to previous model revision.')
      setRollbackOpen(false)
      deployment.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setRollbackPending(false)
    }
  }

  const submitFeedback = async () => {
    if (!feedbackLog) return
    setFeedbackSubmitting(true)
    setFeedbackError(null)
    try {
      let actualVal: unknown = feedbackActual.trim()
      if (/^-?\d+(\.\d+)?$/.test(feedbackActual.trim())) {
        actualVal = Number(feedbackActual.trim())
      }
      await api.post<FeedbackResponse>('/predictions/feedback', {
        items: [{ prediction_id: feedbackLog.id, actual: actualVal }],
      })
      toast.success('Ground-truth label saved.')
      setFeedbackLog(null)
      setFeedbackActual('')
      predictions.reload()
    } catch (err) {
      setFeedbackError(errorMessage(err))
    } finally {
      setFeedbackSubmitting(false)
    }
  }

  const saveSettings = async () => {
    if (!deploymentId || !settingsConfig) return
    setSettingsPending(true)
    try {
      await api.patch<DeploymentDetail>(`/deployments/${deploymentId}`, {
        name: settingsName.trim(),
        description: settingsDesc.trim() || undefined,
        config: settingsConfig,
      })
      toast.success('Deployment settings saved.')
      deployment.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSettingsPending(false)
    }
  }

  const switchVersion = async () => {
    if (!deploymentId || !settingsVersionId) return
    setSettingsPending(true)
    try {
      await api.patch<DeploymentDetail>(`/deployments/${deploymentId}`, {
        model_version_id: settingsVersionId,
      })
      toast.success('Model version updated.')
      setVersionSwitchOpen(false)
      deployment.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSettingsPending(false)
    }
  }

  if (deployment.error && !deployment.data) {
    return <ErrorBlock message={deployment.error} onRetry={deployment.reload} />
  }

  if (deployment.loading && !deployment.data) {
    return <LoadingBlock rows={8} />
  }

  const d = deployment.data
  if (!d) return null

  const featureDriftList =
    latestMonitoring.data?.details?.data_drift?.features ?? []

  const endpointUrl = `${window.location.origin}/api/v1/predictions/${d.id}`

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Deployments', to: '/deployments' },
          { label: d.name },
        ]}
        title={d.name}
        description={
          d.description ||
          `Serving ${d.model_name} v${d.model_version} (${d.algorithm.replaceAll('_', ' ')})`
        }
        actions={
          <div className="button-group">
            <Button
              variant={d.status === 'active' ? 'secondary' : 'primary'}
              icon={d.status === 'active' ? 'stop' : 'play'}
              loading={lifecyclePending}
              onClick={() => void toggleLifecycle()}
            >
              {d.status === 'active' ? 'Stop' : 'Start'}
            </Button>
            <Button
              variant="secondary"
              icon="rotate"
              onClick={() => setRetrainOpen(true)}
            >
              Retrain
            </Button>
            {d.revisions.length > 1 ? (
              <Button
                variant="ghost"
                icon="chevron-left"
                onClick={() => setRollbackOpen(true)}
              >
                Rollback
              </Button>
            ) : null}
          </div>
        }
      />

      <div className="tab-bar" role="tablist">
        <button
          type="button"
          className={`tab-item ${currentTab === 'overview' ? 'is-active' : ''}`}
          onClick={() => setTab('overview')}
        >
          <Icon name="grid" size={15} />
          Overview &amp; Drift
        </button>
        <button
          type="button"
          className={`tab-item ${currentTab === 'test' ? 'is-active' : ''}`}
          onClick={() => setTab('test')}
        >
          <Icon name="play" size={15} />
          Test Playground
        </button>
        <button
          type="button"
          className={`tab-item ${currentTab === 'predictions' ? 'is-active' : ''}`}
          onClick={() => setTab('predictions')}
        >
          <Icon name="activity" size={15} />
          Prediction Logs
        </button>
        <button
          type="button"
          className={`tab-item ${currentTab === 'revisions' ? 'is-active' : ''}`}
          onClick={() => setTab('revisions')}
        >
          <Icon name="clock" size={15} />
          Revisions &amp; Events
        </button>
        <button
          type="button"
          className={`tab-item ${currentTab === 'settings' ? 'is-active' : ''}`}
          onClick={() => setTab('settings')}
        >
          <Icon name="sliders" size={15} />
          Settings
        </button>
      </div>

      {currentTab === 'overview' ? (
        <div className="stack-gap-24">
          <div className="kpi-strip">
            <div className="kpi">
              <span className="kpi-label">Status</span>
              <div className="kpi-value-row">
                <StatusPill
                  status={d.status}
                  label={statusLabel(d.status)}
                  tone={statusTone(d.status)}
                />
              </div>
              <span className="kpi-sub">
                {health.data?.healthy ? 'Healthy container' : 'Health check passing'}
              </span>
            </div>

            <div className="kpi">
              <span className="kpi-label">Monitoring</span>
              <div className="kpi-value-row">
                <StatusPill
                  status={d.latest_monitoring_status || 'not_run'}
                  label={statusLabel(d.latest_monitoring_status || 'not_run')}
                  tone={monitoringTone(d.latest_monitoring_status)}
                />
              </div>
              <span className="kpi-sub">
                {latestMonitoring.data
                  ? `${relativeTime(latestMonitoring.data.created_at)}`
                  : 'No scan yet'}
              </span>
            </div>

            <div className="kpi">
              <span className="kpi-label">Model version</span>
              <div className="kpi-value">
                <Link to={`/models/${d.registered_model_id}`} className="text-link">
                  v{d.model_version}
                </Link>
              </div>
              <span className="kpi-sub">{d.algorithm.replaceAll('_', ' ')}</span>
            </div>

            <div className="kpi">
              <span className="kpi-label">API key prefix</span>
              <div className="kpi-value mono">{d.api_key_prefix}&hellip;</div>
              <span className="kpi-sub">
                Last request {relativeTime(d.last_request_at)}
              </span>
            </div>
          </div>

          <div className="overview-grid">
            <Panel>
              <div className="panel-header-with-action">
                <SectionHeader
                  title="Traffic volume &amp; errors"
                  description="Hourly requests and failures."
                />
                <div className="filter-chips">
                  {[24, 48, 168].map((h) => (
                    <button
                      key={h}
                      type="button"
                      className={`filter-chip ${hours === h ? 'is-active' : ''}`}
                      onClick={() => setHours(h)}
                    >
                      {h === 168 ? '7d' : `${h}h`}
                    </button>
                  ))}
                </div>
              </div>
              <ChartLegend
                items={[
                  { label: 'Requests', tone: 'accent' },
                  { label: 'Failures', tone: 'negative' },
                ]}
              />
              <VolumeChart
                points={
                  timeseries.data?.points.map((p) => ({
                    bucket: String(p.bucket),
                    predictions: p.predictions,
                    failures: p.failures,
                  })) ?? []
                }
              />
            </Panel>

            <Panel>
              <SectionHeader
                title="p95 Latency"
                description="Tail inference latency over the same window."
              />
              <ChartLegend items={[{ label: 'p95 latency', tone: 'accent' }]} />
              <LatencyChart
                points={
                  timeseries.data?.points.map((p) => ({
                    bucket: String(p.bucket),
                    p95_latency_ms: p.p95_latency_ms,
                  })) ?? []
                }
              />
            </Panel>
          </div>

          <Panel>
            <div className="panel-header-with-action">
              <SectionHeader
                title="Drift &amp; performance analysis"
                description="Statistical tests against the training reference baseline (PSI &amp; Kolmogorov-Smirnov)."
              />
              <Button
                variant="secondary"
                icon="refresh"
                loading={scanPending}
                onClick={() => void runMonitoringScan()}
              >
                Run scan now
              </Button>
            </div>

            {latestMonitoring.loading ? (
              <LoadingBlock rows={4} />
            ) : latestMonitoring.data ? (
              <div className="stack-gap-20">
                <div className="form-grid-3">
                  <div className="definition-card">
                    <span className="definition-label">Data drift</span>
                    <strong className="definition-value">
                      {latestMonitoring.data.data_drift_detected ? (
                        <StatusPill status="drifted" label="Drift detected" tone="negative" />
                      ) : (
                        <StatusPill status="stable" label="Stable" tone="positive" />
                      )}
                    </strong>
                    <span className="definition-sub">
                      Drift share: {formatShare(latestMonitoring.data.drift_share)} &middot; Max PSI:{' '}
                      {latestMonitoring.data.psi_max.toFixed(3)}
                    </span>
                  </div>

                  <div className="definition-card">
                    <span className="definition-label">Prediction drift</span>
                    <strong className="definition-value">
                      {latestMonitoring.data.prediction_drift_detected ? (
                        <StatusPill status="drifted" label="Shifted" tone="negative" />
                      ) : (
                        <StatusPill status="stable" label="Stable" tone="positive" />
                      )}
                    </strong>
                    <span className="definition-sub">
                      PSI:{' '}
                      {latestMonitoring.data.details?.prediction_drift?.psi?.toFixed(3) ??
                        '0.000'}
                    </span>
                  </div>

                  <div className="definition-card">
                    <span className="definition-label">Concept drift</span>
                    <strong className="definition-value">
                      {latestMonitoring.data.concept_drift_detected ? (
                        <StatusPill status="drifted" label="Degraded" tone="negative" />
                      ) : (
                        <StatusPill status="stable" label="Stable" tone="positive" />
                      )}
                    </strong>
                    <span className="definition-sub">
                      {latestMonitoring.data.labeled_count > 0
                        ? `${latestMonitoring.data.labeled_count} labelled samples`
                        : 'Awaiting ground truth labels'}
                    </span>
                  </div>
                </div>

                {featureDriftList.length > 0 ? (
                  <div>
                    <h4 style={{ marginBottom: 12 }}>Feature drift breakdown</h4>
                    <FeatureDriftList
                      features={featureDriftList}
                      threshold={d.config.psi_threshold}
                    />
                  </div>
                ) : (
                  <p className="chart-empty">No individual feature drifts detected.</p>
                )}
              </div>
            ) : (
              <EmptyState
                compact
                icon="activity"
                title="No monitoring scans yet"
                description="Predictions will be evaluated once sufficient volume is reached, or you can trigger an on-demand scan."
                action={
                  <Button
                    variant="secondary"
                    icon="refresh"
                    loading={scanPending}
                    onClick={() => void runMonitoringScan()}
                  >
                    Run initial scan
                  </Button>
                }
              />
            )}
          </Panel>
        </div>
      ) : null}

      {currentTab === 'test' ? (
        <PredictionPlayground
          deploymentId={d.id}
          modelVersionId={d.model_version_id}
          targetColumn={d.target_column}
        />
      ) : null}

      {currentTab === 'predictions' ? (
        <div className="stack-gap-16">
          <div className="table-card">
            <div className="table-toolbar">
              <div className="table-toolbar-left">
                <div className="filter-chips">
                  {[
                    { value: '', label: 'All' },
                    { value: 'success', label: 'Success' },
                    { value: 'failed', label: 'Failed' },
                  ].map((filter) => (
                    <button
                      key={filter.value}
                      type="button"
                      className={`filter-chip ${predStatus === filter.value ? 'is-active' : ''}`}
                      onClick={() => {
                        setPredStatus(filter.value)
                        setPredPage(1)
                      }}
                    >
                      {filter.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="table-toolbar-right">
                <span className="table-count">
                  {predictions.data
                    ? `${formatNumber(predictions.data.total)} prediction${
                        predictions.data.total === 1 ? '' : 's'
                      }`
                    : ''}
                </span>
              </div>
            </div>

            {predictions.error ? (
              <div style={{ padding: 16 }}>
                <ErrorBlock message={predictions.error} onRetry={predictions.reload} />
              </div>
            ) : null}

            {!predictions.data && predictions.loading ? (
              <TableSkeleton columns={6} rows={8} />
            ) : predictions.data?.items.length ? (
              <>
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Request ID</th>
                        <th>Status</th>
                        <th className="num">Latency</th>
                        <th>Prediction</th>
                        <th>Actual Ground Truth</th>
                        <th>Timestamp</th>
                        <th className="actions-head" />
                      </tr>
                    </thead>
                    <tbody>
                      {predictions.data.items.map((log) => (
                        <tr key={log.id}>
                          <td>
                            <code className="mono">{log.request_id.slice(0, 10)}&hellip;</code>
                            <CopyButton value={log.request_id} iconOnly />
                          </td>
                          <td>
                            <StatusPill
                              status={log.status}
                              label={statusLabel(log.status)}
                              tone={statusTone(log.status)}
                            />
                          </td>
                          <td className="num">{formatNumber(log.latency_ms, 1)} ms</td>
                          <td>
                            <strong>{String(log.prediction ?? '')}</strong>
                          </td>
                          <td>
                            {log.actual !== null && log.actual !== undefined ? (
                              <span className="mono">{String(log.actual)}</span>
                            ) : (
                              <span className="cell-null">Unlabelled</span>
                            )}
                          </td>
                          <td className="cell-sub">{relativeTime(log.created_at)}</td>
                          <td className="actions-cell">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setFeedbackLog(log)
                                setFeedbackActual(
                                  log.actual !== null && log.actual !== undefined
                                    ? String(log.actual)
                                    : '',
                                )
                                setFeedbackError(null)
                              }}
                            >
                              Add label
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination
                  page={predPage}
                  pages={predictions.data.pages}
                  total={predictions.data.total}
                  pageSize={predictions.data.page_size}
                  onChange={setPredPage}
                />
              </>
            ) : (
              <EmptyState
                compact
                icon="activity"
                title="No predictions logged"
                description="Make API calls or test the model from the Test Playground to populate prediction logs."
                action={
                  <Button variant="primary" onClick={() => setTab('test')}>
                    Go to Playground
                  </Button>
                }
              />
            )}
          </div>
        </div>
      ) : null}

      {currentTab === 'revisions' ? (
        <div className="stack-gap-24">
          <Panel>
            <SectionHeader
              title="Deployment revisions"
              description="History of model version promotions and rollbacks for this endpoint."
            />
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Revision</th>
                    <th>Model version</th>
                    <th>Reason</th>
                    <th>Activated</th>
                    <th>Deactivated</th>
                  </tr>
                </thead>
                <tbody>
                  {d.revisions.map((rev) => (
                    <tr key={rev.id}>
                      <td>
                        <code className="mono">{rev.id.slice(0, 8)}</code>
                      </td>
                      <td>
                        <strong>v{rev.version ?? d.model_version}</strong>
                      </td>
                      <td>{titleCase(rev.reason || 'updated')}</td>
                      <td>{formatDate(rev.activated_at)}</td>
                      <td>
                        {rev.deactivated_at ? (
                          formatDate(rev.deactivated_at)
                        ) : (
                          <StatusPill status="active" label="Current" tone="positive" />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel>
            <SectionHeader
              title="Event log"
              description="Operational audit trail for lifecycle events, keys and rollbacks."
            />
            {d.events.length > 0 ? (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Level</th>
                      <th>Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.events.map((event) => (
                      <tr key={event.id}>
                        <td className="cell-sub">{formatDate(event.created_at)}</td>
                        <td>
                          <StatusPill
                            status={event.level}
                            label={event.level.toUpperCase()}
                            tone={statusTone(event.level)}
                          />
                        </td>
                        <td>{event.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="chart-empty">No lifecycle events recorded yet.</p>
            )}
          </Panel>
        </div>
      ) : null}

      {currentTab === 'settings' ? (
        <div className="stack-gap-24">
          <Panel>
            <SectionHeader
              title="Deployment details"
              description="Update deployment metadata."
            />
            <div className="form-grid-2">
              <Field label="Deployment name" htmlFor="setting-name">
                <Input
                  id="setting-name"
                  value={settingsName}
                  onChange={(e) => setSettingsName(e.target.value)}
                />
              </Field>
              <Field label="Description" htmlFor="setting-desc">
                <Input
                  id="setting-desc"
                  value={settingsDesc}
                  onChange={(e) => setSettingsDesc(e.target.value)}
                />
              </Field>
            </div>
            <div style={{ marginTop: 16 }}>
              <Button
                variant="primary"
                loading={settingsPending}
                onClick={() => void saveSettings()}
              >
                Save metadata
              </Button>
            </div>
          </Panel>

          <Panel>
            <SectionHeader
              title="Pinned model version"
              description="Promote or switch this deployment to another registered model version."
              action={
                <Button
                  variant="secondary"
                  disabled={settingsVersionId === d.model_version_id}
                  onClick={() => setVersionSwitchOpen(true)}
                >
                  Switch version
                </Button>
              }
            />
            <Field
              label="Registered version"
              htmlFor="setting-model-version"
              hint={`Currently pinned to v${d.model_version}.`}
            >
              <Select
                id="setting-model-version"
                value={settingsVersionId}
                onChange={(e) => setSettingsVersionId(e.target.value)}
              >
                {model.data?.versions.map((ver) => (
                  <option key={ver.id} value={ver.id}>
                    v{ver.version} &middot; stage: {ver.stage} ({ver.algorithm})
                  </option>
                ))}
              </Select>
            </Field>
          </Panel>

          {settingsConfig ? (
            <Panel>
              <SectionHeader
                title="Monitoring thresholds"
                description="Fine-tune drift detection sensitivity, sample sizes, and retraining triggers."
              />
              <MonitoringConfigForm value={settingsConfig} onChange={setSettingsConfig} />
              <div style={{ marginTop: 16 }}>
                <Button
                  variant="primary"
                  loading={settingsPending}
                  onClick={() => void saveSettings()}
                >
                  Save monitoring thresholds
                </Button>
              </div>
            </Panel>
          ) : null}

          <Panel>
            <SectionHeader
              title="API Access &amp; Key Rotation"
              description="Manage authentication keys for callers of this endpoint."
            />
            <div className="stack-gap-16">
              <div>
                <span className="field-label">API Key prefix</span>
                <div className="code-line">
                  <code className="mono">{d.api_key_prefix}&hellip;</code>
                </div>
              </div>
              <div>
                <span className="field-label">Prediction endpoint</span>
                <div className="code-line">
                  <code className="mono">POST {endpointUrl}</code>
                  <CopyButton value={endpointUrl} iconOnly />
                </div>
              </div>
              <div>
                <Button
                  variant="secondary"
                  icon="key"
                  loading={rotatePending}
                  onClick={() => void rotateKey()}
                >
                  Rotate API Key
                </Button>
              </div>
            </div>
          </Panel>
        </div>
      ) : null}

      {/* Retrain dialog */}
      <RetrainDialog
        deployment={d}
        open={retrainOpen}
        onClose={() => setRetrainOpen(false)}
        onQueued={(jobId) => navigate(`/training/${jobId}`)}
      />

      {/* API Key revealed modal */}
      {rotatedKey ? (
        <ApiKeyDialog
          open={Boolean(rotatedKey)}
          apiKey={rotatedKey.apiKey}
          deploymentName={d.name}
          endpoint={endpointUrl}
          onClose={() => setRotatedKey(null)}
        />
      ) : null}

      {/* Rollback confirmation */}
      <ConfirmDialog
        open={rollbackOpen}
        title="Rollback deployment?"
        description="This will instantly activate the previous model revision. Callers will immediately receive predictions from the previous version."
        confirmLabel="Rollback now"
        tone="warning"
        loading={rollbackPending}
        onConfirm={() => void rollback()}
        onClose={() => setRollbackOpen(false)}
      />

      {/* Switch version confirmation */}
      <ConfirmDialog
        open={versionSwitchOpen}
        title="Switch model version?"
        description="The deployment will be updated to serve the selected model version. An active revision entry will be logged."
        confirmLabel="Confirm version switch"
        tone="primary"
        loading={settingsPending}
        onConfirm={() => void switchVersion()}
        onClose={() => setVersionSwitchOpen(false)}
      />

      {/* Ground truth feedback modal */}
      {feedbackLog ? (
        <Modal
          open={Boolean(feedbackLog)}
          onClose={() => setFeedbackLog(null)}
          title="Provide ground-truth label"
          description={`Submit true outcome for prediction request ${feedbackLog.request_id.slice(0, 8)}.`}
          footer={
            <div className="modal-actions-between">
              <Button
                variant="ghost"
                onClick={() => setFeedbackLog(null)}
                disabled={feedbackSubmitting}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                loading={feedbackSubmitting}
                onClick={() => void submitFeedback()}
              >
                Save label
              </Button>
            </div>
          }
        >
          <div className="stack-gap-16">
            <div className="definition-list compact">
              <div>
                <span>Model predicted</span>
                <strong>{String(feedbackLog.prediction)}</strong>
              </div>
              <div>
                <span>Target column</span>
                <span>{d.target_column || 'target'}</span>
              </div>
            </div>
            <Field
              label="Observed actual value"
              htmlFor="feedback-actual"
              hint="Enter the actual ground truth label or numeric value."
            >
              <Input
                id="feedback-actual"
                value={feedbackActual}
                onChange={(e) => setFeedbackActual(e.target.value)}
                placeholder="e.g. 0, 1, or category"
                autoFocus
              />
            </Field>
            {feedbackError ? <div className="error-block">{feedbackError}</div> : null}
          </div>
        </Modal>
      ) : null}
    </>
  )
}

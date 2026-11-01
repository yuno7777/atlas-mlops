import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { DeploymentSummary, MonitoringResult, Page, SLOSnapshot } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { FeatureDriftList } from '../components/charts'
import { useToast } from '../components/ToastProvider'
import {
  Button,
  EmptyState,
  ErrorBlock,
  KpiStrip,
  LinkButton,
  PageHeader,
  Panel,
  SectionHeader,
  StatusPill,
  TableSkeleton,
} from '../components/ui'
import {
  formatNumber,
  formatPercent,
  formatShare,
  monitoringTone,
  relativeTime,
  statusLabel,
  statusTone,
} from '../lib/format'

export function MonitoringPage() {
  useDocumentTitle('Monitoring & Drift')
  const { project } = useWorkspace()
  const toast = useToast()

  const deployments = useApi<Page<DeploymentSummary>>(
    project ? '/deployments' : null,
    { project_id: project?.id, page_size: 50 },
    { pollMs: 30000 },
  )
  const slo = useApi<SLOSnapshot>('/system/slo', undefined, { pollMs: 30000 })

  const [scanningId, setScanningId] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const selectedDeployment = deployments.data?.items.find((d) => d.id === selectedId)

  const selectedMonitoring = useApi<MonitoringResult>(
    selectedId ? `/deployments/${selectedId}/monitoring/latest` : null,
    undefined,
    { pollMs: 15000 },
  )

  const runScan = async (deploymentId: string) => {
    setScanningId(deploymentId)
    try {
      const res = await api.post<MonitoringResult>(
        `/deployments/${deploymentId}/monitoring/run`,
      )
      toast.success(`Monitoring analysis finished (${statusLabel(res.status)}).`)
      deployments.reload()
      if (selectedId === deploymentId) {
        selectedMonitoring.reload()
      }
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setScanningId(null)
    }
  }

  const items = deployments.data?.items ?? []
  const activeDeployments = items.filter((d) => d.status === 'active')
  const warningDeployments = items.filter(
    (d) => d.latest_monitoring_status === 'warning' || d.latest_monitoring_status === 'drifted',
  )
  const healthyDeployments = items.filter(
    (d) => d.latest_monitoring_status === 'healthy' || d.latest_monitoring_status === 'stable',
  )

  const featureDriftList =
    selectedMonitoring.data?.details?.data_drift?.features ?? []

  return (
    <>
      <PageHeader
        title="Production Monitoring"
        description="Continuous statistical drift detection across active prediction endpoints. Compares incoming distributions to training reference profiles."
        actions={
          <LinkButton to="/deployments" variant="secondary" icon="rocket">
            Manage deployments
          </LinkButton>
        }
      />

      <div className="stack-gap-24">
        <KpiStrip
          items={[
            {
              label: 'Active endpoints',
              value: formatNumber(activeDeployments.length),
              sub: `${formatNumber(items.length)} total deployments`,
            },
            {
              label: 'Healthy endpoints',
              value: formatNumber(healthyDeployments.length),
              sub: 'Within baseline drift thresholds',
            },
            {
              label: 'Drift alerts',
              value: formatNumber(warningDeployments.length),
              sub: 'Threshold exceeded',
            },
            {
              label: 'Evaluation method',
              value: 'PSI & KS-test',
              sub: 'Population Stability & 2-Sample KS',
            },
          ]}
        />

        <Panel>
          <SectionHeader
            title="Service level objectives"
            description="HTTP availability and latency SLIs from the Prometheus process registry. Values reset when the API process restarts."
            action={slo.data ? <StatusPill status={slo.data.status} label={statusLabel(slo.data.status)} tone={slo.data.status === 'met' ? 'positive' : slo.data.status === 'no_data' ? 'neutral' : 'negative'} /> : undefined}
          />
          {slo.error ? <ErrorBlock message={slo.error} onRetry={slo.reload} /> : null}
          {slo.data ? (
            <>
              <KpiStrip items={[
                { label: 'Availability', value: slo.data.availability === null ? '—' : formatPercent(slo.data.availability), sub: `${formatPercent(slo.data.availability_target)} objective` },
                { label: 'P95 latency', value: slo.data.p95_latency_ms === null ? '—' : `${formatNumber(slo.data.p95_latency_ms, 1)} ms`, sub: `Target ≤ ${formatNumber(slo.data.latency_target_ms)} ms` },
                { label: 'Latency SLI', value: slo.data.latency_sli === null ? '—' : formatPercent(slo.data.latency_sli), sub: `${formatPercent(slo.data.latency_target)} of requests within target` },
                { label: 'Error budget used', value: slo.data.availability_error_budget_percent_used === null ? '—' : `${formatNumber(slo.data.availability_error_budget_percent_used, 1)}%`, sub: `${formatNumber(slo.data.server_errors)} server errors · ${formatNumber(slo.data.requests)} requests` },
              ]} />
              <div className="otel-status-row">
                <span><strong>OpenTelemetry tracing:</strong> {slo.data.trace_export_enabled ? 'OTLP export enabled' : 'Not configured'}</span>
                {slo.data.trace_export_endpoint ? <code>{slo.data.trace_export_endpoint}</code> : <span className="muted">Set OTEL_EXPORTER_OTLP_ENDPOINT to export request traces.</span>}
                <span className="muted">Window: {slo.data.window}</span>
              </div>
            </>
          ) : null}
        </Panel>

        <div className="table-card">
          <div className="table-toolbar">
            <div className="table-toolbar-left">
              <span className="section-title">Deployed models</span>
            </div>
            <div className="table-toolbar-right">
              <span className="table-count">
                {items.length} endpoint{items.length === 1 ? '' : 's'}
              </span>
            </div>
          </div>

          {deployments.error ? (
            <div style={{ padding: 16 }}>
              <ErrorBlock message={deployments.error} onRetry={deployments.reload} />
            </div>
          ) : null}

          {!deployments.data && deployments.loading ? (
            <TableSkeleton columns={7} rows={6} />
          ) : items.length ? (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Deployment</th>
                    <th>Status</th>
                    <th>Monitoring status</th>
                    <th>Model version</th>
                    <th className="num">Last request</th>
                    <th className="actions-head" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((dep) => (
                    <tr
                      key={dep.id}
                      className={selectedId === dep.id ? 'is-selected' : ''}
                      onClick={() => setSelectedId(dep.id === selectedId ? null : dep.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <Link
                          to={`/deployments/${dep.id}?tab=overview`}
                          className="cell-link"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {dep.name}
                        </Link>
                        {dep.description ? (
                          <div className="cell-sub truncate" style={{ maxWidth: 280 }}>
                            {dep.description}
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <StatusPill
                          status={dep.status}
                          label={statusLabel(dep.status)}
                          tone={statusTone(dep.status)}
                        />
                      </td>
                      <td>
                        <StatusPill
                          status={dep.latest_monitoring_status || 'not_run'}
                          label={statusLabel(dep.latest_monitoring_status || 'not_run')}
                          tone={monitoringTone(dep.latest_monitoring_status)}
                        />
                      </td>
                      <td>
                        <strong>{dep.model_name}</strong>
                        <div className="cell-sub">
                          v{dep.model_version} &middot; {dep.algorithm.replaceAll('_', ' ')}
                        </div>
                      </td>
                      <td className="num">{relativeTime(dep.last_request_at)}</td>
                      <td className="actions-cell" onClick={(e) => e.stopPropagation()}>
                        <div className="button-group">
                          <Button
                            variant="ghost"
                            size="sm"
                            loading={scanningId === dep.id}
                            icon="refresh"
                            onClick={() => void runScan(dep.id)}
                          >
                            Scan
                          </Button>
                          <LinkButton
                            to={`/deployments/${dep.id}?tab=overview`}
                            variant="secondary"
                            size="sm"
                          >
                            Details
                          </LinkButton>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              compact
              icon="activity"
              title="No deployments found"
              description="Deploy a registered model to start tracking inference drift, latency, and ground-truth metrics."
              action={
                <LinkButton to="/deployments/new" variant="primary" icon="plus">
                  Create deployment
                </LinkButton>
              }
            />
          )}
        </div>

        {selectedDeployment && selectedMonitoring.data ? (
          <Panel>
            <div className="panel-header-with-action">
              <SectionHeader
                title={`Drift inspection: ${selectedDeployment.name}`}
                description={`Evaluation against ${selectedDeployment.model_name} v${selectedDeployment.model_version} training reference.`}
              />
              <div className="button-group">
                <Button
                  variant="secondary"
                  size="sm"
                  icon="refresh"
                  loading={scanningId === selectedDeployment.id}
                  onClick={() => void runScan(selectedDeployment.id)}
                >
                  Run scan now
                </Button>
                <LinkButton
                  to={`/deployments/${selectedDeployment.id}?tab=overview`}
                  variant="ghost"
                  size="sm"
                >
                  Full deployment view &rarr;
                </LinkButton>
              </div>
            </div>

            <div className="stack-gap-20">
              <div className="form-grid-3">
                <div className="definition-card">
                  <span className="definition-label">Data drift</span>
                  <strong className="definition-value">
                    {selectedMonitoring.data.data_drift_detected ? (
                      <StatusPill status="drifted" label="Drift detected" tone="negative" />
                    ) : (
                      <StatusPill status="stable" label="Stable" tone="positive" />
                    )}
                  </strong>
                  <span className="definition-sub">
                    Drift share: {formatShare(selectedMonitoring.data.drift_share)} &middot; Max PSI:{' '}
                    {selectedMonitoring.data.psi_max.toFixed(3)}
                  </span>
                </div>

                <div className="definition-card">
                  <span className="definition-label">Prediction drift</span>
                  <strong className="definition-value">
                    {selectedMonitoring.data.prediction_drift_detected ? (
                      <StatusPill status="drifted" label="Shifted" tone="negative" />
                    ) : (
                      <StatusPill status="stable" label="Stable" tone="positive" />
                    )}
                  </strong>
                  <span className="definition-sub">
                    PSI:{' '}
                    {selectedMonitoring.data.details?.prediction_drift?.psi?.toFixed(3) ??
                      '0.000'}
                  </span>
                </div>

                <div className="definition-card">
                  <span className="definition-label">Concept drift</span>
                  <strong className="definition-value">
                    {selectedMonitoring.data.concept_drift_detected ? (
                      <StatusPill status="drifted" label="Degraded" tone="negative" />
                    ) : (
                      <StatusPill status="stable" label="Stable" tone="positive" />
                    )}
                  </strong>
                  <span className="definition-sub">
                    {selectedMonitoring.data.labeled_count > 0
                      ? `${selectedMonitoring.data.labeled_count} labelled samples`
                      : 'Requires ground truth feedback'}
                  </span>
                </div>
              </div>

              {featureDriftList.length > 0 ? (
                <div>
                  <h4 style={{ marginBottom: 12 }}>Feature drift breakdown</h4>
                  <FeatureDriftList
                    features={featureDriftList}
                    threshold={selectedDeployment.config.psi_threshold}
                  />
                </div>
              ) : (
                <p className="chart-empty">No feature drift detected in the current window.</p>
              )}
            </div>
          </Panel>
        ) : null}
      </div>
    </>
  )
}

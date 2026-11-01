import { Link } from 'react-router-dom'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { Overview } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { BarList, ChartLegend, LineTrend, TrainingActivityChart } from '../components/charts'
import { Icon } from '../components/Icon'
import {
  EmptyState,
  ErrorBlock,
  KpiStrip,
  LinkButton,
  LoadingBlock,
  PageHeader,
  Panel,
  Pill,
  SectionHeader,
  StatusPill,
} from '../components/ui'
import {
  formatMetric,
  formatNumber,
  metricLabel,
  monitoringTone,
  primaryMetric,
  relativeTime,
  statusLabel,
  statusTone,
} from '../lib/format'

function OverviewSkeleton() {
  return (
    <div className="stack-gap-24">
      <div className="kpi-strip">
        {[0, 1, 2, 3].map((index) => (
          <div className="kpi" key={index}>
            <span className="skeleton" style={{ width: 70, height: 9 }} />
            <span className="skeleton" style={{ width: 50, height: 24, marginTop: 10 }} />
          </div>
        ))}
      </div>
      <div className="overview-grid">
        <LoadingBlock rows={6} />
        <LoadingBlock rows={4} />
      </div>
    </div>
  )
}

export function OverviewPage() {
  useDocumentTitle('Overview')
  const { project } = useWorkspace()
  const { data, loading, error, reload } = useApi<Overview>(
    project ? `/projects/${project.id}/overview` : null,
    undefined,
    { pollMs: 30000 },
  )

  const primary = data?.primary_metric ?? primaryMetric('classification')
  const liveDeployment =
    data?.deployment_health.find((item) => item.status === 'active') ?? data?.deployment_health[0]

  return (
    <>
      <PageHeader
        eyebrow="Project overview"
        title={project?.name ?? 'Overview'}
        description="Training, registry and deployment health for this project. Numbers refresh every 30 seconds."
        actions={
          <>
            <LinkButton to="/datasets?upload=1" variant="secondary" icon="upload">
              Upload dataset
            </LinkButton>
            <LinkButton to="/training/new" variant="primary" icon="plus">
              Train a model
            </LinkButton>
          </>
        }
      />

      {error && !data ? <ErrorBlock message={error} onRetry={reload} /> : null}
      {!data && loading ? <OverviewSkeleton /> : null}

      {data ? (
        <div className="stack-gap-24">
          {liveDeployment ? (
            <section className="hero-live">
              <div className="hero-live-main">
                <div className="inline-row-tight">
                  <span className="eyebrow-label">Live deployment</span>
                  <StatusPill
                    status={liveDeployment.status}
                    label={statusLabel(liveDeployment.status)}
                    tone={statusTone(liveDeployment.status)}
                  />
                  {liveDeployment.latest_monitoring_status ? (
                    <StatusPill
                      status={liveDeployment.latest_monitoring_status}
                      label={`Monitoring: ${statusLabel(liveDeployment.latest_monitoring_status)}`}
                      tone={monitoringTone(liveDeployment.latest_monitoring_status)}
                    />
                  ) : null}
                </div>
                <h2>{liveDeployment.name}</h2>
                <p>
                  Serving {liveDeployment.model_name} v{liveDeployment.model_version} through the
                  prediction API.
                </p>
              </div>
              <div className="hero-facts">
                <div className="hero-fact">
                  <span>Model version</span>
                  <strong>v{liveDeployment.model_version}</strong>
                </div>
                <div className="hero-fact">
                  <span>Last request</span>
                  <strong>{relativeTime(liveDeployment.last_request_at)}</strong>
                </div>
                <div className="hero-fact">
                  <span>Monitoring</span>
                  <strong>{statusLabel(liveDeployment.latest_monitoring_status)}</strong>
                </div>
                <div className="hero-fact">
                  <Link to={`/deployments/${liveDeployment.id}`} className="text-button">
                    Open <Icon name="arrow-right" size={13} />
                  </Link>
                </div>
              </div>
            </section>
          ) : (
            <EmptyState
              title="No deployment is serving this project"
              description="Register a trained experiment as a model version, then create an API-key deployment to start collecting predictions and drift signals."
              icon="rocket"
              action={
                <LinkButton to="/deployments" variant="secondary" icon="rocket">
                  Go to deployments
                </LinkButton>
              }
            />
          )}

          <KpiStrip
            items={[
              {
                label: 'Datasets',
                value: formatNumber(data.counts.datasets),
                sub: `${formatNumber(data.counts.dataset_versions)} versions`,
              },
              {
                label: 'Registered models',
                value: formatNumber(data.counts.registered_models),
                sub: `${formatNumber(data.counts.model_versions)} versions`,
              },
              {
                label: 'Active deployments',
                value: formatNumber(data.counts.active_deployments),
                sub: `${formatNumber(data.counts.training_jobs)} training jobs`,
              },
              {
                label: 'Predictions · 7d',
                value: formatNumber(data.counts.predictions_7d),
                sub: `${formatNumber(data.counts.completed_experiments)} completed experiments`,
              },
            ]}
          />

          <div className="overview-grid">
            <Panel>
              <SectionHeader
                title="Training activity"
                description="Runs by terminal state over the last 14 days."
                action={<Link className="text-button" to="/training">View training</Link>}
              />
              <ChartLegend
                items={[
                  { label: 'Completed', tone: 'accent' },
                  { label: 'Failed', tone: 'negative' },
                  { label: 'Running', tone: 'amber' },
                ]}
              />
              <TrainingActivityChart data={data.training_activity} />
            </Panel>

            <Panel>
              <SectionHeader
                title="Model performance"
                description={`Average ${metricLabel(primary)} on completed runs.`}
              />
              {data.model_performance.length ? (
                <BarList
                  items={data.model_performance.slice(0, 5).map((item) => ({
                    label: `${item.algorithm_label} · ${item.runs} run${item.runs === 1 ? '' : 's'}`,
                    value: item.average,
                    hint: `Best ${formatMetric(item.primary_metric, item.best)}`,
                  }))}
                  formatValue={(value) => formatMetric(primary, value)}
                />
              ) : (
                <p className="chart-empty">No completed experiments yet.</p>
              )}
            </Panel>
          </div>

          <div className="overview-grid">
            <div className="table-card">
              <div className="table-toolbar">
                <div className="table-toolbar-left">
                  <strong style={{ fontSize: 14, fontWeight: 500 }}>Recent training jobs</strong>
                </div>
                <div className="table-toolbar-right">
                  <Link className="text-button" to="/training">
                    View all <Icon name="arrow-right" size={13} />
                  </Link>
                </div>
              </div>
              {data.recent_jobs.length ? (
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Job</th>
                        <th>Status</th>
                        <th>Progress</th>
                        <th className="hide-sm">Problem</th>
                        <th className="num">Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent_jobs.slice(0, 6).map((job) => (
                        <tr key={job.id}>
                          <td>
                            <Link to={`/training/${job.id}`} className="cell-link">
                              {job.name}
                            </Link>
                          </td>
                          <td>
                            <StatusPill
                              status={job.status}
                              label={statusLabel(job.status)}
                              tone={statusTone(job.status)}
                            />
                          </td>
                          <td>
                            <div className="inline-row-tight" style={{ minWidth: 96 }}>
                              <div className="progress" style={{ width: 70 }}>
                                <span
                                  className="progress-fill"
                                  style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }}
                                />
                              </div>
                              <span className="cell-sub num" style={{ marginTop: 0 }}>
                                {job.progress}%
                              </span>
                            </div>
                          </td>
                          <td className="hide-sm muted">{job.problem_type}</td>
                          <td className="num muted">{relativeTime(job.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{ padding: 16 }}>
                  <EmptyState
                    compact
                    icon="flask"
                    title="No training jobs yet"
                    description="Create a run against a dataset version to produce comparable experiments."
                    action={
                      <LinkButton to="/training/new" size="sm" variant="secondary">
                        New training run
                      </LinkButton>
                    }
                  />
                </div>
              )}
            </div>

            <div className="overview-side">
              <Panel>
                <SectionHeader
                  title="Deployments"
                  description={`${data.deployment_health.length} total · ${data.counts.active_deployments} active`}
                />
                {data.deployment_health.length ? (
                  <div className="stack-sm">
                    {data.deployment_health.slice(0, 4).map((deployment) => (
                      <Link
                        key={deployment.id}
                        to={`/deployments/${deployment.id}`}
                        className="space-between"
                        style={{ padding: '8px 0', borderBottom: '1px solid var(--rule)' }}
                      >
                        <div className="min-w-0">
                          <div className="truncate" style={{ fontSize: 12.5, fontWeight: 500 }}>
                            {deployment.name}
                          </div>
                          <div className="cell-sub">
                            {deployment.model_name} v{deployment.model_version} ·{' '}
                            {relativeTime(deployment.last_request_at)}
                          </div>
                        </div>
                        <Pill
                          tone={
                            deployment.latest_monitoring_status
                              ? monitoringTone(deployment.latest_monitoring_status)
                              : statusTone(deployment.status)
                          }
                          dot
                        >
                          {statusLabel(
                            deployment.latest_monitoring_status ?? deployment.status,
                          )}
                        </Pill>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <p className="chart-empty">No deployments yet.</p>
                )}
              </Panel>

              <Panel>
                <SectionHeader title="Recent activity" description="Audited project events." />
                {data.recent_events.length ? (
                  <div className="stack-sm">
                    {data.recent_events.slice(0, 5).map((event) => (
                      <div
                        key={`${event.id}-${event.action}-${event.resource_type}-${event.resource_id ?? 'none'}`}
                        style={{ padding: '7px 0', borderBottom: '1px solid var(--rule)' }}
                      >
                        <div style={{ fontSize: 12.5 }}>{event.action.replaceAll('.', ' · ')}</div>
                        <div className="cell-sub">
                          {event.resource_type} · {relativeTime(event.created_at)}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="chart-empty">No activity recorded yet.</p>
                )}
              </Panel>
            </div>
          </div>

          {data.experiment_performance.length ? (
            <div className="overview-grid">
              <Panel>
                <SectionHeader
                  title="Experiment performance"
                  description={`${metricLabel(primary)} for recent completed experiments.`}
                />
                <LineTrend
                  data={data.experiment_performance
                    .slice()
                    .reverse()
                    .map((point) => ({
                      label: new Intl.DateTimeFormat('en-US', {
                        month: 'short',
                        day: 'numeric',
                      }).format(new Date(point.date)),
                      value: point.value,
                      title: `${point.name} · ${point.algorithm} · ${formatMetric(point.primary_metric, point.value)}`,
                    }))}
                  formatValue={(value) => formatMetric(primary, value)}
                  ariaLabel="Experiment primary metric"
                />
              </Panel>
              <Panel>
                <SectionHeader title="Latest registered models" />
                {data.latest_models.length ? (
                  <div className="stack-sm">
                    {data.latest_models.slice(0, 5).map((model) => (
                      <Link
                        key={model.id}
                        to={`/models/${model.id}`}
                        className="space-between"
                        style={{ padding: '7px 0', borderBottom: '1px solid var(--rule)' }}
                      >
                        <div className="min-w-0">
                          <div className="truncate" style={{ fontSize: 12.5, fontWeight: 500 }}>
                            {model.name}
                          </div>
                          <div className="cell-sub">
                            v{model.version} · {model.algorithm.replaceAll('_', ' ')}
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <Pill tone={statusTone(model.stage)}>{statusLabel(model.stage)}</Pill>
                          <div className="cell-sub num" style={{ marginTop: 4 }}>
                            {formatMetric(primary, model.metrics[primary] ?? null)}
                          </div>
                        </div>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <p className="chart-empty">No models registered yet.</p>
                )}
              </Panel>
            </div>
          ) : null}
        </div>
      ) : null}
    </>
  )
}

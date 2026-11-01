import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { TrainingJobDetail, TrainingJobLogs } from '../api/types'
import { Icon } from '../components/Icon'
import { useToast } from '../components/ToastProvider'
import {
  Button,
  ConfirmDialog,
  DefinitionGrid,
  EmptyState,
  ErrorBlock,
  InlineNotice,
  JsonBlock,
  LinkButton,
  LoadingBlock,
  PageHeader,
  Panel,
  Pill,
  ProgressBar,
  SectionHeader,
  StatusPill,
  Tabs,
} from '../components/ui'
import {
  formatDateTime,
  formatDuration,
  formatMetric,
  metricLabel,
  primaryMetric,
  shortId,
  statusLabel,
  statusTone,
  titleCase,
} from '../lib/format'

type JobTab = 'overview' | 'logs' | 'configuration'

function ExperimentRows({ job }: { job: TrainingJobDetail }) {
  const metric = primaryMetric(job.problem_type)
  if (job.experiments.length) {
    return (
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Experiment</th>
              <th>Algorithm</th>
              <th>Status</th>
              <th className="num">{metricLabel(metric)}</th>
              <th className="num hide-sm">Duration</th>
              <th className="hide-sm">Registry</th>
              <th className="actions-head" />
            </tr>
          </thead>
          <tbody>
            {job.experiments.map((experiment) => (
              <tr key={experiment.id}>
                <td>
                  <Link to={`/experiments/${experiment.id}`} className="cell-link">
                    {experiment.name}
                  </Link>
                  {experiment.error_message ? (
                    <div className="cell-sub truncate" style={{ maxWidth: 280 }}>
                      {experiment.error_message}
                    </div>
                  ) : null}
                </td>
                <td>
                  {experiment.algorithm_label}
                  <div className="cell-sub mono">{experiment.algorithm}</div>
                </td>
                <td>
                  <StatusPill
                    status={experiment.status}
                    label={statusLabel(experiment.status)}
                    tone={statusTone(experiment.status)}
                  />
                </td>
                <td className="num">
                  {experiment.status === 'completed'
                    ? formatMetric(metric, experiment.metrics[metric])
                    : '—'}
                </td>
                <td className="num hide-sm muted">
                  {formatDuration(experiment.training_duration_seconds)}
                </td>
                <td className="hide-sm">
                  {experiment.registered_model_id ? (
                    <Link to={`/models/${experiment.registered_model_id}`} className="pill pill-info">
                      {experiment.registered_model_name ?? 'Model'} v
                      {experiment.registered_version}
                    </Link>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td className="actions-cell">
                  <Link
                    to={`/experiments/${experiment.id}`}
                    className="icon-button"
                    aria-label={`Open ${experiment.name}`}
                  >
                    <Icon name="chevron-right" size={15} />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  if (job.status === 'queued' || job.status === 'running') {
    return (
      <EmptyState
        compact
        icon="flask"
        title="Experiments are still running"
        description="Rows appear as each algorithm finishes. Open the logs tab for live progress."
        action={
          <Button size="sm" variant="secondary" onClick={() => undefined} disabled>
            Waiting
          </Button>
        }
      />
    )
  }
  return (
    <EmptyState
      compact
      icon="flask"
      title="No experiments were produced"
      description={
        job.error_message ??
        'The run did not create an experiment. Check the job logs and configuration.'
      }
    />
  )
}

export function TrainingJobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const toast = useToast()
  const [tab, setTab] = useState<JobTab>('overview')
  const [cancelOpen, setCancelOpen] = useState(false)
  const [cancelPending, setCancelPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const terminalRef = useRef<HTMLPreElement>(null)

  const job = useApi<TrainingJobDetail>(
    jobId ? `/training-jobs/${jobId}` : null,
    undefined,
    { pollMs: 0 },
  )
  const active = job.data?.status === 'queued' || job.data?.status === 'running'
  const logs = useApi<TrainingJobLogs>(
    jobId && tab === 'logs' ? `/training-jobs/${jobId}/logs` : null,
    { limit: 500 },
    { pollMs: active ? 2500 : undefined },
  )

  useDocumentTitle(job.data?.name ?? 'Training job')

  useEffect(() => {
    if (!terminalRef.current) return
    terminalRef.current.scrollTop = terminalRef.current.scrollHeight
  }, [logs.data])

  const cancel = async () => {
    if (!jobId) return
    setCancelPending(true)
    setActionError(null)
    try {
      await api.post(`/training-jobs/${jobId}/cancel`)
      toast.success('Cancellation requested.')
      setCancelOpen(false)
      job.reload()
    } catch (caught) {
      setActionError(errorMessage(caught))
      setCancelOpen(false)
    } finally {
      setCancelPending(false)
    }
  }

  if (job.error && !job.data) {
    return (
      <>
        <PageHeader backTo="/training" backLabel="Training" title="Training job unavailable" />
        <ErrorBlock message={job.error} onRetry={job.reload} />
      </>
    )
  }

  if (!job.data) {
    return (
      <>
        <PageHeader backTo="/training" backLabel="Training" title="Training job" />
        <LoadingBlock rows={8} />
      </>
    )
  }

  const current = job.data
  const metric = primaryMetric(current.problem_type)

  return (
    <>
      <PageHeader
        backTo="/training"
        backLabel="Training"
        eyebrow="Training run"
        title={current.name}
        description={
          <>
            {current.dataset_name} v{current.dataset_version} · {titleCase(current.problem_type)}
            {current.target_column ? ` · target ${current.target_column}` : ' · unsupervised'}
            {current.retrain_source_deployment_id ? (
              <>
                {' '}
                ·{' '}
                <Link to={`/deployments/${current.retrain_source_deployment_id}`} className="inline-link">
                  retrain of deployment
                </Link>
              </>
            ) : null}
          </>
        }
        actions={
          <>
            {active ? (
              <Button variant="danger-ghost" icon="stop" onClick={() => setCancelOpen(true)}>
                Cancel run
              </Button>
            ) : null}
            <LinkButton to="/training/new" variant="secondary" icon="plus">
              New run
            </LinkButton>
          </>
        }
      />

      {actionError ? <ErrorBlock message={actionError} /> : null}

      <Panel className="job-status-panel">
        <div className="job-status-head">
          <div className="inline-row-tight">
            <StatusPill
              status={current.status}
              label={statusLabel(current.status)}
              tone={statusTone(current.status)}
            />
            <span className="muted">{current.status_message ?? 'No status message'}</span>
            {active ? (
              <span className="inline-row-tight" style={{ marginLeft: 4 }}>
                <span className="live-dot" />
                <span className="cell-sub" style={{ marginTop: 0 }}>
                  Live
                </span>
              </span>
            ) : null}
          </div>
          <span className="num" style={{ fontSize: 20, letterSpacing: '-0.02em' }}>
            {current.progress}%
          </span>
        </div>
        <ProgressBar
          value={current.progress}
          tone={current.status === 'failed' ? 'negative' : current.status === 'completed' ? 'positive' : 'accent'}
          label={`Training progress ${current.progress}%`}
        />
        <div className="job-status-facts">
          <div>
            <span>Started</span>
            <strong>{current.started_at ? formatDateTime(current.started_at) : 'Waiting'}</strong>
          </div>
          <div>
            <span>Duration</span>
            <strong className="num">{formatDuration(current.duration_seconds)}</strong>
          </div>
          <div>
            <span>Algorithms</span>
            <strong className="num">{current.algorithm_count}</strong>
          </div>
          <div>
            <span>Experiments</span>
            <strong className="num">{current.experiments.length}</strong>
          </div>
          <div>
            <span>Seed</span>
            <strong className="num">{String(current.config.random_seed ?? '—')}</strong>
          </div>
        </div>
      </Panel>

      {current.status === 'failed' && current.error_message ? (
        <div style={{ marginTop: 16 }}>
          <InlineNotice tone="negative" title="Training failed">
            {current.error_message}
          </InlineNotice>
        </div>
      ) : null}

      <div style={{ marginTop: 20 }}>
        <Tabs
          items={[
            { id: 'overview', label: 'Overview' },
            { id: 'logs', label: 'Logs' },
            { id: 'configuration', label: 'Configuration' },
          ]}
          value={tab}
          onChange={(value) => setTab(value as JobTab)}
          ariaLabel="Training job sections"
        />
      </div>

      {tab === 'overview' ? (
        <div className="job-layout">
          <Panel className="flush-panel">
            <div className="panel-inner-head">
              <SectionHeader
                title="Experiments"
                description={`${metricLabel(metric)} is the primary metric for ${titleCase(current.problem_type)}.`}
              />
            </div>
            <ExperimentRows job={current} />
          </Panel>
          <Panel>
            <SectionHeader title="Run details" />
            <DefinitionGrid
              items={[
                { label: 'Dataset', value: `${current.dataset_name} v${current.dataset_version}` },
                { label: 'Problem', value: titleCase(current.problem_type) },
                { label: 'Target', value: <span className="mono">{current.target_column ?? 'None'}</span> },
                {
                  label: 'Features',
                  value: current.feature_columns?.length
                    ? `${current.feature_columns.length} selected`
                    : 'All available',
                },
                { label: 'Created', value: formatDateTime(current.created_at) },
                { label: 'Created by', value: <span className="mono">{shortId(current.created_by)}</span> },
                { label: 'Completed', value: formatDateTime(current.completed_at) },
                { label: 'Job ID', value: <span className="mono">{shortId(current.id)}</span> },
              ]}
            />
            {!active && current.experiments.length >= 2 ? (
              <div className="panel-note">
                <Link
                  className="text-button"
                  to={`/experiments/compare?ids=${current.experiments
                    .slice(0, 6)
                    .map((experiment) => experiment.id)
                    .join(',')}`}
                >
                  Compare this run’s experiments <Icon name="arrow-right" size={13} />
                </Link>
              </div>
            ) : null}
          </Panel>
        </div>
      ) : null}

      {tab === 'logs' ? (
        <Panel className="flush-panel">
          <div className="table-toolbar">
            <div className="table-toolbar-left">
              <span className="table-count">
                {logs.data ? `${logs.data.items.length} log lines` : 'Logs'}
              </span>
            </div>
            <div className="table-toolbar-right">
              <Button size="sm" variant="ghost" icon="refresh" onClick={logs.reload}>
                Refresh
              </Button>
            </div>
          </div>
          {logs.error ? (
            <div style={{ padding: 16 }}>
              <ErrorBlock message={logs.error} onRetry={logs.reload} />
            </div>
          ) : null}
          {logs.data?.items.length ? (
            <pre className="log-terminal" ref={terminalRef}>
              {logs.data.items.map((line) => (
                <span className={`log-line log-${line.level}`} key={line.id}>
                  <span className="log-time">{formatDateTime(line.created_at)}</span>
                  <span className="log-level">{line.level.toUpperCase()}</span>
                  <span>{line.message}</span>
                </span>
              ))}
            </pre>
          ) : logs.loading ? (
            <LoadingBlock rows={6} />
          ) : (
            <EmptyState
              compact
              icon="terminal"
              title="No log lines yet"
              description="Logs appear once the worker starts processing this job."
            />
          )}
        </Panel>
      ) : null}

      {tab === 'configuration' ? (
        <div className="settings-grid">
          <Panel>
            <SectionHeader title="Algorithms" />
            <div className="stack-sm">
              {current.algorithms.map((algorithm, index) => {
                const selection = algorithm as { algorithm?: string; hyperparameters?: Record<string, unknown> }
                return (
                  <div className="config-algorithm" key={`${selection.algorithm ?? 'algorithm'}-${index}`}>
                    <div className="space-between">
                      <span className="mono" style={{ fontWeight: 500 }}>
                        {selection.algorithm ?? 'Unknown algorithm'}
                      </span>
                      <Pill tone="neutral">Selected</Pill>
                    </div>
                    {selection.hyperparameters ? (
                      <div className="param-chips">
                        {Object.entries(selection.hyperparameters).map(([name, value]) => (
                          <span className="param-chip" key={name}>
                            {name}=<strong>{String(value)}</strong>
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </Panel>
          <Panel>
            <SectionHeader title="Configuration" />
            <JsonBlock value={current.config} />
          </Panel>
        </div>
      ) : null}

      <ConfirmDialog
        open={cancelOpen}
        onClose={() => setCancelOpen(false)}
        title="Cancel this training run?"
        description="The worker stops at the next checkpoint. Experiments that already completed stay available."
        confirmLabel="Cancel run"
        pending={cancelPending}
        onConfirm={() => void cancel()}
      />
    </>
  )
}

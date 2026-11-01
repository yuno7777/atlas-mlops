import { useMemo, useState } from 'react'
import { api, errorMessage } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { BenchmarkReport, DatasetSummary, Page, PipelineRun, PipelineTemplate } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { useToast } from '../components/ToastProvider'
import {
  Button,
  EmptyState,
  ErrorBlock,
  Field,
  Input,
  KpiStrip,
  LoadingBlock,
  PageHeader,
  Panel,
  Pill,
  SectionHeader,
  Select,
  StatusPill,
} from '../components/ui'
import { formatDateTime, formatDuration, formatMetric, metricLabel, statusLabel, statusTone, titleCase } from '../lib/format'

export function BenchmarksPage() {
  useDocumentTitle('Benchmark Lab')
  const { project } = useWorkspace()
  const toast = useToast()
  const catalog = useApi<PipelineTemplate[]>('/benchmarks/catalog')
  const datasets = useApi<Page<DatasetSummary>>(project ? '/datasets' : null, {
    project_id: project?.id,
    page_size: 100,
  })
  const runs = useApi<PipelineRun[]>(project ? '/benchmarks/runs' : null, {
    project_id: project?.id,
    limit: 50,
  }, { pollMs: 10000 })
  const results = useApi<BenchmarkReport[]>(project ? '/benchmarks/results' : null, {
    project_id: project?.id,
    limit: 40,
  }, { pollMs: 15000 })

  const [templateId, setTemplateId] = useState<string | null>(null)
  const [datasetId, setDatasetId] = useState('')
  const [targetColumn, setTargetColumn] = useState('')
  const [auditColumns, setAuditColumns] = useState('')
  const [scheduleAt, setScheduleAt] = useState('')
  const [retryPending, setRetryPending] = useState<string | null>(null)
  const [runPending, setRunPending] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const selectedTemplate = catalog.data?.find((item) => item.id === templateId)
  const selectedDataset = datasets.data?.items.find((item) => item.latest_version_id === datasetId)
  const latestRun = useMemo(() => runs.data?.[0] ?? null, [runs.data])
  const completedRuns = runs.data?.filter((run) => run.status === 'completed').length ?? 0
  const cacheHits = runs.data?.filter((run) => run.cache_hit).length ?? 0

  const start = async () => {
    if (!project || !selectedTemplate || !datasetId) return
    setRunPending(true)
    setRunError(null)
    try {
      const result = await api.post<PipelineRun>('/benchmarks/run', {
        project_id: project.id,
        dataset_version_id: datasetId,
        template_id: selectedTemplate.id,
        target_column: selectedTemplate.problem_type === 'clustering' ? undefined : targetColumn.trim(),
        sensitive_columns: auditColumns.split(',').map((column) => column.trim()).filter(Boolean),
        test_size: 0.2,
        random_seed: 42,
        cv_folds: selectedTemplate.problem_type === 'clustering' ? 2 : 3,
        cache_enabled: true,
        max_attempts: 2,
        scheduled_at: scheduleAt ? new Date(scheduleAt).toISOString() : undefined,
      })
      toast.success(result.cache_hit ? 'Identical successful benchmark reused from cache.' : result.status === 'scheduled' ? 'Benchmark pipeline scheduled.' : 'Benchmark pipeline queued.')
      setTemplateId(null)
      setTargetColumn('')
      setAuditColumns('')
      setScheduleAt('')
      runs.reload()
    } catch (error) {
      setRunError(errorMessage(error))
    } finally {
      setRunPending(false)
    }
  }

  const retry = async (run: PipelineRun) => {
    setRetryPending(run.id)
    try {
      await api.post<PipelineRun>(`/workflows/runs/${run.id}/retry`)
      toast.success('Workflow retry queued as a new attempt.')
      runs.reload()
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setRetryPending(null)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Models and pipelines"
        title="Benchmark Lab"
        description="Run popular tabular model pipelines with a fixed holdout, seeded splits, cross-validation, subgroup evaluation, and an auditable run history."
      />

      <div className="stack-gap-24">
        <KpiStrip items={[
          { label: 'Pipeline recipes', value: catalog.data?.length ?? '—', sub: 'Classification, regression, clustering' },
          { label: 'Completed runs', value: completedRuns, sub: `${runs.data?.length ?? 0} runs recorded` },
          { label: 'Cache reuse', value: cacheHits, sub: 'Exact data and config matches' },
          { label: 'Latest run', value: latestRun ? statusLabel(latestRun.status) : '—', sub: latestRun ? formatDateTime(latestRun.created_at) : 'No run yet' },
        ]} />

        <Panel>
          <SectionHeader title="Popular model and pipeline recipes" description="Every model in a recipe uses the same dataset version, test fraction, seed, and cross-validation plan so scores are comparable within that run." />
          {catalog.error ? <ErrorBlock message={catalog.error} onRetry={catalog.reload} /> : null}
          {!catalog.data ? <LoadingBlock rows={4} /> : (
            <div className="pipeline-grid">
              {catalog.data.map((template) => (
                <article className="pipeline-card" key={template.id}>
                  <div className="pipeline-card-top">
                    <Pill tone="neutral">{titleCase(template.problem_type)}</Pill>
                    <span className="muted">{template.algorithms.length} model{template.algorithms.length === 1 ? '' : 's'}</span>
                  </div>
                  <h3>{template.name}</h3>
                  <p>{template.summary}</p>
                  <div className="pipeline-algorithms">
                    {template.algorithms.map((algorithm) => (
                      <span key={algorithm.algorithm}>{algorithm.algorithm.replaceAll('_', ' ')}</span>
                    ))}
                  </div>
                  <div className="pipeline-protocol">
                    <span>Holdout {Math.round((template.protocol.test_size ?? 0.2) * 100)}%</span>
                    <span>Seed {template.protocol.random_seed ?? 42}</span>
                    <span>{template.protocol.cv_folds ?? 3} folds</span>
                  </div>
                  <Button
                    variant={templateId === template.id ? 'secondary' : 'primary'}
                    icon="flask"
                    onClick={() => {
                      setTemplateId(template.id)
                      setDatasetId('')
                      setRunError(null)
                    }}
                  >
                    {templateId === template.id ? 'Selected' : 'Run recipe'}
                  </Button>
                </article>
              ))}
            </div>
          )}
        </Panel>

        {selectedTemplate ? (
          <Panel>
            <SectionHeader title={`Run ${selectedTemplate.name}`} description="The run stores the recipe, dataset checksum, parameters, and step state. Exact successful matches can reuse a cached result." />
            <div className="form-grid-3 pipeline-run-form">
              <Field label="Dataset version" htmlFor="benchmark-dataset" hint="Choose the exact uploaded version used by this benchmark.">
                <Select id="benchmark-dataset" value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
                  <option value="">Select a dataset</option>
                  {(datasets.data?.items ?? []).filter((dataset) => dataset.latest_version_id).map((dataset) => (
                    <option key={dataset.id} value={dataset.latest_version_id ?? ''}>
                      {dataset.name} · v{dataset.latest_version}
                    </option>
                  ))}
                </Select>
              </Field>
              {selectedTemplate.problem_type !== 'clustering' ? (
                <Field label="Target column" htmlFor="benchmark-target" hint="The target is excluded from model inputs.">
                  <Input id="benchmark-target" value={targetColumn} onChange={(event) => setTargetColumn(event.target.value)} placeholder="e.g. target" />
                </Field>
              ) : <div className="definition-card"><span className="definition-label">Target</span><strong className="definition-value">Unsupervised</strong><span className="definition-sub">Clustering recipe uses features only.</span></div>}
              {selectedTemplate.problem_type !== 'clustering' ? (
                <Field label="Sensitive audit columns (optional)" htmlFor="benchmark-audit" hint="Comma-separated columns are held out for subgroup metrics and excluded from training features.">
                  <Input id="benchmark-audit" value={auditColumns} onChange={(event) => setAuditColumns(event.target.value)} placeholder="e.g. region, age_band" />
                </Field>
              ) : null}
              <Field label="Schedule once (optional)" htmlFor="benchmark-schedule" hint="Requires the monitoring/workflow scheduler or Celery Beat to be active.">
                <Input id="benchmark-schedule" type="datetime-local" value={scheduleAt} onChange={(event) => setScheduleAt(event.target.value)} />
              </Field>
            </div>
            <div className="pipeline-dag-preview" aria-label="Pipeline workflow steps">
              {selectedTemplate.steps.map((step, index) => (
                <span key={step.id}>
                  <span className="workflow-step-node">{step.name}</span>
                  {index < selectedTemplate.steps.length - 1 ? <span className="workflow-step-arrow">→</span> : null}
                </span>
              ))}
            </div>
            {runError ? <div className="error-block" role="alert">{runError}</div> : null}
            <div className="form-actions">
              <Button variant="primary" icon="flask" loading={runPending} disabled={!datasetId || (selectedTemplate.problem_type !== 'clustering' && !targetColumn.trim())} onClick={() => void start()}>
                {scheduleAt ? 'Schedule benchmark' : 'Start benchmark'}
              </Button>
              <Button variant="ghost" onClick={() => setTemplateId(null)}>Close</Button>
              {selectedDataset ? <span className="muted">{selectedDataset.row_count?.toLocaleString() ?? '—'} rows · checksum-bound cache</span> : null}
            </div>
          </Panel>
        ) : null}

        <Panel>
          <SectionHeader title="Benchmark run history" description="Held-out metrics, CV mean/spread, wall-clock training time, fairness results, and workflow progress for reproducibility." action={<Button variant="ghost" size="sm" icon="refresh" onClick={() => { runs.reload(); results.reload() }}>Refresh</Button>} />
          {runs.error ? <ErrorBlock message={runs.error} onRetry={runs.reload} /> : null}
          {!runs.data && runs.loading ? <LoadingBlock rows={4} /> : runs.data?.length ? (
            <div className="stack-gap-16">
              {runs.data.map((run) => (
                <article className="benchmark-run" key={run.id}>
                  <div className="benchmark-run-heading">
                    <div>
                      <strong>{run.name}</strong>
                      <div className="cell-sub">{catalog.data?.find((item) => item.id === run.template_id)?.name ?? run.template_id} · {formatDateTime(run.created_at)} · attempt {run.attempt}/{run.max_attempts}{run.scheduled_at ? ` · scheduled ${formatDateTime(run.scheduled_at)}` : ''}</div>
                    </div>
                    <div className="button-group">
                      {run.cache_hit ? <Pill tone="positive">Cached</Pill> : null}
                      {run.status === 'failed' && run.attempt < run.max_attempts ? <Button size="sm" variant="secondary" loading={retryPending === run.id} onClick={() => void retry(run)}>Retry</Button> : null}
                      <StatusPill status={run.status} label={statusLabel(run.status)} tone={statusTone(run.status)} />
                    </div>
                  </div>
                  <div className="workflow-step-list">
                    {run.step_states.map((step) => (
                      <div className={`workflow-step-item is-${step.status}`} key={step.id} title={step.detail}>
                        <span className="workflow-step-dot" />
                        <span>{step.name}</span>
                        <small>{statusLabel(step.status)}</small>
                      </div>
                    ))}
                  </div>
                  {run.experiments.length ? (
                    <div className="table-wrap">
                      <table className="data">
                        <thead><tr><th>Model</th><th>Status</th><th className="num">Primary metric</th><th className="num">CV mean / std</th><th className="num">Train time</th></tr></thead>
                        <tbody>{run.experiments.map((experiment) => {
                          const primary = selectedMetric(run, catalog.data ?? [])
                          const mean = experiment.cv_metrics?.[`${primary}_mean`]
                          const spread = experiment.cv_metrics?.[`${primary}_std`]
                          return (
                            <tr key={experiment.id}>
                              <td>{experiment.algorithm_label}</td>
                              <td><StatusPill status={experiment.status} label={statusLabel(experiment.status)} tone={statusTone(experiment.status)} /></td>
                              <td className="num">{typeof experiment.metrics[primary] === 'number' ? formatMetric(primary, experiment.metrics[primary] as number) : '—'}</td>
                              <td className="num">{typeof mean === 'number' ? `${formatMetric(primary, mean)} ± ${typeof spread === 'number' ? formatMetric(primary, spread) : '—'}` : '—'}</td>
                              <td className="num">{experiment.training_duration_seconds === null ? '—' : formatDuration(experiment.training_duration_seconds)}</td>
                            </tr>
                          )
                        })}</tbody>
                      </table>
                    </div>
                  ) : null}
                  {run.error_message ? <p className="field-error">{run.error_message}</p> : null}
                </article>
              ))}
            </div>
          ) : (
            <EmptyState compact icon="activity" title="No benchmark runs yet" description="Choose a popular recipe above and compare its models on one dataset version." />
          )}
        </Panel>

        <Panel>
          <SectionHeader title="Recorded model comparisons" description="Completed experiments grouped by their original training job. Rows within a job share the same dataset version, split fraction, and seed; CV mean and spread are shown when available." />
          {results.error ? <ErrorBlock message={results.error} onRetry={results.reload} /> : null}
          {!results.data && results.loading ? <LoadingBlock rows={4} /> : results.data?.length ? (
            <div className="stack-gap-16">
              {results.data.map((report) => {
                const primary = String(report.protocol.primary_metric ?? 'accuracy')
                return (
                  <article className="benchmark-run" key={report.training_job_id}>
                    <div className="benchmark-run-heading">
                      <div>
                        <strong>{report.name}</strong>
                        <div className="cell-sub">{report.dataset_name} · v{report.dataset_version} · {titleCase(report.problem_type)} · {formatDateTime(report.created_at)}</div>
                      </div>
                      <div className="benchmark-protocol-note">
                        <span>{Math.round(Number(report.protocol.test_size ?? 0.2) * 100)}% holdout</span>
                        <span>seed {String(report.protocol.random_seed ?? 42)}</span>
                        <span>{String(report.protocol.cv_folds ?? 0)} CV folds</span>
                      </div>
                    </div>
                    <div className="table-wrap">
                      <table className="data">
                        <thead><tr><th>Algorithm</th><th className="num">{metricLabel(primary)}</th><th className="num">CV mean ± std</th><th className="num">Train time</th></tr></thead>
                        <tbody>{report.experiments.map((experiment) => {
                          const mean = experiment.cv_metrics?.[`${primary}_mean`]
                          const spread = experiment.cv_metrics?.[`${primary}_std`]
                          const metric = experiment.metrics[primary]
                          return (
                            <tr key={experiment.id}>
                              <td>{experiment.algorithm_label}</td>
                              <td className="num">{metric === null || metric === undefined ? '—' : formatMetric(primary, metric)}</td>
                              <td className="num">{typeof mean === 'number' ? `${formatMetric(primary, mean)} ± ${typeof spread === 'number' ? formatMetric(primary, spread) : '—'}` : '—'}</td>
                              <td className="num">{experiment.training_duration_seconds === null ? '—' : formatDuration(experiment.training_duration_seconds)}</td>
                            </tr>
                          )
                        })}</tbody>
                      </table>
                    </div>
                  </article>
                )
              })}
            </div>
          ) : <EmptyState compact icon="chart" title="No completed comparisons yet" description="Completed training jobs will appear here with their split, seed, CV, metric, and timing context." />}
        </Panel>
      </div>
    </>
  )
}

function selectedMetric(run: PipelineRun, templates: PipelineTemplate[]): string {
  const template = templates.find((item) => item.id === run.template_id)
  return template?.metric_keys[0] ?? 'accuracy'
}

import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type {
  ExperimentCompare,
  ExperimentSummary,
  Page,
} from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Icon } from '../components/Icon'
import {
  Button,
  Checkbox,
  EmptyState,
  ErrorBlock,
  LinkButton,
  LoadingBlock,
  Modal,
  PageHeader,
  Pill,
  SearchInput,
  StatusPill,
} from '../components/ui'
import {
  formatMetric,
  metricLabel,
  statusLabel,
  statusTone,
  titleCase,
} from '../lib/format'

export function CompareExperimentsPage() {
  useDocumentTitle('Compare experiments')
  const { project } = useWorkspace()
  const [searchParams, setSearchParams] = useSearchParams()
  const ids = useMemo(() => {
    const raw = searchParams.get('ids') ?? ''
    return Array.from(new Set(raw.split(',').filter(Boolean))).slice(0, 6)
  }, [searchParams])
  const idsKey = ids.join(',')

  const [comparison, setComparison] = useState<ExperimentCompare | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [draft, setDraft] = useState<string[]>([])
  const [pickerSearch, setPickerSearch] = useState('')

  useEffect(() => {
    if (ids.length < 2) {
      setComparison(null)
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .post<ExperimentCompare>('/experiments/compare', { experiment_ids: ids })
      .then((data) => {
        if (!cancelled) setComparison(data)
      })
      .catch((caught) => {
        if (!cancelled) {
          setComparison(null)
          setError(errorMessage(caught))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey])

  const openPicker = () => {
    setDraft(ids)
    setPickerSearch('')
    setPickerOpen(true)
  }

  const applyPicker = () => {
    if (draft.length < 2) return
    setSearchParams({ ids: draft.join(',') }, { replace: true })
    setPickerOpen(false)
  }

  if (ids.length < 2) {
    return (
      <>
        <PageHeader
          backTo="/experiments"
          backLabel="Experiments"
          title="Compare experiments"
          description="Choose two to six completed experiments from the same problem type."
        />
        <EmptyState
          icon="chart"
          title="Select at least two experiments"
          description="Comparison aligns metrics and hyperparameters side by side, and marks the best value for every metric."
          action={
            <LinkButton to="/experiments" variant="secondary" icon="activity">
              Choose experiments
            </LinkButton>
          }
        />
      </>
    )
  }

  return (
    <>
      <PageHeader
        backTo="/experiments"
        backLabel="Experiments"
        eyebrow="Comparison"
        title={`${ids.length} experiments`}
        description={
          comparison
            ? `${titleCase(comparison.problem_type)} · metrics and hyperparameters aligned by run.`
            : 'Same-problem experiments only. Best values are marked for each metric.'
        }
        actions={
          <>
            <Button variant="secondary" icon="sliders" onClick={openPicker}>
              Change selection
            </Button>
            {comparison ? (
              <LinkButton to="/models" variant="primary" icon="cube">
                Model registry
              </LinkButton>
            ) : null}
          </>
        }
      />

      {error ? (
        <div className="stack-gap-16">
          <ErrorBlock message={error} onRetry={() => setSearchParams({ ids: idsKey }, { replace: true })} />
          <EmptyState
            compact
            icon="chart"
            title="These experiments cannot be compared"
            description="Experiments must share a problem type. Replace one or more selections and try again."
            action={
              <Button variant="secondary" size="sm" onClick={openPicker}>
                Change selection
              </Button>
            }
          />
        </div>
      ) : null}

      {loading && !comparison ? <LoadingBlock rows={10} /> : null}

      {comparison ? (
        <div className="compare-card">
          <div className="table-wrap compare-wrap">
            <table className="compare-table">
              <thead>
                <tr>
                  <th className="compare-corner">
                    <span className="eyebrow-label">Metric</span>
                  </th>
                  {comparison.experiments.map((experiment) => (
                    <th key={experiment.id} className="compare-experiment-head">
                      <Link to={`/experiments/${experiment.id}`} className="cell-link">
                        {experiment.name}
                      </Link>
                      <div className="compare-head-meta">
                        {experiment.algorithm_label} · {experiment.dataset_name} v
                        {experiment.dataset_version}
                      </div>
                      <div className="compare-head-badges">
                        <StatusPill
                          status={experiment.status}
                          label={statusLabel(experiment.status)}
                          tone={statusTone(experiment.status)}
                        />
                        {experiment.registered_model_id ? (
                          <Link
                            to={`/models/${experiment.registered_model_id}`}
                            className="pill pill-info"
                          >
                            Registered
                          </Link>
                        ) : null}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="compare-section-row">
                  <th colSpan={comparison.experiments.length + 1}>
                    <span>Evaluation</span>
                    <span className="muted">Best value per row</span>
                  </th>
                </tr>
                {comparison.metric_keys.map((key) => {
                  const best = comparison.best[key]
                  const direction = comparison.directions[key] ?? 'higher'
                  return (
                    <tr key={key}>
                      <th className="compare-metric-name">
                        {metricLabel(key)}
                        <span className="compare-direction">
                          <Icon
                            name={direction === 'min' ? 'arrow-down-right' : 'arrow-up-right'}
                            size={11}
                          />
                          {direction === 'min' ? 'Lower is better' : 'Higher is better'}
                        </span>
                      </th>
                      {comparison.experiments.map((experiment) => {
                        const isBest = best?.experiment_id === experiment.id
                        return (
                          <td key={experiment.id} className={`num ${isBest ? 'is-best' : ''}`}>
                            <span className="compare-value">
                              {formatMetric(key, experiment.metrics[key])}
                            </span>
                            {isBest ? <span className="best-mark">Best</span> : null}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
                <tr className="compare-section-row">
                  <th colSpan={comparison.experiments.length + 1}>
                    <span>Hyperparameters</span>
                    <span className="muted">Values supplied for this run</span>
                  </th>
                </tr>
                {parameterKeys(comparison.experiments).map((key) => (
                  <tr key={key}>
                    <th className="compare-metric-name">
                      <span className="mono">{key}</span>
                    </th>
                    {comparison.experiments.map((experiment) => {
                      const value = experiment.params[key]
                      return (
                        <td key={experiment.id} className="param-cell">
                          {value === undefined ? (
                            <span className="cell-null">—</span>
                          ) : typeof value === 'object' ? (
                            <code className="inline-code">{JSON.stringify(value)}</code>
                          ) : (
                            <span className="mono">{String(value)}</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
                <tr className="compare-section-row">
                  <th colSpan={comparison.experiments.length + 1}>
                    <span>Run</span>
                    <span className="muted">Retention and tracking</span>
                  </th>
                </tr>
                <tr>
                  <th className="compare-metric-name">Registered model</th>
                  {comparison.experiments.map((experiment) => (
                    <td key={experiment.id}>
                      {experiment.registered_model_id ? (
                        <Link
                          to={`/models/${experiment.registered_model_id}`}
                          className="inline-link"
                        >
                          {experiment.registered_model_name} v{experiment.registered_version}
                        </Link>
                      ) : (
                        <span className="cell-null">Not registered</span>
                      )}
                    </td>
                  ))}
                </tr>
                <tr>
                  <th className="compare-metric-name">Training job</th>
                  {comparison.experiments.map((experiment) => (
                    <td key={experiment.id}>
                      <Link to={`/training/${experiment.training_job_id}`} className="inline-link">
                        Open job
                      </Link>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      <ComparePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        projectId={project?.id ?? null}
        selected={draft}
        onSelected={setDraft}
        search={pickerSearch}
        onSearch={setPickerSearch}
        onApply={applyPicker}
      />
    </>
  )
}

function parameterKeys(experiments: ExperimentSummary[]): string[] {
  const keys = new Set<string>()
  for (const experiment of experiments) {
    for (const key of Object.keys(experiment.params)) keys.add(key)
  }
  return Array.from(keys).sort()
}

function ComparePicker({
  open,
  onClose,
  projectId,
  selected,
  onSelected,
  search,
  onSearch,
  onApply,
}: {
  open: boolean
  onClose: () => void
  projectId: string | null
  selected: string[]
  onSelected: (ids: string[]) => void
  search: string
  onSearch: (value: string) => void
  onApply: () => void
}) {
  const [debounced, setDebounced] = useState('')
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 200)
    return () => window.clearTimeout(timer)
  }, [search])

  const experiments = useApi<Page<ExperimentSummary>>(
    open && projectId ? '/experiments' : null,
    {
      project_id: projectId ?? undefined,
      status: 'completed',
      search: debounced || undefined,
      page_size: 100,
      sort: '-created_at',
    },
  )

  const toggle = (id: string) => {
    if (selected.includes(id)) {
      onSelected(selected.filter((item) => item !== id))
      return
    }
    if (selected.length >= 6) return
    onSelected([...selected, id])
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Choose experiments"
      description="Pick two to six completed experiments with the same problem type."
      width={680}
      footer={
        <>
          <span className="modal-selection-count">
            {selected.length} of 6 selected
          </span>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" disabled={selected.length < 2} onClick={onApply}>
            Apply selection
          </Button>
        </>
      }
    >
      <div className="form-stack">
        <SearchInput value={search} onChange={onSearch} placeholder="Search experiments" />
        {experiments.error ? (
          <ErrorBlock compact message={experiments.error} onRetry={experiments.reload} />
        ) : null}
        {experiments.loading ? <LoadingBlock rows={5} /> : null}
        {experiments.data?.items.length ? (
          <div className="picker-list">
            {experiments.data.items.map((experiment) => {
              const checked = selected.includes(experiment.id)
              return (
                <label
                  key={experiment.id}
                  className={`picker-row ${checked ? 'is-selected' : ''}`}
                >
                  <Checkbox
                    checked={checked}
                    onChange={() => toggle(experiment.id)}
                    disabled={!checked && selected.length >= 6}
                    label={
                      <span className="picker-main">
                        <span>
                          <strong>{experiment.name}</strong>
                          <span className="picker-meta">
                            {experiment.algorithm_label} · {experiment.dataset_name} v
                            {experiment.dataset_version}
                          </span>
                        </span>
                        <Pill tone="neutral">{titleCase(experiment.problem_type)}</Pill>
                      </span>
                    }
                  />
                </label>
              )
            })}
          </div>
        ) : experiments.data ? (
          <p className="chart-empty">No completed experiments match this search.</p>
        ) : null}
        {selected.length > 0 ? (
          <div className="picker-selected">
            <span className="field-label">Selected</span>
            <div className="param-chips">
              {selected.map((id) => {
                const match = experiments.data?.items.find((item) => item.id === id)
                return (
                  <span className="param-chip" key={id}>
                    {match?.name ?? id.slice(0, 8)}
                    <button
                      type="button"
                      className="chip-remove"
                      aria-label="Remove from comparison"
                      onClick={() => onSelected(selected.filter((item) => item !== id))}
                    >
                      <Icon name="close" size={11} />
                    </button>
                  </span>
                )
              })}
            </div>
          </div>
        ) : null}
      </div>
    </Modal>
  )
}

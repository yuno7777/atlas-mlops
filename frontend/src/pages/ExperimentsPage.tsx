import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { ExperimentSummary, Page } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Icon } from '../components/Icon'
import {
  Button,
  Checkbox,
  EmptyState,
  ErrorBlock,
  LinkButton,
  PageHeader,
  Pagination,
  SearchInput,
  Select,
  StatusPill,
  TableSkeleton,
} from '../components/ui'
import {
  formatDuration,
  formatMetric,
  metricLabel,
  primaryMetric,
  relativeTime,
  statusLabel,
  statusTone,
  titleCase,
} from '../lib/format'

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'completed', label: 'Completed' },
  { value: 'running', label: 'Running' },
  { value: 'queued', label: 'Queued' },
  { value: 'failed', label: 'Failed' },
]

export function ExperimentsPage() {
  useDocumentTitle('Experiments')
  const { project } = useWorkspace()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [status, setStatus] = useState('')
  const [problemType, setProblemType] = useState('')
  const [sort, setSort] = useState('-created_at')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string[]>([])

  const experiments = useApi<Page<ExperimentSummary>>(
    project ? '/experiments' : null,
    {
      project_id: project?.id,
      status: status || undefined,
      problem_type: problemType || undefined,
      search: debouncedSearch || undefined,
      sort,
      page,
      page_size: 25,
    },
  )

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search.trim())
      setPage(1)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    setPage(1)
  }, [project?.id, status, problemType, sort])

  const toggle = (id: string) => {
    setSelected((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id)
      if (current.length >= 6) return current
      return [...current, id]
    })
  }

  const compare = () => {
    if (selected.length < 2) return
    navigate(`/experiments/compare?ids=${selected.join(',')}`)
  }

  return (
    <>
      <PageHeader
        title="Experiments"
        description="Every algorithm run with its metrics and hyperparameters. Select two to six runs from the same problem type to compare them side by side."
        actions={
          <LinkButton to="/training/new" variant="primary" icon="plus">
            New training run
          </LinkButton>
        }
      />

      <div className="table-card">
        <div className="table-toolbar table-toolbar-wrap">
          <div className="table-toolbar-left">
            <div className="filter-chips" role="group" aria-label="Filter by status">
              {STATUS_FILTERS.map((filter) => (
                <button
                  key={filter.value}
                  type="button"
                  className={`filter-chip ${status === filter.value ? 'is-active' : ''}`}
                  onClick={() => setStatus(filter.value)}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          </div>
          <div className="table-toolbar-right">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Search experiments"
              ariaLabel="Search experiments"
            />
            <Select
              value={problemType}
              onChange={(event) => setProblemType(event.target.value)}
              aria-label="Filter by problem type"
              style={{ width: 160 }}
            >
              <option value="">All problems</option>
              <option value="classification">Classification</option>
              <option value="regression">Regression</option>
              <option value="clustering">Clustering</option>
            </Select>
            <Select
              value={sort}
              onChange={(event) => setSort(event.target.value)}
              aria-label="Sort experiments"
              style={{ width: 150 }}
            >
              <option value="-created_at">Newest first</option>
              <option value="created_at">Oldest first</option>
              <option value="name">Name A–Z</option>
              <option value="-duration">Longest duration</option>
            </Select>
          </div>
        </div>

        {selected.length ? (
          <div className="selection-bar">
            <span>
              <strong>{selected.length}</strong> selected
              <span className="muted"> · choose up to 6 from the same problem type</span>
            </span>
            <div className="inline-row">
              <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
                Clear
              </Button>
              <Button size="sm" variant="primary" disabled={selected.length < 2} onClick={compare}>
                Compare {selected.length >= 2 ? `${selected.length} experiments` : ''}
              </Button>
            </div>
          </div>
        ) : null}

        {experiments.error ? (
          <div style={{ padding: 16 }}>
            <ErrorBlock message={experiments.error} onRetry={experiments.reload} />
          </div>
        ) : null}

        {!experiments.data && experiments.loading ? (
          <TableSkeleton columns={7} rows={8} />
        ) : experiments.data?.items.length ? (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th className="check-cell" />
                    <th>Experiment</th>
                    <th>Algorithm</th>
                    <th>Status</th>
                    <th className="num">Primary metric</th>
                    <th className="num hide-sm">Duration</th>
                    <th className="hide-sm">Registry</th>
                    <th className="num">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {experiments.data.items.map((experiment) => {
                    const metric = primaryMetric(experiment.problem_type)
                    const disabled = experiment.status !== 'completed'
                    return (
                      <tr key={experiment.id}>
                        <td className="check-cell">
                          <Checkbox
                            label={<span className="sr-only">Select {experiment.name}</span>}
                            checked={selected.includes(experiment.id)}
                            onChange={() => toggle(experiment.id)}
                            disabled={disabled || (selected.length >= 6 && !selected.includes(experiment.id))}
                          />
                        </td>
                        <td>
                          <Link to={`/experiments/${experiment.id}`} className="cell-link">
                            {experiment.name}
                          </Link>
                          <div className="cell-sub">
                            {experiment.dataset_name ?? 'Dataset'} v
                            {experiment.dataset_version ?? '—'} ·{' '}
                            {titleCase(experiment.problem_type)}
                          </div>
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
                          <strong>
                            {formatMetric(metric, experiment.metrics[metric])}
                          </strong>
                          <div className="cell-sub">{metricLabel(metric)}</div>
                        </td>
                        <td className="num hide-sm muted">
                          {formatDuration(experiment.training_duration_seconds)}
                        </td>
                        <td className="hide-sm">
                          {experiment.registered_model_id ? (
                            <Link
                              to={`/models/${experiment.registered_model_id}`}
                              className="pill pill-info"
                            >
                              {experiment.registered_model_name ?? 'Model'} v
                              {experiment.registered_version}
                            </Link>
                          ) : (
                            <span className="muted">Not registered</span>
                          )}
                        </td>
                        <td className="num muted">{relativeTime(experiment.created_at)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <Pagination
              page={experiments.data.page}
              pages={experiments.data.pages}
              total={experiments.data.total}
              pageSize={experiments.data.page_size}
              onChange={setPage}
            />
          </>
        ) : experiments.data ? (
          <div style={{ padding: 16 }}>
            {search || status || problemType ? (
              <EmptyState
                compact
                icon="search"
                title="No experiments match these filters"
                description="Try a different search, status or problem type."
                action={
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      setSearch('')
                      setStatus('')
                      setProblemType('')
                    }}
                  >
                    Clear filters
                  </button>
                }
              />
            ) : (
              <EmptyState
                icon="activity"
                title="No experiments yet"
                description="Experiments appear after a training run completes an algorithm. They hold the metrics used for comparison and registry promotion."
                action={
                  <LinkButton to="/training/new" variant="secondary" icon="plus">
                    Start a training run
                  </LinkButton>
                }
              />
            )}
          </div>
        ) : null}

        {selected.length ? (
          <div className="table-footnote">
            <Icon name="info" size={12} /> Completed experiments only
          </div>
        ) : null}
      </div>
    </>
  )
}

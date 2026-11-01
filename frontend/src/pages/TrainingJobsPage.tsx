import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { Page, TrainingJobSummary } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Icon } from '../components/Icon'
import {
  EmptyState,
  ErrorBlock,
  LinkButton,
  PageHeader,
  Pagination,
  ProgressBar,
  SearchInput,
  StatusPill,
  TableSkeleton,
} from '../components/ui'
import {
  formatDuration,
  formatNumber,
  relativeTime,
  statusLabel,
  statusTone,
  titleCase,
} from '../lib/format'

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'queued', label: 'Queued' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
]

export function TrainingJobsPage() {
  useDocumentTitle('Training')
  const { project } = useWorkspace()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)

  const jobs = useApi<Page<TrainingJobSummary>>(
    project ? '/training-jobs' : null,
    {
      project_id: project?.id,
      status: status || undefined,
      search: debouncedSearch || undefined,
      page,
      page_size: 20,
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
  }, [project?.id, status])

  return (
    <>
      <PageHeader
        title="Training"
        description="Queue reproducible runs across dataset versions and algorithms. Each selected algorithm produces its own experiment."
        actions={
          <LinkButton to="/training/new" variant="primary" icon="plus">
            New training run
          </LinkButton>
        }
      />

      <div className="table-card">
        <div className="table-toolbar">
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
              placeholder="Search jobs"
              ariaLabel="Search training jobs"
            />
          </div>
        </div>

        {jobs.error ? (
          <div style={{ padding: 16 }}>
            <ErrorBlock message={jobs.error} onRetry={jobs.reload} />
          </div>
        ) : null}

        {!jobs.data && jobs.loading ? (
          <TableSkeleton columns={6} rows={7} />
        ) : jobs.data?.items.length ? (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Status</th>
                    <th style={{ width: 150 }}>Progress</th>
                    <th className="hide-sm">Dataset</th>
                    <th className="num hide-sm">Algorithms</th>
                    <th className="num hide-sm">Duration</th>
                    <th className="num">Created</th>
                    <th className="actions-head" />
                  </tr>
                </thead>
                <tbody>
                  {jobs.data.items.map((job) => (
                    <tr key={job.id}>
                      <td>
                        <Link to={`/training/${job.id}`} className="cell-link">
                          {job.name}
                        </Link>
                        <div className="cell-sub">
                          {titleCase(job.problem_type)}
                          {job.target_column ? ` · ${job.target_column}` : ' · unsupervised'}
                          {job.retrain_source_deployment_id ? ' · retrain' : ''}
                        </div>
                      </td>
                      <td>
                        <StatusPill
                          status={job.status}
                          label={statusLabel(job.status)}
                          tone={statusTone(job.status)}
                        />
                      </td>
                      <td>
                        <div className="progress-cell">
                          <ProgressBar
                            value={job.progress}
                            tone={
                              job.status === 'failed'
                                ? 'negative'
                                : job.status === 'completed'
                                  ? 'positive'
                                  : 'accent'
                            }
                          />
                          <span className="num cell-sub">{job.progress}%</span>
                        </div>
                      </td>
                      <td className="hide-sm">
                        {job.dataset_name}
                        <div className="cell-sub">v{job.dataset_version}</div>
                      </td>
                      <td className="num hide-sm">{job.algorithm_count}</td>
                      <td className="num hide-sm muted">{formatDuration(job.duration_seconds)}</td>
                      <td className="num muted">{relativeTime(job.created_at)}</td>
                      <td className="actions-cell">
                        <Link
                          to={`/training/${job.id}`}
                          className="icon-button"
                          aria-label={`Open ${job.name}`}
                        >
                          <Icon name="chevron-right" size={15} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={jobs.data.page}
              pages={jobs.data.pages}
              total={jobs.data.total}
              pageSize={jobs.data.page_size}
              onChange={setPage}
            />
          </>
        ) : jobs.data ? (
          <div style={{ padding: 16 }}>
            {search || status ? (
              <EmptyState
                compact
                icon="search"
                title="No training jobs match these filters"
                description="Clear the search or choose a different status."
                action={
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      setSearch('')
                      setStatus('')
                    }}
                  >
                    Clear filters
                  </button>
                }
              />
            ) : (
              <EmptyState
                icon="flask"
                title="No training runs yet"
                description="Configure a dataset version and one or more algorithms. Atlas handles splitting, preprocessing and evaluation."
                action={
                  <LinkButton to="/training/new" variant="secondary" icon="plus">
                    New training run
                  </LinkButton>
                }
              />
            )}
          </div>
        ) : null}

        {jobs.data?.items.some((job) => job.status === 'queued' || job.status === 'running') ? (
          <div className="table-footnote">
            <span className="live-dot" /> Refreshing while jobs are active
          </div>
        ) : jobs.data ? (
          <div className="table-footnote">
            {formatNumber(jobs.data.total)} run{jobs.data.total === 1 ? '' : 's'} in this project
          </div>
        ) : null}
      </div>
    </>
  )
}

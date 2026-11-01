import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { ModelSummary, Page } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Icon } from '../components/Icon'
import {
  EmptyState,
  ErrorBlock,
  LinkButton,
  PageHeader,
  Pagination,
  SearchInput,
  StatusPill,
  TableSkeleton,
} from '../components/ui'
import {
  formatMetric,
  inferPrimaryMetric,
  metricLabel,
  relativeTime,
  statusLabel,
  statusTone,
} from '../lib/format'

export function ModelsPage() {
  useDocumentTitle('Models')
  const { project } = useWorkspace()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [page, setPage] = useState(1)

  const models = useApi<Page<ModelSummary>>(project ? '/models' : null, {
    project_id: project?.id,
    search: debouncedSearch || undefined,
    page,
    page_size: 20,
  })

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search.trim())
      setPage(1)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    setPage(1)
  }, [project?.id])

  return (
    <>
      <PageHeader
        title="Models"
        description="The registry stores fitted pipelines with an explicit stage. A model can keep several production versions while a rollout is in progress."
        actions={
          <LinkButton to="/experiments" variant="primary" icon="activity">
            Register from experiment
          </LinkButton>
        }
      />

      <div className="table-card">
        <div className="table-toolbar">
          <div className="table-toolbar-left">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Search models"
              ariaLabel="Search models"
            />
          </div>
          <div className="table-toolbar-right">
            <span className="table-count">
              {models.data
                ? `${models.data.total} model${models.data.total === 1 ? '' : 's'}`
                : ''}
            </span>
          </div>
        </div>

        {models.error ? (
          <div style={{ padding: 16 }}>
            <ErrorBlock message={models.error} onRetry={models.reload} />
          </div>
        ) : null}

        {!models.data && models.loading ? (
          <TableSkeleton columns={6} rows={6} />
        ) : models.data?.items.length ? (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th className="num">Latest version</th>
                    <th>Latest stage</th>
                    <th className="hide-sm">Algorithm</th>
                    <th className="num">Latest metric</th>
                    <th className="num hide-sm">Versions</th>
                    <th className="num hide-sm">Updated</th>
                    <th className="actions-head" />
                  </tr>
                </thead>
                <tbody>
                  {models.data.items.map((model) => {
                    const metric = inferPrimaryMetric(model.latest_metrics ?? {})
                    const metricValue = model.latest_metrics?.[metric]
                    return (
                      <tr key={model.id}>
                        <td>
                          <Link to={`/models/${model.id}`} className="cell-link">
                            {model.name}
                          </Link>
                          {model.description ? (
                            <div className="cell-sub truncate" style={{ maxWidth: 320 }}>
                              {model.description}
                            </div>
                          ) : null}
                        </td>
                        <td className="num">
                          v{model.latest_version}
                          {model.production_version ? (
                            <div className="cell-sub">prod v{model.production_version}</div>
                          ) : null}
                        </td>
                        <td>
                          <StatusPill
                            status={model.latest_stage ?? 'none'}
                            label={statusLabel(model.latest_stage)}
                            tone={statusTone(model.latest_stage)}
                          />
                        </td>
                        <td className="hide-sm">
                          {model.latest_algorithm?.replaceAll('_', ' ') ?? '—'}
                        </td>
                        <td className="num">
                          {metricValue !== null && metricValue !== undefined ? (
                            <>
                              <strong>{formatMetric(metric, metricValue)}</strong>
                              <div className="cell-sub">{metricLabel(metric)}</div>
                            </>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                        <td className="num hide-sm">{model.version_count}</td>
                        <td className="num hide-sm muted">{relativeTime(model.updated_at)}</td>
                        <td className="actions-cell">
                          <Link
                            to={`/models/${model.id}`}
                            className="icon-button"
                            aria-label={`Open ${model.name}`}
                          >
                            <Icon name="chevron-right" size={15} />
                          </Link>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <Pagination
              page={models.data.page}
              pages={models.data.pages}
              total={models.data.total}
              pageSize={models.data.page_size}
              onChange={setPage}
            />
          </>
        ) : models.data ? (
          <div style={{ padding: 16 }}>
            {search ? (
              <EmptyState
                compact
                icon="search"
                title="No models match this search"
                description="Try a different name or clear the search."
                action={
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSearch('')}>
                    Clear search
                  </button>
                }
              />
            ) : (
              <EmptyState
                icon="cube"
                title="No registered models"
                description="A completed experiment can be packaged as a model version. Registered versions can be promoted, downloaded and deployed."
                action={
                  <LinkButton to="/experiments" variant="secondary" icon="activity">
                    Find an experiment
                  </LinkButton>
                }
              />
            )}
          </div>
        ) : null}

        {models.data?.items.length ? (
          <div className="table-footnote">
            <Icon name="info" size={12} /> Multiple versions may be in production at once
          </div>
        ) : null}
      </div>
    </>
  )
}

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { DeploymentSummary, Page } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Icon } from '../components/Icon'
import {
  EmptyState,
  ErrorBlock,
  LinkButton,
  PageHeader,
  Pagination,
  StatusPill,
  TableSkeleton,
} from '../components/ui'
import {
  formatNumber,
  monitoringTone,
  relativeTime,
  statusLabel,
  statusTone,
} from '../lib/format'

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'stopped', label: 'Stopped' },
  { value: 'failed', label: 'Failed' },
]

export function DeploymentsPage() {
  useDocumentTitle('Deployments')
  const { project } = useWorkspace()
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)

  const deployments = useApi<Page<DeploymentSummary>>(
    project ? '/deployments' : null,
    {
      project_id: project?.id,
      status: status || undefined,
      page,
      page_size: 20,
    },
    { pollMs: 30000 },
  )

  useEffect(() => {
    setPage(1)
  }, [project?.id, status])

  return (
    <>
      <PageHeader
        title="Deployments"
        description="API-key endpoints that serve a pinned model version. Monitoring uses the version’s training reference to detect drift."
        actions={
          <LinkButton to="/deployments/new" variant="primary" icon="rocket">
            New deployment
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
            <span className="table-count">
              {deployments.data
                ? `${formatNumber(deployments.data.total)} deployment${
                    deployments.data.total === 1 ? '' : 's'
                  }`
                : ''}
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
        ) : deployments.data?.items.length ? (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Deployment</th>
                    <th>Status</th>
                    <th>Monitoring</th>
                    <th className="hide-sm">Model version</th>
                    <th className="hide-sm">API key</th>
                    <th className="num">Last request</th>
                    <th className="num hide-sm">Created</th>
                    <th className="actions-head" />
                  </tr>
                </thead>
                <tbody>
                  {deployments.data.items.map((deployment) => (
                    <tr key={deployment.id}>
                      <td>
                        <Link to={`/deployments/${deployment.id}`} className="cell-link">
                          {deployment.name}
                        </Link>
                        {deployment.description ? (
                          <div className="cell-sub truncate" style={{ maxWidth: 300 }}>
                            {deployment.description}
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <StatusPill
                          status={deployment.status}
                          label={statusLabel(deployment.status)}
                          tone={statusTone(deployment.status)}
                        />
                      </td>
                      <td>
                        {deployment.latest_monitoring_status ? (
                          <StatusPill
                            status={deployment.latest_monitoring_status}
                            label={statusLabel(deployment.latest_monitoring_status)}
                            tone={monitoringTone(deployment.latest_monitoring_status)}
                          />
                        ) : (
                          <span className="cell-null">Not run</span>
                        )}
                      </td>
                      <td className="hide-sm">
                        {deployment.model_name}
                        <div className="cell-sub">
                          v{deployment.model_version} · {deployment.algorithm.replaceAll('_', ' ')}
                        </div>
                      </td>
                      <td className="hide-sm mono muted">{deployment.api_key_prefix}…</td>
                      <td className="num muted">{relativeTime(deployment.last_request_at)}</td>
                      <td className="num hide-sm muted">{relativeTime(deployment.created_at)}</td>
                      <td className="actions-cell">
                        <Link
                          to={`/deployments/${deployment.id}`}
                          className="icon-button"
                          aria-label={`Open ${deployment.name}`}
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
              page={deployments.data.page}
              pages={deployments.data.pages}
              total={deployments.data.total}
              pageSize={deployments.data.page_size}
              onChange={setPage}
            />
          </>
        ) : deployments.data ? (
          <div style={{ padding: 16 }}>
            {status ? (
              <EmptyState
                compact
                icon="rocket"
                title="No deployments with this status"
                description="Choose a different status or create a new deployment."
                action={
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setStatus('')}
                  >
                    Show all
                  </button>
                }
              />
            ) : (
              <EmptyState
                icon="rocket"
                title="No deployments yet"
                description="Create an endpoint from a registered model version. Each deployment gets an API key, a prediction endpoint and drift monitoring."
                action={
                  <LinkButton to="/deployments/new" variant="secondary" icon="rocket">
                    Create deployment
                  </LinkButton>
                }
              />
            )}
          </div>
        ) : null}

        {deployments.data?.items.length ? (
          <div className="table-footnote">
            <Icon name="shield" size={12} /> Prediction requests require an API key or a signed-in
            workspace member
          </div>
        ) : null}
      </div>
    </>
  )
}

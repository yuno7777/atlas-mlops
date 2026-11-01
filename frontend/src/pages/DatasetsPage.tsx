import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { DatasetSummary, Page } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { DatasetUploadDialog } from '../components/DatasetUploadDialog'
import { Icon } from '../components/Icon'
import {
  EmptyState,
  ErrorBlock,
  PageHeader,
  Pagination,
  SearchInput,
  TableSkeleton,
} from '../components/ui'
import { formatBytes, formatNumber, relativeTime } from '../lib/format'

export function DatasetsPage() {
  useDocumentTitle('Datasets')
  const { project } = useWorkspace()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [uploadOpen, setUploadOpen] = useState(searchParams.get('upload') === '1')

  const datasets = useApi<Page<DatasetSummary>>(
    project ? '/datasets' : null,
    {
      project_id: project?.id,
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
  }, [project?.id])

  useEffect(() => {
    if (searchParams.get('upload') !== '1') return
    setUploadOpen(true)
    const next = new URLSearchParams(searchParams)
    next.delete('upload')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  return (
    <>
      <PageHeader
        title="Datasets"
        description="Versioned tabular data for this project. Atlas profiles every upload and keeps prior versions available for training."
        actions={
          <button type="button" className="btn btn-primary btn-md" onClick={() => setUploadOpen(true)}>
            <Icon name="upload" /> Upload dataset
          </button>
        }
      />

      <div className="table-card">
        <div className="table-toolbar">
          <div className="table-toolbar-left">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Search datasets"
              ariaLabel="Search datasets"
            />
          </div>
          <div className="table-toolbar-right">
            <span className="table-count">
              {datasets.data
                ? `${formatNumber(datasets.data.total)} dataset${datasets.data.total === 1 ? '' : 's'}`
                : ''}
            </span>
          </div>
        </div>

        {datasets.error ? (
          <div style={{ padding: 16 }}>
            <ErrorBlock message={datasets.error} onRetry={datasets.reload} />
          </div>
        ) : null}

        {!datasets.data && datasets.loading ? (
          <TableSkeleton columns={5} rows={6} />
        ) : datasets.data?.items.length ? (
          <>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Dataset</th>
                    <th className="num">Version</th>
                    <th className="num">Rows</th>
                    <th className="num hide-sm">Columns</th>
                    <th className="num hide-sm">Size</th>
                    <th className="num">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {datasets.data.items.map((dataset) => (
                    <tr key={dataset.id} className="clickable-row">
                      <td>
                        <Link to={`/datasets/${dataset.id}`} className="cell-link">
                          {dataset.name}
                        </Link>
                        {dataset.description ? (
                          <div className="cell-sub truncate" style={{ maxWidth: 380 }}>
                            {dataset.description}
                          </div>
                        ) : null}
                      </td>
                      <td className="num">
                        v{dataset.latest_version}
                        <div className="cell-sub">{dataset.version_count} total</div>
                      </td>
                      <td className="num">{formatNumber(dataset.row_count ?? 0)}</td>
                      <td className="num hide-sm">{formatNumber(dataset.column_count ?? 0)}</td>
                      <td className="num hide-sm">{formatBytes(dataset.size_bytes)}</td>
                      <td className="num muted">{relativeTime(dataset.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={datasets.data.page}
              pages={datasets.data.pages}
              total={datasets.data.total}
              pageSize={datasets.data.page_size}
              onChange={setPage}
            />
          </>
        ) : datasets.data ? (
          <div style={{ padding: 16 }}>
            {search ? (
              <EmptyState
                compact
                icon="search"
                title="No datasets match this search"
                description="Try a different name or clear the search."
                action={
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSearch('')}>
                    Clear search
                  </button>
                }
              />
            ) : (
              <EmptyState
                icon="database"
                title="Upload the first dataset"
                description="Start with a CSV, JSON or Parquet file. Atlas checks the schema, profiles distributions and suggests a target column."
                action={
                  <button
                    type="button"
                    className="btn btn-secondary btn-md"
                    onClick={() => setUploadOpen(true)}
                  >
                    <Icon name="upload" /> Upload dataset
                  </button>
                }
              />
            )}
          </div>
        ) : null}
      </div>

      <DatasetUploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={(version) => navigate(`/datasets/${version.dataset_id}`)}
      />
    </>
  )
}

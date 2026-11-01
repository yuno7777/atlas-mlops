import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, downloadFile, errorMessage } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type {
  CategoricalProfile,
  DataProfile,
  DatasetDetail,
  DatasetVersion,
  DatasetVersionSummary,
  PreviewResponse,
  ValidationCheck,
} from '../api/types'
import { DatasetUploadDialog } from '../components/DatasetUploadDialog'
import { Icon } from '../components/Icon'
import {
  Button,
  ConfirmDialog,
  DefinitionGrid,
  EmptyState,
  ErrorBlock,
  InlineNotice,
  LoadingBlock,
  Modal,
  PageHeader,
  Panel,
  Pill,
  SectionHeader,
  Select,
  StatusPill,
  Tabs,
} from '../components/ui'
import {
  formatBytes,
  formatDate,
  formatDateTime,
  formatNumber,
  formatShare,
  relativeTime,
  statusLabel,
  statusTone,
  titleCase,
} from '../lib/format'

type DatasetTab = 'preview' | 'schema' | 'quality' | 'versions'

function PreviewValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="cell-null">—</span>
  if (typeof value === 'boolean') return <span className="mono">{value ? 'true' : 'false'}</span>
  if (typeof value === 'object') {
    return (
      <span className="mono" title={JSON.stringify(value)}>
        {JSON.stringify(value)}
      </span>
    )
  }
  return <>{String(value)}</>
}

function ValidationBanner({ checks }: { checks: ValidationCheck[] }) {
  const failed = checks.filter((check) => check.status === 'failed')
  const warnings = checks.filter((check) => check.status === 'warning')
  if (!failed.length && !warnings.length) return null
  const issues = [...failed, ...warnings]
  return (
    <InlineNotice
      tone={failed.length ? 'negative' : 'warning'}
      title={`${failed.length ? 'Validation failed' : 'Upload passed with warnings'} · ${issues.length} issue${issues.length === 1 ? '' : 's'}`}
    >
      <ul className="notice-list">
        {issues.slice(0, 4).map((check) => (
          <li key={check.name}>
            <strong>{check.name}</strong> — {check.message}
          </li>
        ))}
      </ul>
      {issues.length > 4 ? <div>And {issues.length - 4} more in the Quality tab.</div> : null}
    </InlineNotice>
  )
}

function profileSummary(profile: DataProfile) {
  return [
    { label: 'Missing cells', value: formatShare(profile.missing.percent, 2) },
    { label: 'Duplicate rows', value: formatShare(profile.duplicates.percent, 2) },
    { label: 'Memory', value: formatBytes(profile.memory_bytes) },
    {
      label: 'Profiled',
      value: profile.sampled ? `${formatNumber(profile.sample_size)} sampled rows` : 'Full dataset',
    },
  ]
}

function PreviewPanel({ versionId }: { versionId: string | null }) {
  const [limit, setLimit] = useState(50)
  const preview = useApi<PreviewResponse>(
    versionId ? `/dataset-versions/${versionId}/preview` : null,
    { limit },
  )

  return (
    <Panel className="flush-panel">
      <div className="table-toolbar">
        <div className="table-toolbar-left">
          <span className="table-count">
            {preview.data
              ? `Showing ${formatNumber(preview.data.returned)} of ${formatNumber(preview.data.total_rows)} rows`
              : 'Preview'}
          </span>
        </div>
        <div className="table-toolbar-right">
          <label className="inline-label" htmlFor="preview-limit">
            Rows
            <Select
              id="preview-limit"
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
              style={{ width: 82 }}
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </Select>
          </label>
        </div>
      </div>
      {preview.error ? (
        <div style={{ padding: 16 }}>
          <ErrorBlock message={preview.error} onRetry={preview.reload} />
        </div>
      ) : null}
      {preview.data?.columns.length && preview.data.rows.length ? (
        <div className="table-wrap preview-wrap">
          <table className="data preview-table">
            <thead>
              <tr>
                <th className="row-number-head">#</th>
                {preview.data.columns.map((column) => (
                  <th key={column.name}>
                    <span className="preview-column-name">{column.name}</span>
                    <span className="preview-column-type">{column.dtype}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.data.rows.map((row, index) => (
                <tr key={index}>
                  <td className="row-number num">{index + 1}</td>
                  {preview.data?.columns.map((column) => (
                    <td key={column.name}>
                      <PreviewValue value={row[column.name]} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : preview.loading ? (
        <LoadingBlock rows={8} />
      ) : (
        <EmptyState compact icon="database" title="No rows to preview" description="The file contains headers but no data rows." />
      )}
    </Panel>
  )
}

function SchemaPanel({ version }: { version: DatasetVersion }) {
  return (
    <Panel className="flush-panel">
      <div className="table-toolbar">
        <div className="table-toolbar-left">
          <span className="table-count">
            {version.schema.length} columns · {formatNumber(version.row_count)} rows
          </span>
        </div>
      </div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Column</th>
              <th>Kind</th>
              <th>Type</th>
              <th className="num hide-sm">Unique</th>
              <th>Nullable</th>
              <th className="hide-sm">Sample values</th>
            </tr>
          </thead>
          <tbody>
            {version.schema.map((column) => (
              <tr key={column.name}>
                <td className="mono" style={{ fontWeight: 500 }}>
                  {column.name}
                </td>
                <td>
                  <Pill tone={column.kind === 'numeric' ? 'info' : 'neutral'}>{column.kind}</Pill>
                </td>
                <td className="muted mono">{column.dtype}</td>
                <td className="num hide-sm">{column.unique_count ?? '—'}</td>
                <td className="muted">{column.nullable ? 'Yes' : 'No'}</td>
                <td className="hide-sm">
                  <div className="sample-values">
                    {column.sample_values.slice(0, 3).map((value, index) => (
                      <code key={index} className="inline-code">
                        {value === null ? 'null' : String(value)}
                      </code>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

function CheckIcon({ status }: { status: ValidationCheck['status'] }) {
  if (status === 'passed') return <Icon name="check-circle" size={15} className="icon-positive" />
  if (status === 'warning') return <Icon name="alert" size={15} className="icon-warning" />
  return <Icon name="x-circle" size={15} className="icon-negative" />
}

function CategoricalCard({ profile }: { profile: CategoricalProfile }) {
  return (
    <div className="category-profile">
      <div className="space-between" style={{ marginBottom: 6 }}>
        <span className="mono" style={{ fontSize: 12, fontWeight: 500 }}>
          {profile.column}
        </span>
        <span className="cell-sub">{profile.unique} unique</span>
      </div>
      {profile.top.map((share) => (
        <div key={share.value} className="category-share">
          <span className="share-label">{share.value}</span>
          <span className="share-track">
            <span className="share-fill" style={{ width: `${Math.min(100, share.percent)}%` }} />
          </span>
          <span className="share-value num">{formatShare(share.percent, 1)}</span>
        </div>
      ))}
      {profile.sampled ? (
        <div className="cell-sub" style={{ marginTop: 6 }}>
          Based on {formatNumber(profile.sample_size)} sampled rows
        </div>
      ) : null}
    </div>
  )
}

function QualityPanel({ version }: { version: DatasetVersion }) {
  const profile = version.profile
  const checks = version.validation.checks
  return (
    <div className="stack-gap-20">
      <Panel>
        <SectionHeader
          title="Validation checks"
          description={version.validation.passed ? 'All required checks passed.' : 'Review the failed checks before training.'}
          action={
            <StatusPill
              status={version.validation.passed ? 'passed' : 'warning'}
              label={version.validation.passed ? 'Passed' : 'Needs review'}
              tone={version.validation.passed ? 'positive' : 'warning'}
            />
          }
        />
        <div className="check-list">
          {checks.map((check) => (
            <div className="check-row" key={check.name}>
              <CheckIcon status={check.status} />
              <div>
                <div style={{ fontWeight: 500 }}>{titleCase(check.name)}</div>
                <div className="cell-sub">{check.message}</div>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="settings-grid">
        <Panel>
          <SectionHeader title="Profile summary" />
          <DefinitionGrid items={profileSummary(profile)} columns={2} />
          {profile.constant_columns.length ? (
            <p className="panel-note">
              Constant columns: <span className="mono">{profile.constant_columns.join(', ')}</span>
            </p>
          ) : null}
          {profile.high_missing_columns.length ? (
            <p className="panel-note">
              High missing: <span className="mono">{profile.high_missing_columns.join(', ')}</span>
            </p>
          ) : null}
        </Panel>
        <Panel>
          <SectionHeader title="Suggested targets" description="Ranked by cardinality and dtype." />
          {version.validation.target_suggestions.length ? (
            <div className="stack-sm">
              {version.validation.target_suggestions.map((suggestion) => (
                <div key={suggestion.column} className="target-suggestion">
                  <div className="space-between">
                    <span className="mono" style={{ fontWeight: 500 }}>
                      {suggestion.column}
                    </span>
                    <Pill tone={suggestion.task === 'classification' ? 'info' : 'neutral'}>
                      {titleCase(suggestion.task)}
                    </Pill>
                  </div>
                  <div className="cell-sub">{suggestion.reason}</div>
                </div>
              ))}
            </div>
          ) : (
            <p className="chart-empty">No target suggestions for this file.</p>
          )}
        </Panel>
      </div>

      {profile.missing.columns.length ? (
        <Panel className="flush-panel">
          <SectionHeader title="Missing values" description={`${formatShare(profile.missing.percent, 2)} of all cells are empty.`} />
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Column</th>
                  <th className="num">Missing</th>
                  <th className="num">Share</th>
                  <th>Bar</th>
                </tr>
              </thead>
              <tbody>
                {profile.missing.columns.map((column) => (
                  <tr key={column.column}>
                    <td className="mono">{column.column}</td>
                    <td className="num">{formatNumber(column.count)}</td>
                    <td className="num">{formatShare(column.percent, 2)}</td>
                    <td>
                      <span className="share-track">
                        <span
                          className="share-fill is-warning"
                          style={{ width: `${Math.min(100, column.percent)}%` }}
                        />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      {profile.numeric.length ? (
        <Panel className="flush-panel">
          <SectionHeader title="Numeric columns" description="Distribution summary used by training and drift monitoring." />
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Column</th>
                  <th className="num">Mean</th>
                  <th className="num">Std</th>
                  <th className="num">Min</th>
                  <th className="num">P25</th>
                  <th className="num">Median</th>
                  <th className="num">P75</th>
                  <th className="num">Max</th>
                  <th className="num hide-sm">Outliers</th>
                  <th className="num hide-sm">Skew</th>
                </tr>
              </thead>
              <tbody>
                {profile.numeric.map((column) => (
                  <tr key={column.column}>
                    <td className="mono">{column.column}</td>
                    <td className="num">{column.mean?.toFixed(2) ?? '—'}</td>
                    <td className="num">{column.std?.toFixed(2) ?? '—'}</td>
                    <td className="num">{column.min?.toFixed(2) ?? '—'}</td>
                    <td className="num">{column.p25?.toFixed(2) ?? '—'}</td>
                    <td className="num">{column.p50?.toFixed(2) ?? '—'}</td>
                    <td className="num">{column.p75?.toFixed(2) ?? '—'}</td>
                    <td className="num">{column.max?.toFixed(2) ?? '—'}</td>
                    <td className="num hide-sm">{formatNumber(column.outliers_iqr)}</td>
                    <td className="num hide-sm">{column.skew?.toFixed(2) ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      {profile.categorical.length ? (
        <Panel>
          <SectionHeader title="Categorical columns" description="Top values and their share of the column." />
          <div className="category-grid">
            {profile.categorical.map((column) => (
              <CategoricalCard key={column.column} profile={column} />
            ))}
          </div>
        </Panel>
      ) : null}

      {profile.datetime.length ? (
        <Panel>
          <SectionHeader title="Datetime columns" />
          <DefinitionGrid
            items={profile.datetime.map((column) => ({
              label: column.column,
              value: `${formatDate(column.min)} → ${formatDate(column.max)}`,
            }))}
          />
        </Panel>
      ) : null}
    </div>
  )
}

function VersionsPanel({
  versions,
  selectedId,
  onSelect,
  onDownload,
}: {
  versions: DatasetVersionSummary[]
  selectedId: string | null
  onSelect: (version: DatasetVersionSummary) => void
  onDownload: (version: DatasetVersionSummary) => void
}) {
  return (
    <Panel className="flush-panel">
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Version</th>
              <th>Status</th>
              <th>File</th>
              <th className="num">Rows</th>
              <th className="num hide-sm">Columns</th>
              <th className="num hide-sm">Size</th>
              <th className="num">Uploaded</th>
              <th className="actions-head" />
            </tr>
          </thead>
          <tbody>
            {versions.map((version) => (
              <tr key={version.id} className={version.id === selectedId ? 'is-selected' : ''}>
                <td>
                  <button type="button" className="text-button" onClick={() => onSelect(version)}>
                    v{version.version}
                  </button>
                  {version.id === selectedId ? <span className="current-mark">Current</span> : null}
                </td>
                <td>
                  <StatusPill
                    status={version.status}
                    label={statusLabel(version.status)}
                    tone={statusTone(version.status)}
                  />
                </td>
                <td className="mono muted">{version.original_filename}</td>
                <td className="num">{formatNumber(version.row_count)}</td>
                <td className="num hide-sm">{formatNumber(version.column_count)}</td>
                <td className="num hide-sm">{formatBytes(version.size_bytes)}</td>
                <td className="num muted">{formatDateTime(version.created_at)}</td>
                <td className="actions-cell">
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Download version ${version.version}`}
                    onClick={() => onDownload(version)}
                  >
                    <Icon name="download" size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

export function DatasetDetailPage() {
  const { datasetId } = useParams<{ datasetId: string }>()
  const navigate = useNavigate()
  const [tab, setTab] = useState<DatasetTab>('preview')
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deletePending, setDeletePending] = useState(false)
  const [noticeOpen, setNoticeOpen] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const detail = useApi<DatasetDetail>(datasetId ? `/datasets/${datasetId}` : null)
  const versions = useApi<DatasetVersionSummary[]>(
    datasetId ? `/datasets/${datasetId}/versions` : null,
    undefined,
    { pollMs: 20000 },
  )
  const version = useApi<DatasetVersion>(
    selectedVersionId ? `/dataset-versions/${selectedVersionId}` : null,
  )

  useDocumentTitle(detail.data?.dataset.name ?? 'Dataset')

  useEffect(() => {
    if (!detail.data) return
    if (selectedVersionId) return
    const latest = detail.data.latest_version ?? null
    if (latest) setSelectedVersionId(latest.id)
    else if (versions.data?.length) setSelectedVersionId(versions.data[0].id)
  }, [detail.data, versions.data, selectedVersionId])

  useEffect(() => {
    if (!versions.data?.length) return
    if (selectedVersionId && versions.data.some((item) => item.id === selectedVersionId)) return
    setSelectedVersionId(versions.data[0].id)
  }, [versions.data, selectedVersionId])

  const activeVersion = version.data
  const dataset = detail.data?.dataset

  const download = async (target?: DatasetVersion | DatasetVersionSummary | null) => {
    const versionId = target?.id ?? selectedVersionId
    if (!versionId) return
    const versionNumber = target?.version ?? activeVersion?.version ?? 1
    try {
      await downloadFile(
        `/dataset-versions/${versionId}/download`,
        `${dataset?.name ?? 'dataset'}-v${versionNumber}.csv`,
      )
    } catch (caught) {
      setNotice(errorMessage(caught))
      setNoticeOpen(true)
    }
  }

  const remove = async () => {
    if (!datasetId) return
    setDeletePending(true)
    try {
      await api.delete(`/datasets/${datasetId}`)
      navigate('/datasets', { replace: true })
    } catch (caught) {
      setNotice(errorMessage(caught))
      setNoticeOpen(true)
      setDeleteOpen(false)
    } finally {
      setDeletePending(false)
    }
  }

  if (detail.error && !detail.data) {
    return (
      <>
        <PageHeader backTo="/datasets" backLabel="Datasets" title="Dataset unavailable" />
        <ErrorBlock message={detail.error} onRetry={detail.reload} />
      </>
    )
  }

  if (!detail.data || !dataset) {
    return (
      <>
        <PageHeader backTo="/datasets" backLabel="Datasets" title="Dataset" />
        <LoadingBlock rows={8} />
      </>
    )
  }

  return (
    <>
      <PageHeader
        backTo="/datasets"
        backLabel="Datasets"
        eyebrow="Dataset"
        title={dataset.name}
        description={dataset.description ?? 'No description provided.'}
        actions={
          <>
            <Button
              variant="ghost"
              icon="trash"
              onClick={() => setDeleteOpen(true)}
              aria-label="Delete dataset"
            >
              Delete
            </Button>
            <Button variant="secondary" icon="download" onClick={() => void download()} disabled={!activeVersion}>
              Download
            </Button>
            <Button variant="primary" icon="upload" onClick={() => setUploadOpen(true)}>
              Add version
            </Button>
          </>
        }
      />

      <div className="dataset-facts">
        <div className="dataset-fact">
          <span>Latest version</span>
          <strong className="num">v{dataset.latest_version}</strong>
        </div>
        <div className="dataset-fact">
          <span>Versions</span>
          <strong className="num">{dataset.version_count}</strong>
        </div>
        <div className="dataset-fact">
          <span>Rows</span>
          <strong className="num">{formatNumber(dataset.row_count ?? 0)}</strong>
        </div>
        <div className="dataset-fact">
          <span>Columns</span>
          <strong className="num">{formatNumber(dataset.column_count ?? 0)}</strong>
        </div>
        <div className="dataset-fact">
          <span>File size</span>
          <strong className="num">{formatBytes(dataset.size_bytes)}</strong>
        </div>
        <div className="dataset-fact">
          <span>Updated</span>
          <strong>{relativeTime(dataset.updated_at)}</strong>
        </div>
      </div>

      {activeVersion ? <ValidationBanner checks={activeVersion.validation.checks} /> : null}

      <div className="dataset-detail-bar">
        <Tabs
          items={[
            { id: 'preview', label: 'Preview' },
            { id: 'schema', label: 'Schema', count: activeVersion?.schema.length },
            { id: 'quality', label: 'Quality' },
            { id: 'versions', label: 'Versions', count: versions.data?.length },
          ]}
          value={tab}
          onChange={(value) => setTab(value as DatasetTab)}
          ariaLabel="Dataset sections"
        />
        <label className="inline-label" htmlFor="dataset-version">
          Version
          <Select
            id="dataset-version"
            value={selectedVersionId ?? ''}
            onChange={(event) => setSelectedVersionId(event.target.value)}
            style={{ width: 136 }}
          >
            {(versions.data ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                v{item.version} · {formatDate(item.created_at)}
              </option>
            ))}
          </Select>
        </label>
      </div>

      {version.error ? <ErrorBlock message={version.error} onRetry={version.reload} /> : null}
      {!activeVersion && version.loading ? <LoadingBlock rows={8} /> : null}

      {tab === 'preview' ? <PreviewPanel versionId={selectedVersionId} /> : null}
      {tab === 'schema' && activeVersion ? <SchemaPanel version={activeVersion} /> : null}
      {tab === 'quality' && activeVersion ? <QualityPanel version={activeVersion} /> : null}
      {tab === 'versions' ? (
        <VersionsPanel
          versions={versions.data ?? []}
          selectedId={selectedVersionId}
          onSelect={(next) => {
            setSelectedVersionId(next.id)
            setTab('preview')
          }}
          onDownload={(target) => void download(target)}
        />
      ) : null}

      <DatasetUploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        datasetId={datasetId}
        onUploaded={(next) => {
          setSelectedVersionId(next.id)
          setTab('preview')
          detail.reload()
          versions.reload()
        }}
      />

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        title={`Delete “${dataset.name}”?`}
        description="This removes the dataset and all versions. Datasets used by training jobs cannot be deleted."
        confirmLabel="Delete dataset"
        pending={deletePending}
        onConfirm={() => void remove()}
      />

      <Modal
        open={noticeOpen}
        onClose={() => setNoticeOpen(false)}
        title="Action failed"
        footer={
          <Button variant="secondary" onClick={() => setNoticeOpen(false)}>
            Close
          </Button>
        }
      >
        <div className="error-block">{notice}</div>
      </Modal>
    </>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, downloadFile, errorMessage } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type {
  ExperimentSummary,
  ModelDetail,
  ModelVersion,
  Page,
  VersionCompare,
} from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Icon } from '../components/Icon'
import { useToast } from '../components/ToastProvider'
import {
  Button,
  Checkbox,
  ConfirmDialog,
  EmptyState,
  ErrorBlock,
  Field,
  LinkButton,
  LoadingBlock,
  Modal,
  PageHeader,
  Panel,
  Pill,
  Select,
  StatusPill,
  Textarea,
} from '../components/ui'
import {
  formatDate,
  formatMetric,
  inferPrimaryMetric,
  metricLabel,
  primaryMetric,
  relativeTime,
  statusLabel,
  statusTone,
  titleCase,
} from '../lib/format'

export function ModelDetailPage() {
  const { modelId } = useParams<{ modelId: string }>()
  const { project } = useWorkspace()
  const toast = useToast()
  const model = useApi<ModelDetail>(modelId ? `/models/${modelId}` : null)
  const experiments = useApi<Page<ExperimentSummary>>(
    modelId && project ? '/experiments' : null,
    {
      project_id: project?.id,
      status: 'completed',
      page_size: 100,
      sort: '-created_at',
    },
  )
  useDocumentTitle(model.data?.name ?? 'Model')

  const [selected, setSelected] = useState<string[]>([])
  const [addOpen, setAddOpen] = useState(false)
  const [experimentId, setExperimentId] = useState('')
  const [versionDescription, setVersionDescription] = useState('')
  const [addPending, setAddPending] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)
  const [stageTarget, setStageTarget] = useState<ModelVersion | null>(null)
  const [stageChoice, setStageChoice] = useState('staging')
  const [stagePending, setStagePending] = useState(false)
  const [archiveTarget, setArchiveTarget] = useState<ModelVersion | null>(null)
  const [archivePending, setArchivePending] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareData, setCompareData] = useState<VersionCompare | null>(null)
  const [compareLoading, setCompareLoading] = useState(false)
  const [compareError, setCompareError] = useState<string | null>(null)

  useEffect(() => {
    if (!addOpen) return
    setExperimentId('')
    setVersionDescription('')
    setAddError(null)
  }, [addOpen])

  useEffect(() => {
    setSelected([])
  }, [modelId])

  const latest = model.data?.versions[0]
  const primary = latest
    ? (latest.problem_type ? primaryMetric(latest.problem_type) : inferPrimaryMetric(latest.metrics))
    : 'accuracy'

  const productionVersion = useMemo(
    () => model.data?.versions.find((version) => version.stage === 'production'),
    [model.data],
  )

  const toggle = (id: string) => {
    setSelected((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id)
      if (current.length >= 6) return current
      return [...current, id]
    })
  }

  const addVersion = async () => {
    if (!modelId || !experimentId) {
      setAddError('Choose a completed experiment.')
      return
    }
    setAddPending(true)
    setAddError(null)
    try {
      const version = await api.post<ModelVersion>(`/models/${modelId}/versions`, {
        experiment_id: experimentId,
        description: versionDescription.trim() || undefined,
      })
      toast.success(`Version ${version.version} registered.`)
      setAddOpen(false)
      model.reload()
    } catch (caught) {
      setAddError(errorMessage(caught))
    } finally {
      setAddPending(false)
    }
  }

  const promote = async () => {
    if (!stageTarget) return
    setStagePending(true)
    try {
      await api.post(`/model-versions/${stageTarget.id}/promote`, { stage: stageChoice })
      toast.success(
        stageChoice === 'none'
          ? `Version ${stageTarget.version} has no stage now.`
          : `Version ${stageTarget.version} moved to ${stageChoice}.`,
      )
      setStageTarget(null)
      model.reload()
    } catch (caught) {
      toast.error(errorMessage(caught))
    } finally {
      setStagePending(false)
    }
  }

  const archive = async () => {
    if (!archiveTarget) return
    setArchivePending(true)
    try {
      await api.post(`/model-versions/${archiveTarget.id}/archive`)
      toast.success(`Version ${archiveTarget.version} archived.`)
      setArchiveTarget(null)
      model.reload()
    } catch (caught) {
      toast.error(errorMessage(caught))
    } finally {
      setArchivePending(false)
    }
  }

  const download = async (version: ModelVersion) => {
    if (!model.data) return
    try {
      await downloadFile(
        `/model-versions/${version.id}/download`,
        `${model.data.name}-v${version.version}.joblib`,
      )
    } catch (caught) {
      toast.error(errorMessage(caught))
    }
  }

  const downloadModelCard = async (version: ModelVersion) => {
    if (!model.data) return
    try {
      await downloadFile(
        `/model-versions/${version.id}/card.md`,
        `${model.data.name}-v${version.version}-model-card.md`,
      )
    } catch (caught) {
      toast.error(errorMessage(caught))
    }
  }

  const openCompare = async () => {
    if (!modelId || selected.length < 2) return
    setCompareOpen(true)
    setCompareLoading(true)
    setCompareError(null)
    setCompareData(null)
    try {
      const data = await api.post<VersionCompare>(`/models/${modelId}/versions/compare`, {
        version_ids: selected,
      })
      setCompareData(data)
    } catch (caught) {
      setCompareError(errorMessage(caught))
    } finally {
      setCompareLoading(false)
    }
  }

  if (model.error && !model.data) {
    return (
      <>
        <PageHeader backTo="/models" backLabel="Models" title="Model unavailable" />
        <ErrorBlock message={model.error} onRetry={model.reload} />
      </>
    )
  }

  if (!model.data) {
    return (
      <>
        <PageHeader backTo="/models" backLabel="Models" title="Model" />
        <LoadingBlock rows={8} />
      </>
    )
  }

  const current = model.data

  return (
    <>
      <PageHeader
        backTo="/models"
        backLabel="Models"
        eyebrow="Registry"
        title={current.name}
        description={current.description ?? 'No description provided.'}
        actions={
          <>
            <Button variant="secondary" icon="plus" onClick={() => setAddOpen(true)}>
              Add version
            </Button>
            <LinkButton to="/deployments/new" variant="primary" icon="rocket">
              Deploy model
            </LinkButton>
          </>
        }
      />

      <div className="dataset-facts">
        <div className="dataset-fact">
          <span>Latest version</span>
          <strong className="num">v{current.latest_version}</strong>
        </div>
        <div className="dataset-fact">
          <span>Versions</span>
          <strong className="num">{current.version_count}</strong>
        </div>
        <div className="dataset-fact">
          <span>Production</span>
          <strong className="num">
            {productionVersion ? `v${productionVersion.version}` : 'None'}
          </strong>
        </div>
        <div className="dataset-fact">
          <span>Latest stage</span>
          <StatusPill
            status={current.latest_stage ?? 'none'}
            label={statusLabel(current.latest_stage)}
            tone={statusTone(current.latest_stage)}
          />
        </div>
        <div className="dataset-fact">
          <span>{metricLabel(primary)}</span>
          <strong className="num">
            {latest ? formatMetric(primary, latest.metrics[primary]) : '—'}
          </strong>
        </div>
        <div className="dataset-fact">
          <span>Updated</span>
          <strong>{relativeTime(current.updated_at)}</strong>
        </div>
      </div>

      <Panel className="flush-panel">
        <div className="table-toolbar">
          <div className="table-toolbar-left">
            <strong style={{ fontSize: 14, fontWeight: 500 }}>Versions</strong>
            <span className="table-count">
              {selected.length ? `${selected.length} selected` : 'Select 2–6 to compare'}
            </span>
          </div>
          <div className="table-toolbar-right">
            <Button
              size="sm"
              variant="secondary"
              icon="chart"
              disabled={selected.length < 2}
              onClick={() => void openCompare()}
            >
              Compare
            </Button>
          </div>
        </div>
        {current.versions.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th className="check-cell" />
                  <th>Version</th>
                  <th>Stage</th>
                  <th>Algorithm</th>
                  <th className="num">Primary metric</th>
                  <th className="num hide-sm">Deployments</th>
                  <th className="num hide-sm">Created</th>
                  <th className="actions-head" />
                </tr>
              </thead>
              <tbody>
                {current.versions.map((version) => {
                  const metric = version.problem_type
                    ? primaryMetric(version.problem_type)
                    : inferPrimaryMetric(version.metrics)
                  return (
                    <tr key={version.id}>
                      <td className="check-cell">
                        <Checkbox
                          label={<span className="sr-only">Select version {version.version}</span>}
                          checked={selected.includes(version.id)}
                          onChange={() => toggle(version.id)}
                          disabled={selected.length >= 6 && !selected.includes(version.id)}
                        />
                      </td>
                      <td>
                        <span className="mono" style={{ fontWeight: 500 }}>
                          v{version.version}
                        </span>
                        {version.stage === 'production' ? (
                          <span className="current-mark">Live</span>
                        ) : null}
                        <div className="cell-sub">
                          <Link to={`/experiments/${version.experiment_id}`} className="inline-link">
                            Source experiment
                          </Link>
                        </div>
                      </td>
                      <td>
                        <StatusPill
                          status={version.stage}
                          label={statusLabel(version.stage)}
                          tone={statusTone(version.stage)}
                        />
                      </td>
                      <td>
                        {version.algorithm.replaceAll('_', ' ')}
                        <div className="cell-sub mono">{version.framework}</div>
                      </td>
                      <td className="num">
                        <strong>{formatMetric(metric, version.metrics[metric])}</strong>
                        <div className="cell-sub">{metricLabel(metric)}</div>
                      </td>
                      <td className="num hide-sm">{version.deployment_count}</td>
                      <td className="num hide-sm muted">{formatDate(version.created_at)}</td>
                      <td className="actions-cell">
                        <div className="row-actions">
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Download model card for version ${version.version}`}
                            title="Download model card"
                            onClick={() => void downloadModelCard(version)}
                          >
                            <Icon name="file" size={15} />
                          </button>
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Download version ${version.version}`}
                            onClick={() => void download(version)}
                          >
                            <Icon name="download" size={15} />
                          </button>
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Change stage for version ${version.version}`}
                            onClick={() => {
                              setStageChoice(version.stage === 'none' ? 'staging' : version.stage)
                              setStageTarget(version)
                            }}
                          >
                            <Icon name="arrow-up-right" size={15} />
                          </button>
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Archive version ${version.version}`}
                            disabled={version.stage === 'archived'}
                            onClick={() => setArchiveTarget(version)}
                          >
                            <Icon name="archive" size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon="cube"
            title="No versions in this model"
            description="Add a completed experiment as the first version."
            action={
              <Button variant="secondary" size="sm" onClick={() => setAddOpen(true)}>
                Add version
              </Button>
            }
          />
        )}
        <div className="table-footnote">
          Promoting a version does not start or update a deployment. Change the deployment’s model
          version explicitly.
        </div>
      </Panel>

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Add model version"
        description="Choose a completed experiment from this project. Its fitted pipeline and reference profile become a new model version."
        footer={
          <>
            <Button variant="secondary" onClick={() => setAddOpen(false)} disabled={addPending}>
              Cancel
            </Button>
            <Button variant="primary" loading={addPending} onClick={() => void addVersion()}>
              Add version
            </Button>
          </>
        }
      >
        <div className="form-stack">
          <Field label="Experiment" htmlFor="model-version-experiment">
            <Select
              id="model-version-experiment"
              value={experimentId}
              onChange={(event) => setExperimentId(event.target.value)}
            >
              <option value="">Choose a completed experiment</option>
              {(experiments.data?.items ?? []).map((experiment) => (
                <option key={experiment.id} value={experiment.id}>
                  {experiment.name} — {experiment.algorithm_label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Version description"
            htmlFor="model-version-description"
            hint="Optional. Record what changed in this version."
          >
            <Textarea
              id="model-version-description"
              value={versionDescription}
              onChange={(event) => setVersionDescription(event.target.value)}
              rows={3}
              maxLength={2000}
            />
          </Field>
          {experiments.error ? (
            <ErrorBlock compact message={experiments.error} onRetry={experiments.reload} />
          ) : null}
          {addError ? <div className="error-block is-compact">{addError}</div> : null}
        </div>
      </Modal>

      <Modal
        open={Boolean(stageTarget)}
        onClose={() => setStageTarget(null)}
        title={stageTarget ? `Change stage for v${stageTarget.version}` : 'Change stage'}
        description="Stages are labels for review. They do not move traffic; deployments bind to a specific model version."
        footer={
          <>
            <Button variant="secondary" onClick={() => setStageTarget(null)} disabled={stagePending}>
              Cancel
            </Button>
            <Button variant="primary" loading={stagePending} onClick={() => void promote()}>
              Update stage
            </Button>
          </>
        }
      >
        <div className="stage-options">
          {[
            {
              id: 'staging',
              title: 'Staging',
              description: 'Ready for review or a canary deployment.',
            },
            {
              id: 'production',
              title: 'Production',
              description: 'Approved for serving. Multiple versions may be in production.',
            },
            {
              id: 'none',
              title: 'Remove stage',
              description: 'Keep the version available without a promotion label.',
            },
          ].map((option) => (
            <label
              key={option.id}
              className={`stage-option ${stageChoice === option.id ? 'is-selected' : ''}`}
            >
              <input
                type="radio"
                name="model-stage"
                value={option.id}
                checked={stageChoice === option.id}
                onChange={() => setStageChoice(option.id)}
              />
              <span>
                <strong>{option.title}</strong>
                <small>{option.description}</small>
              </span>
            </label>
          ))}
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(archiveTarget)}
        onClose={() => setArchiveTarget(null)}
        title={archiveTarget ? `Archive version ${archiveTarget.version}?` : 'Archive version'}
        description="Archived versions stay in the registry and can still be downloaded. Existing deployments that pin this version keep serving it."
        confirmLabel="Archive version"
        pending={archivePending}
        onConfirm={() => void archive()}
      />

      <Modal
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        title="Compare model versions"
        description="Metrics and hyperparameters for the selected versions."
        width={980}
        footer={
          <Button variant="secondary" onClick={() => setCompareOpen(false)}>
            Close
          </Button>
        }
      >
        {compareError ? <ErrorBlock message={compareError} /> : null}
        {compareLoading ? <LoadingBlock rows={8} /> : null}
        {compareData ? (
          <VersionCompareTable data={compareData} model={current} />
        ) : null}
      </Modal>
    </>
  )
}

function VersionCompareTable({
  data,
  model,
}: {
  data: VersionCompare
  model: ModelDetail
}) {
  const parameterKeys = useMemo(() => {
    const keys = new Set<string>()
    for (const version of data.versions) for (const key of Object.keys(version.params)) keys.add(key)
    return Array.from(keys).sort()
  }, [data.versions])

  return (
    <div className="table-wrap compare-wrap">
      <table className="compare-table">
        <thead>
          <tr>
            <th className="compare-corner">
              <span className="eyebrow-label">Version</span>
            </th>
            {data.versions.map((version) => (
              <th key={version.id} className="compare-experiment-head">
                <Link to={`/experiments/${version.experiment_id}`} className="cell-link">
                  {model.name} v{version.version}
                </Link>
                <div className="compare-head-meta">{version.algorithm.replaceAll('_', ' ')}</div>
                <div className="compare-head-badges">
                  <StatusPill
                    status={version.stage}
                    label={statusLabel(version.stage)}
                    tone={statusTone(version.stage)}
                  />
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="compare-section-row">
            <th colSpan={data.versions.length + 1}>
              <span>Metrics</span>
              <span className="muted">Best value marked</span>
            </th>
          </tr>
          {data.metric_keys.map((key) => {
            const direction = data.directions[key] ?? 'max'
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
                {data.versions.map((version) => {
                  const isBest = data.best[key] === version.id
                  return (
                    <td key={version.id} className={`num ${isBest ? 'is-best' : ''}`}>
                      <span className="compare-value">
                        {formatMetric(key, version.metrics[key])}
                      </span>
                      {isBest ? <span className="best-mark">Best</span> : null}
                    </td>
                  )
                })}
              </tr>
            )
          })}
          <tr className="compare-section-row">
            <th colSpan={data.versions.length + 1}>
              <span>Hyperparameters</span>
            </th>
          </tr>
          {parameterKeys.map((key) => (
            <tr key={key}>
              <th className="compare-metric-name">
                <span className="mono">{key}</span>
              </th>
              {data.versions.map((version) => {
                const value = version.params[key]
                return (
                  <td key={version.id}>
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
            <th colSpan={data.versions.length + 1}>
              <span>Registry</span>
            </th>
          </tr>
          <tr>
            <th className="compare-metric-name">Stage</th>
            {data.versions.map((version) => (
              <td key={version.id}>
                <Pill tone={statusTone(version.stage)}>{statusLabel(version.stage)}</Pill>
              </td>
            ))}
          </tr>
          <tr>
            <th className="compare-metric-name">Deployments</th>
            {data.versions.map((version) => (
              <td key={version.id} className="num">
                {version.deployment_count}
              </td>
            ))}
          </tr>
          <tr>
            <th className="compare-metric-name">Problem</th>
            {data.versions.map((version) => (
              <td key={version.id}>{version.problem_type ? titleCase(version.problem_type) : '—'}</td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  )
}

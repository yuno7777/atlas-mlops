import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import { useApi } from '../api/hooks'
import type {
  DatasetSummary,
  DatasetVersionSummary,
  DeploymentDetail,
  Page,
  RetrainComparison,
  TrainingJobDetail,
} from '../api/types'
import { Icon } from './Icon'
import { useToast } from './ToastProvider'
import {
  Button,
  ErrorBlock,
  Field,
  Input,
  LoadingBlock,
  Modal,
  Panel,
  SectionHeader,
  Select,
  StatusPill,
} from './ui'
import {
  formatMetric,
  formatMetricDelta,
  metricLabel,
  primaryMetric,
  relativeTime,
} from '../lib/format'

export function RetrainDialog({
  deployment,
  open,
  onClose,
  onQueued,
}: {
  deployment: DeploymentDetail
  open: boolean
  onClose: () => void
  onQueued?: (jobId: string) => void
}) {
  const toast = useToast()
  const comparison = useApi<RetrainComparison>(
    open ? `/deployments/${deployment.id}/retrain/comparison` : null,
  )

  const datasets = useApi<Page<DatasetSummary>>(
    open ? '/datasets' : null,
    { project_id: deployment.project_id, page_size: 100 },
  )

  const matchedDataset = useMemo(() => {
    if (!datasets.data || !deployment.dataset_name) return null
    return datasets.data.items.find((item) => item.name === deployment.dataset_name) ?? null
  }, [datasets.data, deployment.dataset_name])

  const versions = useApi<DatasetVersionSummary[]>(
    open && matchedDataset ? `/datasets/${matchedDataset.id}/versions` : null,
  )

  const [versionId, setVersionId] = useState<string>('')
  const [name, setName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setVersionId('')
      setName('')
      setSubmitError(null)
    }
  }, [open])

  const problemType = deployment.problem_type ?? 'classification'
  const primaryKey = primaryMetric(problemType)

  const submit = async () => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const response = await api.post<TrainingJobDetail>(
        `/deployments/${deployment.id}/retrain`,
        {
          dataset_version_id: versionId.trim() || undefined,
          name: name.trim() || undefined,
        },
      )
      toast.success(`Retraining job queued (${response.name}).`)
      onClose()
      if (onQueued) {
        onQueued(response.id)
      }
    } catch (err) {
      setSubmitError(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const hasRunningJob =
    comparison.data?.latest_job_status === 'running' ||
    comparison.data?.latest_job_status === 'queued'

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Retrain deployment"
      description={`Queue an asynchronous training job using ${deployment.model_name}'s algorithm configuration.`}
      width={720}
      footer={
        <div className="modal-actions-between">
          <Button type="button" variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="primary"
            icon="play"
            loading={submitting}
            onClick={() => void submit()}
          >
            Queue retraining run
          </Button>
        </div>
      }
    >
      <div className="stack-gap-20">
        {hasRunningJob && comparison.data?.latest_job_id ? (
          <div className="inline-notice inline-notice-warning">
            <Icon name="alert-triangle" size={16} />
            <span>
              A retraining job is currently active for this deployment.{' '}
              <Link to={`/training/${comparison.data.latest_job_id}`} className="text-link">
                View training job
              </Link>
            </span>
          </div>
        ) : null}

        <div className="form-grid-2">
          <Field
            label="Dataset version"
            htmlFor="retrain-dataset-version"
            hint="Choose which dataset version to train against. Defaults to the deployed version."
          >
            <Select
              id="retrain-dataset-version"
              value={versionId}
              onChange={(e) => setVersionId(e.target.value)}
            >
              <option value="">
                Current version {deployment.dataset_version ? `(v${deployment.dataset_version})` : ''}
              </option>
              {versions.data?.map((version) => (
                <option key={version.id} value={version.id}>
                  v{version.version} &middot; {version.original_filename} ({version.row_count} rows)
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Job name"
            htmlFor="retrain-name"
            hint="Optional label for the training job and generated experiment."
          >
            <Input
              id="retrain-name"
              placeholder={`Retrain \u00b7 ${deployment.name}`}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
        </div>

        {submitError ? <div className="error-block">{submitError}</div> : null}

        {comparison.loading ? (
          <LoadingBlock rows={4} />
        ) : comparison.error ? (
          <ErrorBlock message={comparison.error} onRetry={comparison.reload} />
        ) : comparison.data ? (
          <div className="stack-gap-16">
            <Panel>
              <SectionHeader
                title="Current vs Challenger experiments"
                description={`Evaluation metrics comparison based on ${metricLabel(primaryKey)}.`}
              />
              <div className="definition-list compact" style={{ marginBottom: 12 }}>
                <div>
                  <span>Incumbent model</span>
                  <strong>
                    {deployment.model_name} v{comparison.data.incumbent.version} &middot;{' '}
                    {formatMetric(
                      primaryKey,
                      comparison.data.incumbent.metrics[primaryKey] as number | null,
                    )}
                  </strong>
                </div>
                <div>
                  <span>Recommendation</span>
                  <span>{comparison.data.recommendation_reason}</span>
                </div>
              </div>

              {comparison.data.candidates.length > 0 ? (
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Candidate Experiment</th>
                        <th>Algorithm</th>
                        <th className="num">{metricLabel(primaryKey)}</th>
                        <th className="num">Delta vs Incumbent</th>
                        <th>Recommendation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparison.data.candidates.map((candidate) => {
                        const candMetric = candidate.metrics[primaryKey] ?? null
                        const incMetric = (comparison.data?.incumbent.metrics[primaryKey] as number) ?? null
                        const delta =
                          candMetric !== null && incMetric !== null ? candMetric - incMetric : null
                        const isRecommended =
                          comparison.data?.recommended_experiment_id === candidate.id

                        return (
                          <tr key={candidate.id}>
                            <td>
                              <Link to={`/experiments/${candidate.id}`} className="cell-link">
                                {candidate.name}
                              </Link>
                              <div className="cell-sub">{relativeTime(candidate.created_at)}</div>
                            </td>
                            <td>{candidate.algorithm_label}</td>
                            <td className="num">{formatMetric(primaryKey, candMetric)}</td>
                            <td className="num">
                              {delta !== null ? (
                                <span
                                  className={`delta-badge ${
                                    delta > 0 ? 'is-positive' : delta < 0 ? 'is-negative' : ''
                                  }`}
                                >
                                  {formatMetricDelta(primaryKey, delta)}
                                </span>
                              ) : (
                                <span className="cell-null">&mdash;</span>
                              )}
                            </td>
                            <td>
                              {isRecommended ? (
                                <StatusPill status="recommended" label="Recommended" tone="positive" />
                              ) : (
                                <span className="cell-null">Candidate</span>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="chart-empty" style={{ margin: '8px 0' }}>
                  No candidate retrain experiments completed yet for this deployment.
                </p>
              )}
            </Panel>
          </div>
        ) : null}
      </div>
    </Modal>
  )
}

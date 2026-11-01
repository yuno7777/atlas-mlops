import { useState } from 'react'
import { api, errorMessage } from '../api/client'
import { useApi } from '../api/hooks'
import type { ChallengerInfo, DeploymentRollout, ModelDetail } from '../api/types'
import { useToast } from './ToastProvider'
import { Button, EmptyState, ErrorBlock, Field, Input, Panel, SectionHeader, Select, StatusPill } from './ui'
import { formatNumber, formatPercent, statusLabel, statusTone } from '../lib/format'

export function ChallengerPanel({ deploymentId, modelId, championVersionId }: { deploymentId: string; modelId: string; championVersionId: string }) {
  const toast = useToast()
  const info = useApi<ChallengerInfo>(`/deployments/${deploymentId}/challenger`, undefined, { pollMs: 15000 })
  const model = useApi<ModelDetail>(`/models/${modelId}`)
  const rollout = useApi<DeploymentRollout | null>(`/deployments/${deploymentId}/rollout`, undefined, { pollMs: 10000 })
  const [candidateId, setCandidateId] = useState('')
  const [trafficOverride, setTrafficOverride] = useState<{ deploymentId: string; value: number } | null>(null)
  const [minSamples, setMinSamples] = useState(100)
  const [minLabeledSamples, setMinLabeledSamples] = useState(20)
  const [maxErrorPercent, setMaxErrorPercent] = useState(2)
  const [maxP95Latency, setMaxP95Latency] = useState(1000)
  const [maxMetricDropPercent, setMaxMetricDropPercent] = useState(3)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const candidates = model.data?.versions.filter((version) => version.id !== championVersionId && version.stage !== 'archived') ?? []
  const traffic = trafficOverride?.deploymentId === deploymentId
    ? trafficOverride.value
    : info.data?.traffic_percent || 10
  const automated = rollout.data?.status === 'running'
  const evaluation = rollout.data?.last_evaluation ?? {}
  const evaluationText = typeof evaluation.reason === 'string' ? evaluation.reason : 'Waiting for rollout evaluation.'

  const refresh = () => { info.reload(); rollout.reload() }
  const act = async (action: 'set' | 'traffic' | 'promote' | 'reject' | 'clear') => {
    setPending(true); setError(null)
    try {
      if (action === 'set') await api.put(`/deployments/${deploymentId}/challenger`, { model_version_id: candidateId, traffic_percent: traffic })
      if (action === 'traffic') await api.patch(`/deployments/${deploymentId}/challenger`, { traffic_percent: traffic })
      if (action === 'promote') await api.post(`/deployments/${deploymentId}/challenger/promote`)
      if (action === 'reject') await api.post(`/deployments/${deploymentId}/challenger/reject`)
      if (action === 'clear') await api.delete(`/deployments/${deploymentId}/challenger`)
      refresh()
      toast.success(action === 'promote' ? 'Challenger promoted to champion.' : action === 'reject' || action === 'clear' ? 'Challenger configuration cleared.' : 'Challenger routing updated.')
    } catch (caught) { setError(errorMessage(caught)) } finally { setPending(false) }
  }

  const startRollout = async () => {
    const modelVersionId = info.data?.challenger_version_id ?? candidateId
    if (!modelVersionId) return
    setPending(true); setError(null)
    try {
      await api.post<DeploymentRollout>(`/deployments/${deploymentId}/rollout`, {
        model_version_id: modelVersionId,
        traffic_steps: [5, 20, 50, 100],
        gates: {
          min_samples: minSamples,
          max_error_rate: maxErrorPercent / 100,
          max_p95_latency_ms: maxP95Latency,
          min_labeled_samples: minLabeledSamples,
          max_metric_regression: maxMetricDropPercent / 100,
        },
      })
      refresh()
      toast.success('Progressive rollout started at 5% traffic.')
    } catch (caught) { setError(errorMessage(caught)) } finally { setPending(false) }
  }

  const cancelRollout = async () => {
    setPending(true); setError(null)
    try {
      await api.post<DeploymentRollout>(`/deployments/${deploymentId}/rollout/cancel`)
      refresh()
      toast.success('Rollout cancelled; traffic returned to the champion.')
    } catch (caught) { setError(errorMessage(caught)) } finally { setPending(false) }
  }

  if (info.error || model.error) return <ErrorBlock message={info.error ?? model.error ?? 'Could not load challenger settings.'} onRetry={() => { info.reload(); model.reload(); rollout.reload() }} />
  if (info.loading || model.loading || !info.data || !model.data) return <Panel><p className="panel-note">Loading challenger controls…</p></Panel>
  const configured = Boolean(info.data.challenger_version_id)

  return <div className="stack-gap-20">
    <Panel>
      <SectionHeader title="Champion and challenger" description="Route a controlled share of requests to a candidate version and compare live outcomes." />
      <div className="challenger-compare">
        <div className="challenger-model"><span className="eyebrow-label">Champion · 100% baseline</span><strong>v{info.data.champion_version}</strong><span>{info.data.champion_algorithm}</span></div>
        <div className="challenger-model is-candidate"><span className="eyebrow-label">Challenger · {info.data.traffic_percent}% traffic</span><strong>{configured ? `v${info.data.challenger_version}` : 'Not configured'}</strong><span>{info.data.challenger_algorithm ?? 'Choose a model version below'}</span></div>
      </div>
      {!configured ? <div className="challenger-controls">
        {candidates.length ? <>
          <Field label="Candidate model version" htmlFor="challenger-version"><Select id="challenger-version" value={candidateId} onChange={(event) => setCandidateId(event.target.value)}><option value="">Select a version</option>{candidates.map((version) => <option key={version.id} value={version.id}>v{version.version} · {version.algorithm} · {version.stage}</option>)}</Select></Field>
          <Field label={`Traffic share: ${traffic}%`} htmlFor="challenger-traffic"><input id="challenger-traffic" className="range-input" type="range" min="1" max="80" value={traffic} onChange={(event) => setTrafficOverride({ deploymentId, value: Number(event.target.value) })} /></Field>
          <div className="button-group"><Button variant="secondary" loading={pending} disabled={!candidateId || automated} onClick={() => void act('set')}>Start comparison</Button><Button variant="primary" icon="rocket" loading={pending} disabled={!candidateId || automated} onClick={() => void startRollout()}>Start progressive rollout</Button></div>
        </> : <EmptyState compact icon="cube" title="No candidate versions" description="Register another version of this model before starting a comparison." />}
      </div> : <div className="form-actions"><Field label={`Challenger traffic: ${traffic}%`} htmlFor="challenger-traffic"><input id="challenger-traffic" className="range-input" type="range" min="0" max="80" value={traffic} disabled={automated} onChange={(event) => setTrafficOverride({ deploymentId, value: Number(event.target.value) })} /></Field><Button variant="secondary" loading={pending} disabled={automated} onClick={() => void act('traffic')}>Save traffic</Button><Button variant="primary" loading={pending} disabled={automated} onClick={() => void act('promote')}>Promote challenger</Button><Button variant="danger-ghost" loading={pending} disabled={automated} onClick={() => void act('reject')}>Reject</Button><Button variant="primary" icon="rocket" loading={pending} disabled={automated} onClick={() => void startRollout()}>Start progressive rollout</Button></div>}
      {configured && !automated ? <div className="challenger-clear"><Button size="sm" variant="ghost" loading={pending} onClick={() => void act('clear')}>Clear configuration</Button></div> : null}
      {error ? <div className="error-block" role="alert">{error}</div> : null}
    </Panel>

    <Panel>
      <SectionHeader title="Automated release gates" description="Traffic advances through 5%, 20%, 50%, and 100% only when the sample, failure, latency, and labeled-quality gates pass." action={rollout.data ? <StatusPill status={rollout.data.status} label={statusLabel(rollout.data.status)} tone={statusTone(rollout.data.status)} /> : undefined} />
      {!automated ? <>
        <p className="panel-note">Configure gates before starting. Feedback-based quality checks require labels on both candidate and incumbent requests.</p>
        <div className="form-grid-3 rollout-gates-form">
          <Field label="Minimum candidate requests" htmlFor="rollout-min-samples"><Input id="rollout-min-samples" type="number" min={10} value={minSamples} onChange={(event) => setMinSamples(Math.max(10, Number(event.target.value)))} /></Field>
          <Field label="Minimum labels per variant" htmlFor="rollout-min-labels"><Input id="rollout-min-labels" type="number" min={0} value={minLabeledSamples} onChange={(event) => setMinLabeledSamples(Math.max(0, Number(event.target.value)))} /></Field>
          <Field label="Maximum error rate (%)" htmlFor="rollout-error-rate"><Input id="rollout-error-rate" type="number" min={0} max={100} step={0.1} value={maxErrorPercent} onChange={(event) => setMaxErrorPercent(Math.min(100, Math.max(0, Number(event.target.value))))} /></Field>
          <Field label="Maximum p95 latency (ms)" htmlFor="rollout-latency"><Input id="rollout-latency" type="number" min={1} value={maxP95Latency} onChange={(event) => setMaxP95Latency(Math.max(1, Number(event.target.value)))} /></Field>
          <Field label="Maximum metric regression (%)" htmlFor="rollout-quality"><Input id="rollout-quality" type="number" min={0} max={100} step={0.1} value={maxMetricDropPercent} onChange={(event) => setMaxMetricDropPercent(Math.min(100, Math.max(0, Number(event.target.value))))} /></Field>
        </div>
      </> : (
        <>
          <div className="rollout-progress">
            {rollout.data?.traffic_steps.map((step, index) => <div className={`rollout-stage ${index <= (rollout.data?.current_step ?? 0) ? 'is-active' : ''}`} key={step}><span>{step}%</span><small>{index < (rollout.data?.current_step ?? 0) ? 'Passed' : index === rollout.data?.current_step ? 'Current' : 'Pending'}</small></div>)}
          </div>
          <p className="panel-note">{evaluationText}</p>
          <div className="rollout-evidence">
            <span>Requests: {formatNumber(Number(evaluation.candidate_samples ?? 0))}</span>
            <span>Errors: {typeof evaluation.candidate_error_rate === 'number' ? formatPercent(evaluation.candidate_error_rate) : '—'}</span>
            <span>p95: {typeof evaluation.candidate_p95_latency_ms === 'number' ? `${formatNumber(evaluation.candidate_p95_latency_ms, 1)} ms` : '—'}</span>
            <span>Labeled: {formatNumber(Number(evaluation.challenger_labeled_samples ?? 0))} / {formatNumber(Number(evaluation.champion_labeled_samples ?? 0))}</span>
          </div>
          <div className="form-actions"><Button variant="danger-ghost" loading={pending} onClick={() => void cancelRollout()}>Cancel rollout</Button><Button variant="ghost" size="sm" icon="refresh" onClick={refresh}>Refresh status</Button></div>
        </>
      )}
    </Panel>

    <Panel>
      <SectionHeader title="Live comparison" description="Counts and latency update as predictions are routed. Accuracy appears after labels are submitted." />
      {info.data.variants.length ? <div className="table-wrap"><table className="data"><thead><tr><th>Variant</th><th>Model</th><th className="num">Predictions</th><th className="num">Labeled</th><th className="num">Accuracy</th><th className="num">Avg latency</th></tr></thead><tbody>{info.data.variants.map((variant) => <tr key={variant.variant}><td>{variant.variant === 'champion' ? 'Champion' : 'Challenger'}</td><td>{variant.algorithm ?? 'Model'} {variant.model_version ? `v${variant.model_version}` : ''}</td><td className="num">{formatNumber(variant.predictions)}</td><td className="num">{formatNumber(variant.labeled)}</td><td className="num">{variant.accuracy === null ? '—' : formatPercent(variant.accuracy)}</td><td className="num">{formatNumber(variant.avg_latency_ms, 1)} ms</td></tr>)}</tbody></table></div> : <EmptyState compact icon="activity" title="No comparison traffic yet" description="Run predictions after configuring a challenger to collect live metrics." />}
    </Panel>
  </div>
}

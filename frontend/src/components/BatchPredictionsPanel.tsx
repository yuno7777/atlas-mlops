import { useState } from 'react'
import { api, downloadFile, errorMessage } from '../api/client'
import { useApi } from '../api/hooks'
import type { BatchPrediction } from '../api/types'
import { useToast } from './ToastProvider'
import { Button, EmptyState, ErrorBlock, Panel, Pill, SectionHeader } from './ui'
import { formatDateTime, formatNumber, statusLabel } from '../lib/format'

export function BatchPredictionsPanel({ deploymentId }: { deploymentId: string }) {
  const toast = useToast()
  const batches = useApi<BatchPrediction[]>(`/deployments/${deploymentId}/batch-predictions`)
  const [file, setFile] = useState<File | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const upload = async () => {
    if (!file) return
    setPending(true); setError(null)
    try {
      const form = new FormData()
      form.set('file', file)
      const created = await api.upload<BatchPrediction>(`/deployments/${deploymentId}/batch-predictions`, form)
      setFile(null); batches.reload(); toast.success(`Scored ${created.success_count} rows.`)
    } catch (caught) { setError(errorMessage(caught)) } finally { setPending(false) }
  }

  const download = async (batch: BatchPrediction) => {
    try { await downloadFile(`/deployments/${deploymentId}/batch-predictions/${batch.id}/download`, `predictions-${batch.id.slice(0, 8)}.csv`) }
    catch (caught) { toast.error(errorMessage(caught)) }
  }

  return <div className="stack-gap-20">
    <Panel>
      <SectionHeader title="Score a CSV" description="Upload a file with the model’s feature columns. The target column is optional and removed before scoring." />
      <div className="batch-upload-row">
        <label className="batch-file-picker" htmlFor="batch-file"><span>{file?.name ?? 'Choose a CSV file'}</span><span className="muted">CSV · up to configured upload limit</span></label>
        <input id="batch-file" type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        <Button variant="primary" icon="play" loading={pending} disabled={!file} onClick={() => void upload()}>Score rows</Button>
      </div>
      {error ? <div className="error-block" role="alert">{error}</div> : null}
    </Panel>
    <Panel>
      <SectionHeader title="Recent batches" description="Completed runs include a preview and downloadable CSV with predictions." />
      {batches.error ? <ErrorBlock compact message={batches.error} onRetry={batches.reload} /> : batches.loading ? <p className="panel-note">Loading batch history…</p> : batches.data?.length ? <div className="table-wrap"><table className="data"><thead><tr><th>File</th><th>Status</th><th className="num">Rows</th><th>Created</th><th /></tr></thead><tbody>{batches.data.map((batch) => <tr key={batch.id}><td><strong>{batch.original_filename}</strong>{batch.error_message ? <span className="cell-sub">{batch.error_message}</span> : null}</td><td><Pill tone={batch.status === 'completed' ? 'positive' : batch.status === 'failed' ? 'negative' : 'warning'}>{statusLabel(batch.status)}</Pill></td><td className="num">{formatNumber(batch.success_count)} / {formatNumber(batch.row_count)}</td><td className="muted">{formatDateTime(batch.created_at)}</td><td className="num"><Button size="sm" variant="secondary" disabled={batch.status !== 'completed'} onClick={() => void download(batch)}>Download CSV</Button></td></tr>)}</tbody></table></div> : <EmptyState compact icon="file" title="No batch runs" description="Upload a CSV to score multiple records at once." />}
    </Panel>
    {batches.data?.filter((batch) => batch.preview.length).slice(0, 1).map((batch) => <Panel key={batch.id}>
      <SectionHeader title="Latest result preview" description={`${batch.original_filename} · showing ${batch.preview.length} of ${batch.row_count} rows`} />
      <div className="table-wrap"><table className="data"><thead><tr>{batch.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{batch.preview.map((row, index) => <tr key={`${batch.id}-${index}`}>{batch.columns.map((column) => <td key={column}>{String(row[column] ?? '—')}</td>)}</tr>)}</tbody></table></div>
    </Panel>)}
  </div>
}

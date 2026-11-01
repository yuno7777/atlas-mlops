import { useState } from 'react'
import { api, errorMessage } from '../api/client'
import { useApi } from '../api/hooks'
import type { AlertChannel, AlertTestResponse } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { useToast } from './ToastProvider'
import { Button, EmptyState, ErrorBlock, Field, Input, Panel, Pill, SectionHeader, Select } from './ui'
import { formatDateTime, statusLabel } from '../lib/format'

type ChannelForm = { name: string; kind: 'webhook' | 'slack'; target_url: string; secret: string; min_status: 'warning' | 'critical' }
const emptyForm: ChannelForm = { name: '', kind: 'webhook', target_url: '', secret: '', min_status: 'warning' }

export function AlertSettingsPanel() {
  const { project } = useWorkspace()
  const toast = useToast()
  const [form, setForm] = useState<ChannelForm>(emptyForm)
  const [editing, setEditing] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const channels = useApi<AlertChannel[]>(project ? `/projects/${project.id}/alert-channels` : null)

  const save = async () => {
    if (!project) return
    setPending(true); setError(null)
    try {
      const payload = { name: form.name, kind: form.kind, target_url: form.target_url, min_status: form.min_status, ...(form.secret ? { secret: form.secret } : {}) }
      if (editing) await api.patch(`/projects/${project.id}/alert-channels/${editing}`, payload)
      else await api.post(`/projects/${project.id}/alert-channels`, payload)
      setForm(emptyForm); setEditing(null); channels.reload(); toast.success(editing ? 'Alert channel updated.' : 'Alert channel created.')
    } catch (caught) { setError(errorMessage(caught)) } finally { setPending(false) }
  }

  const test = async (channel: AlertChannel) => {
    if (!project) return
    try {
      const result = await api.post<AlertTestResponse>(`/projects/${project.id}/alert-channels/${channel.id}/test`)
      channels.reload()
      if (result.ok) toast.success(`Test alert delivered (${result.response_code ?? 'no status'}).`)
      else toast.error(result.error ?? 'Test alert delivery failed.')
    } catch (caught) { toast.error(errorMessage(caught)) }
  }

  const toggle = async (channel: AlertChannel) => {
    if (!project) return
    try { await api.patch(`/projects/${project.id}/alert-channels/${channel.id}`, { enabled: !channel.enabled }); channels.reload() }
    catch (caught) { toast.error(errorMessage(caught)) }
  }

  const remove = async (channel: AlertChannel) => {
    if (!project) return
    try { await api.delete(`/projects/${project.id}/alert-channels/${channel.id}`); channels.reload(); toast.success('Alert channel removed.') }
    catch (caught) { toast.error(errorMessage(caught)) }
  }

  const edit = (channel: AlertChannel) => {
    setEditing(channel.id)
    setForm({ name: channel.name, kind: channel.kind, target_url: channel.target_url, secret: '', min_status: channel.min_status })
  }

  if (!project) return <Panel><EmptyState compact icon="alert-triangle" title="Choose a project" description="Alert channels are configured per project." /></Panel>
  return <div className="stack-gap-20">
    <Panel>
      <SectionHeader title={editing ? 'Edit alert channel' : 'Add alert channel'} description="Send warning or critical drift transitions to Slack or an HTTP webhook." />
      <div className="alert-form-grid">
        <Field label="Channel name" htmlFor="alert-name"><Input id="alert-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Production monitoring" /></Field>
        <Field label="Destination type" htmlFor="alert-kind"><Select id="alert-kind" value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as ChannelForm['kind'] })}><option value="webhook">Generic webhook</option><option value="slack">Slack incoming webhook</option></Select></Field>
        <Field label="Webhook URL" htmlFor="alert-url"><Input id="alert-url" type="url" value={form.target_url} onChange={(event) => setForm({ ...form, target_url: event.target.value })} placeholder="https://hooks.example.com/…" /></Field>
        <Field label="Minimum alert level" htmlFor="alert-status"><Select id="alert-status" value={form.min_status} onChange={(event) => setForm({ ...form, min_status: event.target.value as ChannelForm['min_status'] })}><option value="warning">Warning and critical</option><option value="critical">Critical only</option></Select></Field>
        <Field label="Signing secret" htmlFor="alert-secret" hint="Optional. The secret is never returned after saving."><Input id="alert-secret" type="password" autoComplete="new-password" value={form.secret} onChange={(event) => setForm({ ...form, secret: event.target.value })} placeholder={editing ? 'Leave blank to keep current secret' : 'Optional'} /></Field>
      </div>
      {error ? <div className="error-block" role="alert">{error}</div> : null}
      <div className="form-actions"><Button variant="ghost" disabled={!editing || pending} onClick={() => { setEditing(null); setForm(emptyForm); setError(null) }}>Cancel</Button><Button variant="primary" loading={pending} disabled={!form.name.trim() || !form.target_url.trim()} onClick={() => void save()}>{editing ? 'Save channel' : 'Create channel'}</Button></div>
    </Panel>
    <Panel>
      <SectionHeader title="Configured channels" description="Use the test action to verify the destination before relying on drift notifications." />
      {channels.error ? <ErrorBlock compact message={channels.error} onRetry={channels.reload} /> : channels.loading ? <p className="panel-note">Loading alert channels…</p> : channels.data?.length ? <div className="alert-channel-list">{channels.data.map((channel) => <article className="alert-channel" key={channel.id}>
        <div className="alert-channel-main"><div className="inline-row"><h3>{channel.name}</h3><Pill tone={channel.enabled ? 'positive' : 'neutral'}>{channel.enabled ? 'Enabled' : 'Paused'}</Pill><Pill tone="neutral">{channel.kind === 'slack' ? 'Slack' : 'Webhook'}</Pill></div><div className="mono break-all alert-url">{channel.target_url}</div><div className="cell-sub">{statusLabel(channel.min_status)} minimum · {channel.has_secret ? 'Signed' : 'Unsigned'} · Last test: {channel.last_delivery_at ? formatDateTime(channel.last_delivery_at) : 'Never'}</div>
          {channel.recent_deliveries.length ? <div className="cell-sub">Recent delivery: {channel.recent_deliveries[0].status}{channel.recent_deliveries[0].response_code ? ` · HTTP ${channel.recent_deliveries[0].response_code}` : ''}{channel.recent_deliveries[0].error_message ? ` · ${channel.recent_deliveries[0].error_message}` : ''}</div> : null}</div>
        <div className="inline-row alert-channel-actions"><Button size="sm" variant="secondary" onClick={() => void test(channel)}>Send test</Button><Button size="sm" variant="ghost" onClick={() => toggle(channel)}>{channel.enabled ? 'Pause' : 'Enable'}</Button><Button size="sm" variant="ghost" onClick={() => edit(channel)}>Edit</Button><Button size="sm" variant="danger-ghost" onClick={() => void remove(channel)}>Delete</Button></div>
      </article>)}</div> : <EmptyState compact icon="alert-triangle" title="No alert channels" description="Create a channel to receive notifications when monitoring detects drift." />}
    </Panel>
  </div>
}

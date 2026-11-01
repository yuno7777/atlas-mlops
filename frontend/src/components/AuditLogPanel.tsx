import { useState } from 'react'
import { useApi } from '../api/hooks'
import type { AuditEventPage } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Button, EmptyState, ErrorBlock, Field, Input, LoadingBlock, Panel, Select, SectionHeader } from './ui'
import { formatDateTime } from '../lib/format'

const PAGE_SIZE = 20

export function AuditLogPanel() {
  const { workspace, projects } = useWorkspace()
  const [offset, setOffset] = useState(0)
  const [action, setAction] = useState('')
  const [projectId, setProjectId] = useState('')
  const audit = useApi<AuditEventPage>(workspace ? `/workspaces/${workspace.id}/audit-events` : null, {
    offset, limit: PAGE_SIZE, action: action.trim() || undefined, project_id: projectId || undefined,
  })

  return <Panel>
    <SectionHeader title="Workspace audit log" description="Search recorded actions across projects, members, deployments, and model changes." />
    <div className="audit-filters">
      <Field label="Action contains" htmlFor="audit-action"><Input id="audit-action" value={action} onChange={(event) => { setAction(event.target.value); setOffset(0) }} placeholder="e.g. member.invited" /></Field>
      <Field label="Project" htmlFor="audit-project"><Select id="audit-project" value={projectId} onChange={(event) => { setProjectId(event.target.value); setOffset(0) }}><option value="">All projects</option>{projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
    </div>
    {audit.error ? <ErrorBlock compact message={audit.error} onRetry={audit.reload} /> : audit.loading && !audit.data ? <LoadingBlock rows={5} /> : audit.data?.items.length ? <>
      <div className="table-wrap"><table className="data"><thead><tr><th>Action</th><th>Resource</th><th>Actor</th><th>When</th></tr></thead><tbody>{audit.data.items.map((event) => <tr key={event.id}><td><details className="audit-event-details"><summary className="mono">{event.action}</summary><pre>{JSON.stringify(event.details, null, 2)}</pre></details></td><td>{event.resource_type}{event.resource_id ? <span className="cell-sub mono">{event.resource_id}</span> : null}</td><td>{event.user_email ?? 'System'}{event.ip_address ? <span className="cell-sub mono">{event.ip_address}</span> : null}</td><td className="muted">{formatDateTime(event.created_at)}</td></tr>)}</tbody></table></div>
      <div className="audit-pagination"><span className="muted">{audit.data.total ? offset + 1 : 0}–{Math.min(offset + PAGE_SIZE, audit.data.total)} of {audit.data.total}</span><div className="inline-row"><Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</Button><Button size="sm" disabled={offset + PAGE_SIZE >= audit.data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</Button></div></div>
    </> : <EmptyState compact icon="activity" title="No matching events" description="Adjust the filters or return after a workspace action has been recorded." />}
  </Panel>
}

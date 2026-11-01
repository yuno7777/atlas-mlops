import { useEffect, useState } from 'react'
import { api, errorMessage } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { AuditEvent, Member, SystemInfo, User } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { useToast } from '../components/ToastProvider'
import {
  Button,
  DefinitionGrid,
  EmptyState,
  ErrorBlock,
  Field,
  Input,
  PageHeader,
  Panel,
  Pill,
  SectionHeader,
  StatusPill,
  Tabs,
} from '../components/ui'
import {
  formatDate,
  formatDateTime,
  relativeTime,
  statusLabel,
} from '../lib/format'

type SettingsTab = 'profile' | 'workspace' | 'system'

export function SettingsPage() {
  useDocumentTitle('Settings')
  const { user, updateUser } = useAuth()
  const { workspace, project } = useWorkspace()
  const toast = useToast()
  const [tab, setTab] = useState<SettingsTab>('profile')

  const members = useApi<Member[]>(
    tab === 'workspace' && workspace ? `/workspaces/${workspace.id}/members` : null,
  )
  const audit = useApi<AuditEvent[]>(
    tab === 'workspace' && project ? `/projects/${project.id}/audit-events` : null,
    { limit: 12 },
  )
  const system = useApi<SystemInfo>(tab === 'system' ? '/system/info' : null)

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Settings"
        description="Your account, the people with access, and the runtime this Atlas instance is using."
      />
      <Tabs
        items={[
          { id: 'profile', label: 'Profile' },
          { id: 'workspace', label: 'Workspace' },
          { id: 'system', label: 'System' },
        ]}
        value={tab}
        onChange={(value) => setTab(value as SettingsTab)}
        ariaLabel="Settings sections"
      />

      <div className="settings-body">
        {tab === 'profile' ? (
          <div className="settings-grid">
            <ProfilePanel
              user={user}
              onSaved={(next) => {
                updateUser(next)
                toast.success('Profile updated.')
              }}
            />
            <PasswordPanel />
          </div>
        ) : null}

        {tab === 'workspace' ? (
          <div className="stack-gap-20">
            <div className="settings-grid">
              <Panel>
                <SectionHeader
                  title="Workspace"
                  description="Every dataset, model and deployment is scoped to this workspace."
                />
                <DefinitionGrid
                  items={[
                    { label: 'Name', value: workspace?.name ?? '—' },
                    { label: 'Slug', value: <span className="mono">{workspace?.slug ?? '—'}</span> },
                    { label: 'Your role', value: workspace?.role ?? '—' },
                    { label: 'Created', value: formatDate(workspace?.created_at) },
                  ]}
                />
              </Panel>
              <Panel>
                <SectionHeader title="Current project" />
                <DefinitionGrid
                  items={[
                    { label: 'Name', value: project?.name ?? '—' },
                    { label: 'Slug', value: <span className="mono">{project?.slug ?? '—'}</span> },
                    { label: 'Created', value: formatDate(project?.created_at) },
                    { label: 'Updated', value: relativeTime(project?.updated_at) },
                  ]}
                />
                {project?.description ? <p className="panel-note">{project.description}</p> : null}
              </Panel>
            </div>

            <Panel>
              <SectionHeader
                title="Members"
                description="Accounts with access to this workspace."
                action={
                  <Pill tone="neutral">
                    {members.data?.length ?? 0} member{(members.data?.length ?? 0) === 1 ? '' : 's'}
                  </Pill>
                }
              />
              {members.error ? (
                <ErrorBlock compact message={members.error} onRetry={members.reload} />
              ) : members.data?.length ? (
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th className="num">Joined</th>
                      </tr>
                    </thead>
                    <tbody>
                      {members.data.map((member) => (
                        <tr key={member.user_id}>
                          <td style={{ fontWeight: 500 }}>{member.full_name}</td>
                          <td className="muted">{member.email}</td>
                          <td>
                            <Pill tone={member.role === 'owner' ? 'info' : 'neutral'}>
                              {statusLabel(member.role)}
                            </Pill>
                          </td>
                          <td className="num muted">{formatDate(member.joined_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : members.loading ? (
                <div className="panel-note">Loading members…</div>
              ) : (
                <EmptyState
                  compact
                  icon="users"
                  title="No members found"
                  description="Workspace membership will appear here."
                />
              )}
            </Panel>

            <Panel>
              <SectionHeader
                title="Project activity"
                description="Recent changes recorded in the audit log."
              />
              {audit.data?.length ? (
                <div className="activity-list">
                  {audit.data.map((event) => (
                    <div className="activity-row" key={event.id}>
                      <div className="activity-mark" aria-hidden="true" />
                      <div className="activity-main">
                        <div>
                          <span className="mono" style={{ fontSize: 12 }}>
                            {event.action}
                          </span>{' '}
                          <span className="muted">on {event.resource_type}</span>
                        </div>
                        <div className="cell-sub">
                          {event.user_email ?? 'System'} · {formatDateTime(event.created_at)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : audit.loading ? (
                <div className="panel-note">Loading activity…</div>
              ) : (
                <p className="chart-empty">No activity recorded for this project yet.</p>
              )}
            </Panel>
          </div>
        ) : null}

        {tab === 'system' ? (
          <div className="settings-grid">
            <Panel>
              <SectionHeader
                title="Runtime"
                description="Read-only information about this Atlas deployment."
              />
              {system.error ? (
                <ErrorBlock compact message={system.error} onRetry={system.reload} />
              ) : system.data ? (
                <DefinitionGrid
                  items={[
                    { label: 'Version', value: system.data.version },
                    { label: 'Environment', value: system.data.environment },
                    {
                      label: 'Execution',
                      value: <span className="mono">{system.data.execution_mode}</span>,
                    },
                    {
                      label: 'Database',
                      value: <span className="mono">{system.data.database}</span>,
                    },
                    {
                      label: 'Artifact storage',
                      value: <span className="mono">{system.data.storage_backend}</span>,
                    },
                    {
                      label: 'Monitoring scheduler',
                      value: (
                        <StatusPill
                          status={system.data.monitoring_scheduler ? 'active' : 'stopped'}
                          label={system.data.monitoring_scheduler ? 'Enabled' : 'Disabled'}
                          tone={system.data.monitoring_scheduler ? 'positive' : 'neutral'}
                        />
                      ),
                    },
                  ]}
                />
              ) : (
                <div className="panel-note">Loading runtime information…</div>
              )}
            </Panel>
            <Panel>
              <SectionHeader title="Tracking and API" />
              {system.data ? (
                <>
                  <DefinitionGrid
                    items={[
                      {
                        label: 'MLflow',
                        value: (
                          <StatusPill
                            status={system.data.mlflow_reachable ? 'healthy' : 'warning'}
                            label={
                              system.data.mlflow_enabled
                                ? system.data.mlflow_reachable
                                  ? 'Reachable'
                                  : 'Enabled, unreachable'
                                : 'Disabled'
                            }
                            tone={
                              !system.data.mlflow_enabled
                                ? 'neutral'
                                : system.data.mlflow_reachable
                                  ? 'positive'
                                  : 'warning'
                            }
                          />
                        ),
                      },
                      { label: 'Checked', value: formatDateTime(system.data.timestamp) },
                    ]}
                  />
                  <div className="panel-note mono break-all">
                    {system.data.mlflow_tracking_uri || 'No tracking URI configured'}
                  </div>
                </>
              ) : null}
              <div className="inline-row" style={{ marginTop: 16 }}>
                <a className="btn btn-secondary btn-md" href="/api/v1/docs" target="_blank" rel="noreferrer">
                  Open API reference
                </a>
                <a className="btn btn-ghost btn-md" href="/api/v1/health" target="_blank" rel="noreferrer">
                  Health check
                </a>
              </div>
            </Panel>
          </div>
        ) : null}
      </div>
    </>
  )
}

function ProfilePanel({
  user,
  onSaved,
}: {
  user: User | null
  onSaved: (user: User) => void
}) {
  const [fullName, setFullName] = useState(user?.full_name ?? '')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setFullName(user?.full_name ?? '')
  }, [user])

  const save = async () => {
    if (!fullName.trim()) {
      setError('Your name cannot be empty.')
      return
    }
    setPending(true)
    setError(null)
    try {
      const updated = await api.patch<User>('/auth/me', { full_name: fullName.trim() })
      onSaved(updated)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <Panel>
      <SectionHeader title="Profile" description="How your name appears in the audit log." />
      <div className="form-stack">
        <Field label="Full name" htmlFor="settings-name">
          <Input
            id="settings-name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            maxLength={120}
          />
        </Field>
        <Field label="Email" htmlFor="settings-email" hint="Email changes are not available yet.">
          <Input id="settings-email" value={user?.email ?? ''} disabled readOnly />
        </Field>
        {error ? <div className="error-block is-compact">{error}</div> : null}
        <div className="form-actions">
          <Button
            variant="secondary"
            disabled={pending || fullName.trim() === (user?.full_name ?? '')}
            onClick={() => setFullName(user?.full_name ?? '')}
          >
            Reset
          </Button>
          <Button variant="primary" loading={pending} onClick={save}>
            Save profile
          </Button>
        </div>
      </div>
    </Panel>
  )
}

function PasswordPanel() {
  const toast = useToast()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    if (next.length < 10) {
      setError('The new password must be at least 10 characters.')
      return
    }
    if (next !== confirm) {
      setError('The new passwords do not match.')
      return
    }
    setPending(true)
    setError(null)
    try {
      await api.post('/auth/change-password', {
        current_password: current,
        new_password: next,
      })
      setCurrent('')
      setNext('')
      setConfirm('')
      toast.success('Password changed.')
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <Panel>
      <SectionHeader
        title="Password"
        description="Use at least 10 characters. Existing sessions stay signed in."
      />
      <div className="form-stack">
        <Field label="Current password" htmlFor="settings-current-password">
          <Input
            id="settings-current-password"
            type="password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            autoComplete="current-password"
          />
        </Field>
        <Field label="New password" htmlFor="settings-new-password">
          <Input
            id="settings-new-password"
            type="password"
            value={next}
            onChange={(event) => setNext(event.target.value)}
            autoComplete="new-password"
          />
        </Field>
        <Field label="Confirm new password" htmlFor="settings-confirm-password">
          <Input
            id="settings-confirm-password"
            type="password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            autoComplete="new-password"
          />
        </Field>
        {error ? <div className="error-block is-compact">{error}</div> : null}
        <div className="form-actions">
          <Button
            variant="primary"
            loading={pending}
            disabled={!current || !next || !confirm}
            onClick={save}
          >
            Change password
          </Button>
        </div>
      </div>
    </Panel>
  )
}

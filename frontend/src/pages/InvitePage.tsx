import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { WorkspaceInvite } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Button, EmptyState, ErrorBlock, LoadingBlock, PageHeader, Panel, Pill } from '../components/ui'
import { formatDateTime, statusLabel } from '../lib/format'

export function InvitePage() {
  const { token } = useParams<{ token: string }>()
  const { user } = useAuth()
  const { refreshWorkspaces, selectWorkspace } = useWorkspace()
  const navigate = useNavigate()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const invite = useApi<WorkspaceInvite>(token ? `/invites/${token}` : null)
  useDocumentTitle('Workspace invitation')

  const accept = async () => {
    if (!token) return
    setPending(true)
    setError(null)
    try {
      const accepted = await api.post<WorkspaceInvite>(`/invites/${token}/accept`)
      selectWorkspace(accepted.workspace_id)
      await refreshWorkspaces()
      navigate('/overview', { replace: true })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <PageHeader eyebrow="Workspace access" title="Invitation" description="Review the invitation before joining this workspace." />
      {invite.error ? <ErrorBlock message={invite.error} onRetry={invite.reload} /> : invite.loading ? <LoadingBlock rows={3} /> : invite.data ? (
        <Panel className="invite-panel">
          <div className="invite-heading"><span className="context-avatar">{invite.data.workspace_id.slice(0, 2).toUpperCase()}</span><div><div className="eyebrow-label">Workspace invitation</div><h2>{invite.data.email}</h2></div></div>
          <div className="definition-list compact">
            <div><span>Invited email</span><strong>{invite.data.email}</strong></div>
            <div><span>Access role</span><Pill tone="info">{statusLabel(invite.data.role)}</Pill></div>
            <div><span>Expires</span><span>{formatDateTime(invite.data.expires_at)}</span></div>
            <div><span>Signed in as</span><strong>{user?.email ?? 'Unknown account'}</strong></div>
          </div>
          {error ? <div className="error-block">{error}</div> : null}
          {user?.email.toLowerCase() !== invite.data.email.toLowerCase() ? <p className="panel-note">Sign in with the invited email address to accept this link.</p> : null}
          <div className="form-actions">
            <Button variant="secondary" onClick={() => navigate('/overview')}>Cancel</Button>
            <Button variant="primary" loading={pending} disabled={user?.email.toLowerCase() !== invite.data.email.toLowerCase()} onClick={() => void accept()}>Join workspace</Button>
          </div>
        </Panel>
      ) : <Panel><EmptyState compact title="Invitation unavailable" description="This invite link could not be loaded." /></Panel>}
    </>
  )
}

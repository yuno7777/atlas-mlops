import { useState } from 'react'
import { api, errorMessage } from '../api/client'
import { useApi } from '../api/hooks'
import type { CreatedWorkspaceInvite, Member, WorkspaceInvite } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { useToast } from './ToastProvider'
import { Button, CopyButton, EmptyState, ErrorBlock, Field, Input, Panel, Pill, SectionHeader, Select } from './ui'
import { formatDate, formatDateTime, statusLabel } from '../lib/format'

export function TeamSettingsPanel({ workspaceId, role }: { workspaceId: string | null; role: string | undefined }) {
  const { user } = useAuth()
  const toast = useToast()
  const members = useApi<Member[]>(workspaceId ? `/workspaces/${workspaceId}/members` : null)
  const invites = useApi<WorkspaceInvite[]>(workspaceId ? `/workspaces/${workspaceId}/invites` : null)
  const [email, setEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('member')
  const [inviteLink, setInviteLink] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canManage = role === 'owner' || role === 'admin'
  const isOwner = role === 'owner'

  const sendInvite = async () => {
    if (!workspaceId || !email.trim()) return
    setPending(true)
    setError(null)
    try {
      const created = await api.post<CreatedWorkspaceInvite>(`/workspaces/${workspaceId}/invites`, {
        email: email.trim(), role: inviteRole,
      })
      setInviteLink(new URL(created.invite_url, window.location.origin).toString())
      setEmail('')
      invites.reload()
      toast.success('Invitation link created.')
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  const updateRole = async (member: Member, nextRole: string) => {
    if (!workspaceId || nextRole === member.role) return
    setError(null)
    try {
      await api.patch<void>(`/workspaces/${workspaceId}/members/${member.user_id}`, { role: nextRole })
      members.setData((members.data ?? []).map((item) => item.user_id === member.user_id ? { ...item, role: nextRole } : item))
      toast.success(`Updated ${member.full_name}'s role.`)
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  const removeMember = async (member: Member) => {
    if (!workspaceId) return
    setError(null)
    try {
      await api.delete<void>(`/workspaces/${workspaceId}/members/${member.user_id}`)
      members.setData((members.data ?? []).filter((item) => item.user_id !== member.user_id))
      toast.success(`Removed ${member.full_name} from the workspace.`)
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  const revokeInvite = async (invite: WorkspaceInvite) => {
    if (!workspaceId) return
    try {
      await api.delete<void>(`/workspaces/${workspaceId}/invites/${invite.id}`)
      invites.reload()
      toast.success('Invitation revoked.')
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  if (!workspaceId) return <Panel><EmptyState compact icon="users" title="Choose a workspace" description="Select a workspace to manage its members." /></Panel>

  return (
    <div className="stack-gap-20">
      <Panel>
        <SectionHeader title="Members" description="Manage workspace access and roles." action={<Pill tone="neutral">{members.data?.length ?? 0} members</Pill>} />
        {members.error ? <ErrorBlock compact message={members.error} onRetry={members.reload} /> : members.loading ? <p className="panel-note">Loading members…</p> : members.data?.length ? (
          <div className="table-wrap"><table className="data"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Joined</th>{canManage ? <th /> : null}</tr></thead><tbody>
            {members.data.map((member) => {
              const protectedMember = member.role === 'owner' || member.user_id === user?.id
              return <tr key={member.user_id}>
                <td style={{ fontWeight: 500 }}>{member.full_name}</td><td className="muted">{member.email}</td>
                <td>{canManage && !protectedMember ? <Select aria-label={`Role for ${member.email}`} value={member.role} onChange={(event) => void updateRole(member, event.target.value)}><option value="admin" disabled={!isOwner}>Admin</option><option value="member">Member</option><option value="viewer">Viewer</option></Select> : <Pill tone={member.role === 'owner' ? 'info' : 'neutral'}>{statusLabel(member.role)}</Pill>}</td>
                <td className="muted">{formatDate(member.joined_at)}</td>
                {canManage ? <td className="num">{!protectedMember ? <Button size="sm" variant="danger-ghost" onClick={() => void removeMember(member)}>Remove</Button> : null}</td> : null}
              </tr>
            })}
          </tbody></table></div>
        ) : <EmptyState compact icon="users" title="No members found" description="Workspace membership will appear here." />}
      </Panel>

      <Panel>
        <SectionHeader title="Invite someone" description="Create a secure link that expires after seven days. Share it with the invited email address." />
        {canManage ? <div className="invite-form">
          <Field label="Email address" htmlFor="invite-email"><Input id="invite-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="teammate@company.com" /></Field>
          <Field label="Role" htmlFor="invite-role"><Select id="invite-role" value={inviteRole} onChange={(event) => setInviteRole(event.target.value)}><option value="member">Member</option><option value="viewer">Viewer</option>{isOwner ? <option value="admin">Admin</option> : null}</Select></Field>
          <Button variant="primary" icon="plus" loading={pending} disabled={!email.trim()} onClick={() => void sendInvite()}>Create invite link</Button>
        </div> : <p className="panel-note">Workspace admins and owners can invite members.</p>}
        {inviteLink ? <div className="invite-link-box"><div><strong>Invite link ready</strong><span className="mono break-all">{inviteLink}</span></div><CopyButton value={inviteLink} label="Copy link" /></div> : null}
        {error ? <div className="error-block" role="alert">{error}</div> : null}
      </Panel>

      <Panel>
        <SectionHeader title="Pending invitations" description="Links can be revoked before they are accepted." />
        {invites.error ? <ErrorBlock compact message={invites.error} onRetry={invites.reload} /> : invites.loading ? <p className="panel-note">Loading invitations…</p> : invites.data?.length ? <div className="table-wrap"><table className="data"><thead><tr><th>Email</th><th>Role</th><th>Status</th><th>Expires</th><th /></tr></thead><tbody>{invites.data.map((invite) => <tr key={invite.id}><td>{invite.email}</td><td>{statusLabel(invite.role)}</td><td><Pill tone={invite.status === 'pending' ? 'warning' : 'neutral'}>{statusLabel(invite.status)}</Pill></td><td className="muted">{formatDateTime(invite.expires_at)}</td><td className="num">{canManage && invite.status === 'pending' ? <Button size="sm" variant="danger-ghost" onClick={() => void revokeInvite(invite)}>Revoke</Button> : null}</td></tr>)}</tbody></table></div> : <p className="chart-empty">No invitations have been created.</p>}
      </Panel>
    </div>
  )
}

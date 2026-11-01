import { useState } from 'react'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthProvider'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Button, Field, Input, Textarea } from './ui'

export function ProjectOnboarding() {
  const { user, logout } = useAuth()
  const { workspace, createProject } = useWorkspace()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    if (!name.trim()) {
      setError('Give the project a name.')
      return
    }
    setPending(true)
    setError(null)
    try {
      await createProject({ name: name.trim(), description: description.trim() || undefined })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="onboarding-shell">
      <div className="onboarding-card">
        <div className="brand" style={{ padding: 0, height: 28 }}>
          <span className="logo-mark" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </span>
          <span className="brand-name">Atlas</span>
        </div>
        <h1>Create the first project in {workspace?.name ?? 'your workspace'}</h1>
        <p>
          A project holds the datasets, training runs, registered models and deployments for one
          prediction problem. You can create more projects later.
        </p>
        <div className="stack">
          <Field label="Project name" htmlFor="onboarding-project-name">
            <Input
              id="onboarding-project-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Customer churn"
              maxLength={120}
              autoFocus
            />
          </Field>
          <Field label="Description" htmlFor="onboarding-project-description" hint="Optional.">
            <Textarea
              id="onboarding-project-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What will this project predict?"
              rows={3}
            />
          </Field>
          {error ? <div className="error-block is-compact">{error}</div> : null}
          <div className="form-actions" style={{ marginTop: 4 }}>
            <Button variant="ghost" onClick={logout}>
              Sign out
            </Button>
            <Button variant="primary" loading={pending} onClick={submit}>
              Create project
            </Button>
          </div>
          {user ? <p className="fine-print">Signed in as {user.email}</p> : null}
        </div>
      </div>
    </div>
  )
}

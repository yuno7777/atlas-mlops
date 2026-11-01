import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Button, Field, Input, Modal, Textarea } from './ui'
import { useToast } from './ToastProvider'

export function ProjectCreateDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { createProject } = useWorkspace()
  const toast = useToast()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setName('')
      setDescription('')
      setError(null)
    }
  }, [open])

  const submit = async () => {
    if (!name.trim()) {
      setError('Give the project a name.')
      return
    }
    setPending(true)
    setError(null)
    try {
      await createProject({
        name: name.trim(),
        description: description.trim() || undefined,
      })
      toast.success('Project created.')
      onClose()
      navigate('/overview')
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New project"
      description="Projects group datasets, training runs, registered models and deployments."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button variant="primary" loading={pending} onClick={submit}>
            Create project
          </Button>
        </>
      }
    >
      <div className="stack">
        <Field label="Project name" htmlFor="project-name">
          <Input
            id="project-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Customer churn"
            maxLength={120}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void submit()
            }}
          />
        </Field>
        <Field label="Description" htmlFor="project-description" hint="Optional. What does this project predict?">
          <Textarea
            id="project-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Churn propensity for the subscription customer base."
            maxLength={2000}
            rows={3}
          />
        </Field>
        {error ? <div className="error-block is-compact">{error}</div> : null}
      </div>
    </Modal>
  )
}

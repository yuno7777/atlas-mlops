import { useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../api/client'
import type { DatasetVersion } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { formatBytes } from '../lib/format'
import { Button, Field, Input, Modal, Textarea } from './ui'
import { Icon } from './Icon'

const ACCEPT = '.csv,.json,.parquet'

export function DatasetUploadDialog({
  open,
  onClose,
  datasetId,
  onUploaded,
}: {
  open: boolean
  onClose: () => void
  datasetId?: string
  onUploaded: (version: DatasetVersion) => void
}) {
  const { project } = useWorkspace()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    setName('')
    setDescription('')
    setFile(null)
    setError(null)
    setDragging(false)
  }, [open])

  const chooseFile = (next: File | null) => {
    if (!next) return
    const extension = next.name.slice(next.name.lastIndexOf('.')).toLowerCase()
    if (!ACCEPT.split(',').includes(extension)) {
      setError('Use a CSV, JSON or Parquet file.')
      return
    }
    setError(null)
    setFile(next)
  }

  const submit = async () => {
    if (!datasetId && !name.trim()) {
      setError('Give the dataset a name.')
      return
    }
    if (!file) {
      setError('Choose a file to upload.')
      return
    }
    setPending(true)
    setError(null)
    const form = new FormData()
    form.append('file', file)
    if (datasetId) {
      try {
        const version = await api.upload<DatasetVersion>(`/datasets/${datasetId}/versions`, form)
        onUploaded(version)
        onClose()
      } catch (caught) {
        setError(errorMessage(caught))
      } finally {
        setPending(false)
      }
      return
    }
    if (!project) {
      setError('Select a project before uploading.')
      setPending(false)
      return
    }
    form.append('project_id', project.id)
    form.append('name', name.trim())
    if (description.trim()) form.append('description', description.trim())
    try {
      const version = await api.upload<DatasetVersion>('/datasets', form)
      onUploaded(version)
      onClose()
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
      title={datasetId ? 'Add a dataset version' : 'Upload a dataset'}
      description={
        datasetId
          ? 'The new file becomes the next version. Earlier versions stay available for training and downloads.'
          : 'Upload a tabular file to this project. Atlas profiles it on ingest and stores it as version 1.'
      }
      width={580}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button variant="primary" loading={pending} onClick={submit}>
            {pending ? 'Uploading…' : datasetId ? 'Add version' : 'Upload dataset'}
          </Button>
        </>
      }
    >
      <div className="form-stack">
        {!datasetId ? (
          <>
            <Field label="Dataset name" htmlFor="upload-dataset-name">
              <Input
                id="upload-dataset-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Customer churn"
                maxLength={120}
              />
            </Field>
            <Field label="Description" htmlFor="upload-dataset-description" hint="Optional.">
              <Textarea
                id="upload-dataset-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What does one row represent?"
                rows={2}
                maxLength={1000}
              />
            </Field>
          </>
        ) : null}

        <div className="field">
          <span className="field-label">File</span>
          <button
            type="button"
            className={`dropzone ${dragging ? 'is-dragging' : ''} ${file ? 'has-file' : ''}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              chooseFile(event.dataTransfer.files?.[0] ?? null)
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              hidden
              onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
            />
            {file ? (
              <>
                <Icon name="file" size={20} />
                <span className="dropzone-title">{file.name}</span>
                <span className="dropzone-hint">{formatBytes(file.size)} · click to replace</span>
              </>
            ) : (
              <>
                <Icon name="upload" size={20} />
                <span className="dropzone-title">Drop a file here or click to browse</span>
                <span className="dropzone-hint">CSV, JSON or Parquet</span>
              </>
            )}
          </button>
          <p className="field-hint">
            CSV files must be UTF-8. The first row should contain column names.
          </p>
        </div>
        {error ? <div className="error-block is-compact">{error}</div> : null}
      </div>
    </Modal>
  )
}

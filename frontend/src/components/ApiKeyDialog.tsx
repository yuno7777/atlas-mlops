import { CopyButton, Modal } from './ui'
import { Icon } from './Icon'

export function ApiKeyDialog({
  open,
  apiKey,
  deploymentName,
  endpoint,
  onClose,
}: {
  open: boolean
  apiKey: string
  deploymentName: string
  endpoint: string
  onClose: () => void
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="API key created"
      description={`Use this key to call ${deploymentName}. Treat it like a password.`}
      width={600}
      footer={
        <button type="button" className="btn btn-primary" onClick={onClose}>
          I have stored this key
        </button>
      }
    >
      <div className="stack-gap-16">
        <div className="inline-notice inline-notice-warning">
          <Icon name="alert-triangle" size={16} />
          <span>
            This is the only time the full key is shown. Store it in a secret manager now.
          </span>
        </div>
        <div className="api-key-reveal">
          <code className="mono">{apiKey}</code>
          <CopyButton value={apiKey} label="Copy key" />
        </div>
        <div>
          <span className="field-label">Endpoint</span>
          <div className="code-line">
            <code className="mono">POST {endpoint}</code>
            <CopyButton value={endpoint} iconOnly />
          </div>
        </div>
        <pre className="code-block">{`curl -X POST "${endpoint}" \\
  -H "X-API-Key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{"records":[{"feature_name": 0.0}]}'`}</pre>
      </div>
    </Modal>
  )
}

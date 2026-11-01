import { Link } from 'react-router-dom'
import { useApi, useDocumentTitle } from '../api/hooks'
import type { LineageNode, LineageResponse } from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Icon } from '../components/Icon'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Panel, Pill } from '../components/ui'

const stages: { kind: LineageNode['kind']; label: string }[] = [
  { kind: 'dataset', label: 'Dataset versions' },
  { kind: 'training_job', label: 'Training jobs' },
  { kind: 'experiment', label: 'Experiments' },
  { kind: 'model_version', label: 'Model versions' },
  { kind: 'deployment', label: 'Deployments' },
]

export function LineagePage() {
  useDocumentTitle('Lineage')
  const { project } = useWorkspace()
  const lineage = useApi<LineageResponse>(
    project ? `/projects/${project.id}/lineage` : null,
  )
  const edges = lineage.data?.edges ?? []

  return (
    <>
      <PageHeader
        eyebrow="Project graph"
        title="Lineage"
        description="Trace each deployed model back through its registered version, experiment, training job, and dataset."
      />
      {!project ? (
        <Panel><EmptyState compact icon="git-branch" title="Choose a project" description="Project lineage appears after you select a project." /></Panel>
      ) : lineage.error ? (
        <ErrorBlock message={lineage.error} onRetry={lineage.reload} />
      ) : lineage.loading ? (
        <LoadingBlock rows={6} />
      ) : lineage.data?.nodes.length ? (
        <Panel className="lineage-panel">
          <div className="lineage-summary">
            <span>{project.name}</span>
            <span className="muted">{lineage.data.nodes.length} records · {edges.length} relationships</span>
          </div>
          <div className="lineage-columns">
            {stages.map((stage, index) => {
              const nodes = lineage.data?.nodes.filter((node) => node.kind === stage.kind) ?? []
              return (
                <section className="lineage-column" key={stage.kind} aria-label={stage.label}>
                  <div className="lineage-column-heading">
                    <span>{stage.label}</span>
                    <Pill tone="neutral">{nodes.length}</Pill>
                  </div>
                  {nodes.length ? nodes.map((node) => {
                    const incoming = edges.filter((edge) => edge.target === node.id)
                    const outgoing = edges.filter((edge) => edge.source === node.id)
                    const content = (
                      <>
                        <strong>{node.label}</strong>
                        {node.subtitle ? <span className="lineage-subtitle">{node.subtitle}</span> : null}
                        <span className="lineage-relations">
                          <span>{incoming.length} upstream</span>
                          <Icon name="arrow-right" size={12} />
                          <span>{outgoing.length} downstream</span>
                        </span>
                      </>
                    )
                    return node.href ? (
                      <Link className="lineage-node" to={node.href} key={node.id}>
                        {content}
                      </Link>
                    ) : (
                      <div className="lineage-node" key={node.id}>{content}</div>
                    )
                  }) : <p className="lineage-empty">No records</p>}
                  {index < stages.length - 1 ? <Icon className="lineage-stage-arrow" name="arrow-right" size={16} /> : null}
                </section>
              )
            })}
          </div>
          <details className="lineage-relationships">
            <summary>Relationship list</summary>
            <ul>
              {edges.map((edge, index) => {
                const source = lineage.data?.nodes.find((node) => node.id === edge.source)
                const target = lineage.data?.nodes.find((node) => node.id === edge.target)
                return <li key={`${edge.source}-${edge.target}-${index}`}><span>{source?.label ?? edge.source}</span><span className="muted">{edge.label ?? 'links to'}</span><span>{target?.label ?? edge.target}</span></li>
              })}
            </ul>
          </details>
        </Panel>
      ) : (
        <Panel><EmptyState compact icon="git-branch" title="No lineage yet" description="Upload data and complete a training run to build the project graph." /></Panel>
      )}
      {lineage.data && !lineage.loading ? <p className="panel-note">Statuses reflect the records in the selected project. Open any node to inspect its source record.</p> : null}
    </>
  )
}

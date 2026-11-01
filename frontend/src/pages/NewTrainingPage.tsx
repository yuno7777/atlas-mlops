import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import { useApi, useDocumentTitle } from '../api/hooks'
import type {
  Algorithm,
  DatasetSummary,
  DatasetVersion,
  DatasetVersionSummary,
  Hyperparameter,
  Page,
  TrainingJobDetail,
} from '../api/types'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { Icon } from '../components/Icon'
import { useToast } from '../components/ToastProvider'
import {
  Button,
  Checkbox,
  EmptyState,
  ErrorBlock,
  Field,
  Input,
  LinkButton,
  LoadingBlock,
  PageHeader,
  Panel,
  Pill,
  Select,
  Toggle,
} from '../components/ui'
import { formatNumber, titleCase } from '../lib/format'

type ProblemType = 'classification' | 'regression' | 'clustering'

interface AlgorithmChoice {
  algorithm: string
  hyperparameters: Record<string, unknown>
}

interface TrainingRequest {
  project_id: string
  dataset_version_id: string
  name?: string
  problem_type: ProblemType
  target_column: string | null
  feature_columns: string[] | null
  algorithms: AlgorithmChoice[]
  test_size: number
  random_seed: number
  cv_folds: number
  register_model_name?: string
}

const PROBLEMS: { id: ProblemType; title: string; description: string }[] = [
  {
    id: 'classification',
    title: 'Classification',
    description: 'Predict a discrete label, such as churn, fraud or a segment.',
  },
  {
    id: 'regression',
    title: 'Regression',
    description: 'Predict a continuous number, such as revenue or demand.',
  },
  {
    id: 'clustering',
    title: 'Clustering',
    description: 'Group rows without a target column using unsupervised algorithms.',
  },
]

const STEPS = ['Data', 'Algorithms', 'Review'] as const

export function NewTrainingPage() {
  useDocumentTitle('New training run')
  const { project } = useWorkspace()
  const navigate = useNavigate()
  const toast = useToast()

  const [step, setStep] = useState(0)
  const [datasetChoice, setDatasetChoice] = useState('')
  const [versionChoice, setVersionChoice] = useState('')
  const [problemType, setProblemType] = useState<ProblemType | null>(null)
  const [target, setTarget] = useState('')
  const [allFeatures, setAllFeatures] = useState(true)
  const [features, setFeatures] = useState<string[]>([])
  const [selectedAlgorithms, setSelectedAlgorithms] = useState<AlgorithmChoice[]>([])
  const [runName, setRunName] = useState('')
  const [testSize, setTestSize] = useState(0.2)
  const [randomSeed, setRandomSeed] = useState(42)
  const [cvFolds, setCvFolds] = useState(0)
  const [registerName, setRegisterName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const datasets = useApi<Page<DatasetSummary>>(project ? '/datasets' : null, {
    project_id: project?.id,
    page_size: 100,
  })
  const versions = useApi<DatasetVersionSummary[]>(
    datasetChoice ? `/datasets/${datasetChoice}/versions` : null,
  )
  const versionDetail = useApi<DatasetVersion>(
    versionChoice ? `/dataset-versions/${versionChoice}` : null,
  )
  const algorithms = useApi<Algorithm[]>(problemType ? '/algorithms' : null, {
    problem_type: problemType ?? undefined,
  })

  useEffect(() => {
    if (!versions.data?.length) return
    if (versionChoice && versions.data.some((version) => version.id === versionChoice)) return
    setVersionChoice(versions.data[0].id)
  }, [versions.data, versionChoice])

  const targetSuggestions = versionDetail.data?.validation.target_suggestions ?? []
  const selectedDataset = datasets.data?.items.find((item) => item.id === datasetChoice)
  const selectedVersionSummary = versions.data?.find((item) => item.id === versionChoice)
  const selectedAlgorithmsData = useMemo(
    () =>
      selectedAlgorithms
        .map((choice) => algorithms.data?.find((item) => item.id === choice.algorithm))
        .filter((item): item is Algorithm => Boolean(item)),
    [selectedAlgorithms, algorithms.data],
  )
  const supportsCv = selectedAlgorithmsData.some((algorithm) => algorithm.supports_cv)

  const chooseDataset = (id: string) => {
    setDatasetChoice(id)
    setVersionChoice('')
    setTarget('')
    setFeatures([])
  }

  const chooseProblem = (next: ProblemType) => {
    setProblemType(next)
    setSelectedAlgorithms([])
    if (next === 'clustering') setTarget('')
  }

  const toggleAlgorithm = (algorithm: Algorithm) => {
    setSelectedAlgorithms((current) => {
      const existing = current.find((choice) => choice.algorithm === algorithm.id)
      if (existing) return current.filter((choice) => choice.algorithm !== algorithm.id)
      if (current.length >= 10) return current
      const defaults: Record<string, unknown> = {}
      for (const parameter of algorithm.hyperparameters) defaults[parameter.name] = parameter.default
      return [...current, { algorithm: algorithm.id, hyperparameters: defaults }]
    })
  }

  const updateHyperparameter = (algorithmId: string, name: string, value: unknown) => {
    setSelectedAlgorithms((current) =>
      current.map((choice) =>
        choice.algorithm === algorithmId
          ? { ...choice, hyperparameters: { ...choice.hyperparameters, [name]: value } }
          : choice,
      ),
    )
  }

  const validateStep = (targetStep: number): string | null => {
    if (targetStep === 0) {
      if (!datasetChoice) return 'Choose a dataset.'
      if (!versionChoice) return 'Choose a dataset version.'
      if (!problemType) return 'Choose a problem type.'
      if (problemType !== 'clustering' && !target) return 'Choose a target column.'
      if (!allFeatures && features.length === 0) return 'Select at least one feature column.'
    }
    if (targetStep === 1 && selectedAlgorithms.length === 0) {
      return 'Select at least one algorithm.'
    }
    if (targetStep === 2) {
      if (!Number.isFinite(testSize) || testSize < 0.1 || testSize > 0.4) {
        return 'Test size must be between 0.1 and 0.4.'
      }
      if (supportsCv && (cvFolds < 0 || cvFolds > 10)) {
        return 'Cross-validation folds must be between 0 and 10.'
      }
    }
    return null
  }

  const next = () => {
    const message = validateStep(step)
    if (message) {
      setError(message)
      return
    }
    setError(null)
    setStep((current) => Math.min(2, current + 1))
  }

  const submit = async () => {
    if (!project) return
    for (let index = 0; index <= 2; index += 1) {
      const message = validateStep(index)
      if (message) {
        setStep(index)
        setError(message)
        return
      }
    }
    setPending(true)
    setError(null)
    const payload: TrainingRequest = {
      project_id: project.id,
      dataset_version_id: versionChoice,
      name: runName.trim() || undefined,
      problem_type: problemType as ProblemType,
      target_column: problemType === 'clustering' ? null : target || null,
      feature_columns: allFeatures ? null : features,
      algorithms: selectedAlgorithms,
      test_size: testSize,
      random_seed: randomSeed,
      cv_folds: supportsCv ? cvFolds : 0,
      register_model_name: registerName.trim() || undefined,
    }
    try {
      const job = await api.post<TrainingJobDetail>('/training-jobs', payload)
      toast.success('Training run queued.')
      navigate(`/training/${job.id}`)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  if (!datasets.loading && !datasets.data?.items.length) {
    return (
      <>
        <PageHeader
          backTo="/training"
          backLabel="Training"
          title="New training run"
          description="A training run needs a dataset version first."
        />
        <EmptyState
          icon="database"
          title="Upload a dataset before training"
          description="Atlas trains from a versioned tabular dataset. Upload one, then return here to configure algorithms."
          action={
            <LinkButton to="/datasets?upload=1" variant="primary" icon="upload">
              Upload dataset
            </LinkButton>
          }
        />
      </>
    )
  }

  return (
    <>
      <PageHeader
        backTo="/training"
        backLabel="Training"
        eyebrow="New run"
        title="Train a model"
        description="Pick a dataset version, choose one or more algorithms, then review the configuration before queueing the run."
      />

      <div className="wizard-stepper" aria-label="Training setup steps">
        {STEPS.map((label, index) => (
          <button
            key={label}
            type="button"
            className={`wizard-step ${index === step ? 'is-current' : ''} ${index < step ? 'is-done' : ''}`}
            onClick={() => {
              if (index > step) {
                const message = validateStep(step)
                if (message) {
                  setError(message)
                  return
                }
              }
              setError(null)
              setStep(index)
            }}
          >
            <span className="wizard-step-number">
              {index < step ? <Icon name="check" size={12} /> : index + 1}
            </span>
            <span>{label}</span>
          </button>
        ))}
      </div>

      <div className="wizard-layout">
        <div className="wizard-main">
          {step === 0 ? (
            <div className="stack-gap-20">
              <Panel>
                <div className="section-header">
                  <div>
                    <h2>Dataset</h2>
                    <p className="section-description">
                      Choose the data this run trains on. Every version is immutable.
                    </p>
                  </div>
                </div>
                <div className="form-grid-2">
                  <Field label="Dataset" htmlFor="training-dataset">
                    <Select
                      id="training-dataset"
                      value={datasetChoice}
                      onChange={(event) => chooseDataset(event.target.value)}
                    >
                      <option value="">Select a dataset</option>
                      {(datasets.data?.items ?? []).map((dataset) => (
                        <option key={dataset.id} value={dataset.id}>
                          {dataset.name} · v{dataset.latest_version}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Version" htmlFor="training-version">
                    <Select
                      id="training-version"
                      value={versionChoice}
                      onChange={(event) => {
                        setVersionChoice(event.target.value)
                        setTarget('')
                        setFeatures([])
                      }}
                      disabled={!datasetChoice || !versions.data?.length}
                    >
                      {!versions.data?.length ? <option value="">No versions</option> : null}
                      {(versions.data ?? []).map((version) => (
                        <option key={version.id} value={version.id}>
                          v{version.version} · {formatNumber(version.row_count)} rows
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
                {selectedDataset && selectedVersionSummary ? (
                  <div className="selection-meta">
                    <Pill tone="neutral">
                      {formatNumber(selectedVersionSummary.row_count)} rows ×{' '}
                      {formatNumber(selectedVersionSummary.column_count)} columns
                    </Pill>
                    <span className="muted">{selectedVersionSummary.original_filename}</span>
                  </div>
                ) : null}
              </Panel>

              <Panel>
                <div className="section-header">
                  <div>
                    <h2>Problem type</h2>
                    <p className="section-description">
                      This determines the metrics, preprocessing and available algorithms.
                    </p>
                  </div>
                </div>
                <div className="problem-grid">
                  {PROBLEMS.map((problem) => (
                    <button
                      key={problem.id}
                      type="button"
                      className={`problem-card ${problemType === problem.id ? 'is-selected' : ''}`}
                      onClick={() => chooseProblem(problem.id)}
                    >
                      <Icon
                        name={
                          problem.id === 'classification'
                            ? 'target'
                            : problem.id === 'regression'
                              ? 'activity'
                              : 'layers'
                        }
                        size={18}
                      />
                      <strong>{problem.title}</strong>
                      <span>{problem.description}</span>
                    </button>
                  ))}
                </div>
              </Panel>

              {problemType ? (
                <Panel>
                  <div className="section-header">
                    <div>
                      <h2>Columns</h2>
                      <p className="section-description">
                        {problemType === 'clustering'
                          ? 'Choose which columns the clustering algorithm should use.'
                          : 'Choose the target to predict and the feature columns used as inputs.'}
                      </p>
                    </div>
                  </div>
                  {versionDetail.error ? (
                    <ErrorBlock compact message={versionDetail.error} onRetry={versionDetail.reload} />
                  ) : !versionDetail.data ? (
                    <LoadingBlock rows={4} />
                  ) : (
                    <div className="stack">
                      {problemType !== 'clustering' ? (
                        <>
                          <Field
                            label="Target column"
                            htmlFor="training-target"
                            hint="The column the model should predict."
                          >
                            <Select
                              id="training-target"
                              value={target}
                              onChange={(event) => {
                                const nextTarget = event.target.value
                                setTarget(nextTarget)
                                setFeatures((current) =>
                                  current.filter((column) => column !== nextTarget),
                                )
                              }}
                            >
                              <option value="">Select a target</option>
                              {versionDetail.data.schema.map((column) => (
                                <option key={column.name} value={column.name}>
                                  {column.name} · {column.kind}
                                </option>
                              ))}
                            </Select>
                          </Field>
                          {targetSuggestions.length ? (
                            <div className="suggestion-row">
                              <span className="field-label">Suggestions</span>
                              {targetSuggestions.map((suggestion) => (
                                <button
                                  key={suggestion.column}
                                  type="button"
                                  className={`suggestion-chip ${target === suggestion.column ? 'is-selected' : ''}`}
                                  onClick={() => {
                                    setTarget(suggestion.column)
                                    setProblemType(suggestion.task)
                                  }}
                                >
                                  <Icon name="target" size={12} />
                                  {suggestion.column}
                                  <span>{suggestion.task}</span>
                                </button>
                              ))}
                            </div>
                          ) : null}
                        </>
                      ) : null}

                      <div className="feature-choice">
                        <Checkbox
                          label="Use all available columns as features"
                          checked={allFeatures}
                          onChange={setAllFeatures}
                        />
                        {allFeatures ? (
                          <p className="field-hint" style={{ margin: '4px 0 0 26px' }}>
                            Target and unusable columns are excluded automatically.
                          </p>
                        ) : (
                          <div className="feature-grid">
                            {versionDetail.data.schema
                              .filter((column) => column.name !== target)
                              .map((column) => (
                                <Checkbox
                                  key={column.name}
                                  checked={features.includes(column.name)}
                                  onChange={(checked) =>
                                    setFeatures((current) =>
                                      checked
                                        ? [...current, column.name]
                                        : current.filter((name) => name !== column.name),
                                    )
                                  }
                                  label={
                                    <>
                                      <span className="mono">{column.name}</span>
                                      <span className="cell-sub">{column.kind}</span>
                                    </>
                                  }
                                />
                              ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </Panel>
              ) : null}
            </div>
          ) : null}

          {step === 1 ? (
            <div className="stack-gap-20">
              <Panel>
                <div className="section-header">
                  <div>
                    <h2>Algorithms</h2>
                    <p className="section-description">
                      Select up to ten algorithms. Each one becomes a separate experiment with the
                      same split and seed.
                    </p>
                  </div>
                  <Pill tone="neutral">{selectedAlgorithms.length} selected</Pill>
                </div>
                {algorithms.error ? (
                  <ErrorBlock message={algorithms.error} onRetry={algorithms.reload} />
                ) : algorithms.loading ? (
                  <LoadingBlock rows={6} />
                ) : (
                  <div className="algorithm-grid">
                    {(algorithms.data ?? []).map((algorithm) => {
                      const selected = selectedAlgorithms.some(
                        (choice) => choice.algorithm === algorithm.id,
                      )
                      return (
                        <button
                          key={algorithm.id}
                          type="button"
                          className={`algorithm-card ${selected ? 'is-selected' : ''}`}
                          onClick={() => toggleAlgorithm(algorithm)}
                          aria-pressed={selected}
                        >
                          <div className="space-between">
                            <strong>{algorithm.label}</strong>
                            <span className="algorithm-check" aria-hidden="true">
                              {selected ? <Icon name="check" size={12} /> : null}
                            </span>
                          </div>
                          <span className="algorithm-description">{algorithm.description}</span>
                          <span className="algorithm-meta">
                            {algorithm.framework}
                            {algorithm.supports_cv ? ' · cross-validation' : ''}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                )}
              </Panel>

              {selectedAlgorithmsData.map((algorithm) => {
                const choice = selectedAlgorithms.find((item) => item.algorithm === algorithm.id)
                if (!choice) return null
                return (
                  <Panel key={algorithm.id}>
                    <div className="section-header">
                      <div>
                        <h2>{algorithm.label}</h2>
                        <p className="section-description">Hyperparameters for this experiment.</p>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setSelectedAlgorithms((current) =>
                            current.filter((item) => item.algorithm !== algorithm.id),
                          )
                        }
                      >
                        Remove
                      </Button>
                    </div>
                    <div className="form-grid-2">
                      {algorithm.hyperparameters.map((parameter) => (
                        <HyperparameterField
                          key={parameter.name}
                          parameter={parameter}
                          value={choice.hyperparameters[parameter.name]}
                          onChange={(value) =>
                            updateHyperparameter(algorithm.id, parameter.name, value)
                          }
                        />
                      ))}
                    </div>
                  </Panel>
                )
              })}
            </div>
          ) : null}

          {step === 2 ? (
            <div className="stack-gap-20">
              <Panel>
                <div className="section-header">
                  <div>
                    <h2>Run configuration</h2>
                    <p className="section-description">
                      These settings apply to every algorithm in this training job.
                    </p>
                  </div>
                </div>
                <div className="form-grid-2">
                  <Field label="Run name" htmlFor="training-name" hint="Optional. Generated if left empty.">
                    <Input
                      id="training-name"
                      value={runName}
                      onChange={(event) => setRunName(event.target.value)}
                      placeholder="Churn experiment · November"
                      maxLength={160}
                    />
                  </Field>
                  <Field
                    label="Register model name"
                    htmlFor="training-register"
                    hint="Optional. Register the best experiment automatically."
                  >
                    <Input
                      id="training-register"
                      value={registerName}
                      onChange={(event) => setRegisterName(event.target.value)}
                      placeholder="customer-churn"
                      maxLength={120}
                    />
                  </Field>
                  <Field label="Test split" htmlFor="training-test-size" hint="Between 10% and 40%.">
                    <div className="input-with-suffix">
                      <Input
                        id="training-test-size"
                        type="number"
                        min={10}
                        max={40}
                        step={5}
                        value={Math.round(testSize * 100)}
                        onChange={(event) => setTestSize(Number(event.target.value) / 100)}
                      />
                      <span>%</span>
                    </div>
                  </Field>
                  <Field label="Random seed" htmlFor="training-seed" hint="Makes the split reproducible.">
                    <Input
                      id="training-seed"
                      type="number"
                      min={0}
                      max={2147483647}
                      value={randomSeed}
                      onChange={(event) => setRandomSeed(Number(event.target.value))}
                    />
                  </Field>
                  {supportsCv ? (
                    <Field
                      label="Cross-validation folds"
                      htmlFor="training-cv"
                      hint="0 disables cross-validation. Uses up to 10 folds."
                    >
                      <Input
                        id="training-cv"
                        type="number"
                        min={0}
                        max={10}
                        value={cvFolds}
                        onChange={(event) => setCvFolds(Number(event.target.value))}
                      />
                    </Field>
                  ) : null}
                </div>
              </Panel>

              <Panel>
                <div className="section-header">
                  <div>
                    <h2>Review</h2>
                    <p className="section-description">
                      The job runs in the background. You can watch progress and logs on the job page.
                    </p>
                  </div>
                </div>
                <dl className="review-list">
                  <div>
                    <dt>Dataset</dt>
                    <dd>
                      {selectedDataset?.name ?? '—'}{' '}
                      {selectedVersionSummary ? `· v${selectedVersionSummary.version}` : ''}
                    </dd>
                  </div>
                  <div>
                    <dt>Problem</dt>
                    <dd>{problemType ? titleCase(problemType) : '—'}</dd>
                  </div>
                  <div>
                    <dt>Target</dt>
                    <dd className="mono">{problemType === 'clustering' ? 'None' : target || '—'}</dd>
                  </div>
                  <div>
                    <dt>Features</dt>
                    <dd>{allFeatures ? 'All available columns' : `${features.length} selected`}</dd>
                  </div>
                  <div>
                    <dt>Algorithms</dt>
                    <dd>{selectedAlgorithmsData.map((algorithm) => algorithm.label).join(', ')}</dd>
                  </div>
                  <div>
                    <dt>Split</dt>
                    <dd>
                      {Math.round((1 - testSize) * 100)}% train / {Math.round(testSize * 100)}% test
                    </dd>
                  </div>
                  <div>
                    <dt>Seed</dt>
                    <dd className="num">{randomSeed}</dd>
                  </div>
                  <div>
                    <dt>Cross-validation</dt>
                    <dd>{supportsCv && cvFolds > 0 ? `${cvFolds} folds` : 'Off'}</dd>
                  </div>
                </dl>
              </Panel>

              {registerName.trim() ? (
                <p className="panel-note">
                  After completion, the best experiment will be registered as{' '}
                  <strong>{registerName.trim()}</strong>. If the model name already exists, a new
                  version is added.
                </p>
              ) : null}
            </div>
          ) : null}

          {error ? <div className="error-block">{error}</div> : null}
        </div>

        <aside className="wizard-aside">
          <div className="wizard-summary">
            <div className="eyebrow-label">Run summary</div>
            <div className="wizard-summary-block">
              <span>Dataset</span>
              <strong>{selectedDataset?.name ?? 'Not selected'}</strong>
              <small>
                {selectedVersionSummary
                  ? `Version ${selectedVersionSummary.version} · ${formatNumber(selectedVersionSummary.row_count)} rows`
                  : 'Choose a version'}
              </small>
            </div>
            <div className="wizard-summary-block">
              <span>Setup</span>
              <strong>{problemType ? titleCase(problemType) : 'No problem type'}</strong>
              <small>
                {problemType === 'clustering'
                  ? 'Unsupervised'
                  : target
                    ? `Target: ${target}`
                    : 'Choose a target'}
              </small>
            </div>
            <div className="wizard-summary-block">
              <span>Algorithms</span>
              <strong>
                {selectedAlgorithmsData.length
                  ? `${selectedAlgorithmsData.length} selected`
                  : 'None selected'}
              </strong>
              <small>
                {selectedAlgorithmsData.map((algorithm) => algorithm.label).join(', ') || 'Select at least one'}
              </small>
            </div>
            <div className="wizard-actions">
              {step > 0 ? (
                <Button variant="ghost" onClick={() => setStep((current) => current - 1)}>
                  Back
                </Button>
              ) : null}
              {step < 2 ? (
                <Button variant="primary" onClick={next}>
                  Continue
                </Button>
              ) : (
                <Button variant="primary" loading={pending} onClick={() => void submit()}>
                  Start training
                </Button>
              )}
            </div>
          </div>
        </aside>
      </div>
    </>
  )
}

function HyperparameterField({
  parameter,
  value,
  onChange,
}: {
  parameter: Hyperparameter
  value: unknown
  onChange: (value: unknown) => void
}) {
  const id = `hp-${parameter.name}`
  if (parameter.type === 'bool') {
    return (
      <div className="field">
        <span className="field-label">{parameter.label}</span>
        <Toggle
          checked={Boolean(value)}
          onChange={onChange}
          label={parameter.label}
        />
        {parameter.description ? <p className="field-hint">{parameter.description}</p> : null}
      </div>
    )
  }
  if (parameter.type === 'choice') {
    return (
      <Field label={parameter.label} htmlFor={id} hint={parameter.description}>
        <Select
          id={id}
          value={String(value ?? '')}
          onChange={(event) => onChange(event.target.value)}
        >
          {(parameter.choices ?? []).map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))}
        </Select>
      </Field>
    )
  }
  return (
    <Field label={parameter.label} htmlFor={id} hint={parameter.description}>
      <Input
        id={id}
        type="number"
        value={value === null || value === undefined ? '' : String(value)}
        min={parameter.min ?? undefined}
        max={parameter.max ?? undefined}
        step={parameter.step ?? (parameter.type === 'int' ? 1 : 'any')}
        onChange={(event) => {
          const raw = event.target.value
          if (raw === '') {
            onChange(parameter.type === 'int' ? 0 : 0)
            return
          }
          onChange(Number(raw))
        }}
      />
    </Field>
  )
}

export type JsonObject = Record<string, unknown>
export type MetricMap = Record<string, number | null>

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface User {
  id: string
  email: string
  full_name: string
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface Workspace {
  id: string
  name: string
  slug: string
  role: string
  created_at: string
}

export interface Member {
  user_id: string
  email: string
  full_name: string
  role: string
  joined_at: string
}

export interface Project {
  id: string
  workspace_id: string
  name: string
  slug: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface Hyperparameter {
  name: string
  label: string
  type: 'int' | 'float' | 'choice' | 'bool'
  default: unknown
  min: number | null
  max: number | null
  step: number | null
  choices: string[] | null
  description: string
}

export interface Algorithm {
  id: string
  label: string
  problem_type: 'classification' | 'regression' | 'clustering'
  description: string
  framework: string
  supports_cv: boolean
  hyperparameters: Hyperparameter[]
}

export interface DatasetColumn {
  name: string
  dtype: string
  kind: string
  nullable: boolean
  unique_count: number | null
  sample_values: unknown[]
}

export interface NumericProfile {
  column: string
  count: number
  mean: number | null
  std: number | null
  min: number | null
  p25: number | null
  p50: number | null
  p75: number | null
  max: number | null
  zeros: number
  negatives: number
  outliers_iqr: number
  skew: number | null
}

export interface CategoryShare {
  value: string
  count: number
  percent: number
}

export interface CategoricalProfile {
  column: string
  unique: number
  top: CategoryShare[]
  sampled: boolean
  sample_size: number
}

export interface MissingColumn {
  column: string
  count: number
  percent: number
}

export interface DataProfile {
  rows: number
  columns: number
  memory_bytes: number
  sampled: boolean
  sample_size: number
  missing: {
    total_cells: number
    percent: number
    columns: MissingColumn[]
  }
  duplicates: { rows: number; percent: number }
  numeric: NumericProfile[]
  categorical: CategoricalProfile[]
  datetime: { column: string; min: string | null; max: string | null }[]
  constant_columns: string[]
  high_missing_columns: string[]
}

export interface TargetSuggestion {
  column: string
  task: 'classification' | 'regression'
  reason: string
  score: number
}

export interface ValidationCheck {
  name: string
  status: 'passed' | 'warning' | 'failed'
  message: string
}

export interface DatasetValidation {
  passed: boolean
  checks: ValidationCheck[]
  target_suggestions: TargetSuggestion[]
}

export interface DatasetVersion {
  id: string
  dataset_id: string
  version: number
  status: string
  original_filename: string
  content_type: string
  size_bytes: number
  row_count: number
  column_count: number
  checksum: string
  created_at: string
  schema: DatasetColumn[]
  profile: DataProfile
  validation: DatasetValidation
}

export interface DatasetVersionSummary {
  id: string
  dataset_id: string
  version: number
  status: string
  original_filename: string
  size_bytes: number
  row_count: number
  column_count: number
  created_at: string
}

export interface DatasetSummary {
  id: string
  project_id: string
  name: string
  description: string | null
  latest_version: number
  version_count: number
  latest_version_id: string | null
  row_count: number | null
  column_count: number | null
  size_bytes: number | null
  created_at: string
  updated_at: string
}

export interface DatasetDetail {
  dataset: DatasetSummary
  latest_version: DatasetVersion | null
  version_count: number
}

export interface PreviewResponse {
  columns: DatasetColumn[]
  rows: JsonObject[]
  total_rows: number
  returned: number
}

export interface TrainingJobSummary {
  id: string
  project_id: string
  name: string
  problem_type: string
  status: string
  progress: number
  status_message: string | null
  dataset_version_id: string
  dataset_name: string
  dataset_version: number
  target_column: string | null
  algorithm_count: number
  retrain_source_deployment_id: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
}

export interface TrainingJobDetail extends TrainingJobSummary {
  feature_columns: string[] | null
  algorithms: JsonObject[]
  config: JsonObject
  error_message: string | null
  cancel_requested: boolean
  experiments: ExperimentSummary[]
  created_by: string
}

export interface TrainingJobLog {
  id: number
  level: string
  message: string
  created_at: string
}

export interface TrainingJobLogs {
  items: TrainingJobLog[]
  last_id: number | null
}

export interface ExperimentSummary {
  id: string
  project_id: string
  training_job_id: string
  dataset_version_id: string
  dataset_name?: string | null
  dataset_version?: number | null
  name: string
  algorithm: string
  algorithm_label: string
  problem_type: string
  params: JsonObject
  metrics: MetricMap
  cv_metrics: JsonObject | null
  status: string
  error_message: string | null
  mlflow_run_id: string | null
  tracking_warning: string | null
  training_duration_seconds: number | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  registered_model_id?: string | null
  registered_model_name?: string | null
  registered_version?: number | null
  registered_stage?: string | null
  artifact_available?: boolean
}

export interface ReferenceFeature {
  kind: 'numeric' | 'categorical'
  categories?: Record<string, number>
  missing_rate?: number
  unique?: number
  mean?: number | null
  std?: number | null
  samples?: number[]
}

export interface ReferenceProfile {
  version: number
  problem_type: string
  trained_rows: number
  schema: { features: DatasetColumn[] }
  features: Record<string, ReferenceFeature>
  prediction_reference: JsonObject
  baseline_metrics: MetricMap
  dropped_columns: string[]
}

export interface ExperimentDetail extends ExperimentSummary {
  reference_profile: ReferenceProfile | null
  job_name?: string | null
}

export interface BestMetric {
  experiment_id: string
  value: number
  direction: string
}

export interface ExperimentCompare {
  problem_type: string
  metric_keys: string[]
  directions: Record<string, string>
  best: Record<string, BestMetric>
  experiments: ExperimentSummary[]
}

export interface ModelSummary {
  id: string
  project_id: string
  name: string
  description: string | null
  latest_version: number
  version_count: number
  created_at: string
  updated_at: string
  latest_stage?: string | null
  latest_metrics?: MetricMap | null
  latest_algorithm?: string | null
  production_version?: number | null
}

export interface ModelVersion {
  id: string
  registered_model_id: string
  registered_model_name?: string | null
  version: number
  experiment_id: string
  dataset_version_id: string
  algorithm: string
  framework: string
  stage: string
  metrics: MetricMap
  params: JsonObject
  artifact_sha256: string
  created_at: string
  created_by: string
  deployment_count: number
  problem_type?: string | null
  reference_feature_count: number
}

export interface ModelDetail extends ModelSummary {
  versions: ModelVersion[]
}

export interface VersionCompare {
  metric_keys: string[]
  directions: Record<string, string>
  best: Record<string, string>
  versions: ModelVersion[]
}

export interface MonitoringConfig {
  psi_threshold: number
  drift_share_threshold: number
  performance_degradation_threshold: number
  min_samples: number
  window_hours: number
  auto_retrain_on_drift: boolean
  auto_retrain_cooldown_hours: number
}

export interface DeploymentSummary {
  id: string
  project_id: string
  name: string
  status: string
  registered_model_id: string
  model_name: string
  model_version_id: string
  model_version: number
  algorithm: string
  stage: string
  api_key_prefix: string
  description: string | null
  last_request_at: string | null
  activated_at: string | null
  stopped_at: string | null
  created_at: string
  updated_at: string
  latest_monitoring_status?: string | null
  config: MonitoringConfig
}

export interface DeploymentRevision {
  id: string
  model_version_id: string
  version?: number | null
  activated_at: string
  deactivated_at: string | null
  reason: string
}

export interface DeploymentEvent {
  id: number
  level: string
  message: string
  details: JsonObject
  created_at: string
}

export interface DeploymentDetail extends DeploymentSummary {
  model_metrics: MetricMap
  model_params: JsonObject
  problem_type: string | null
  target_column: string | null
  dataset_name: string | null
  dataset_version: number | null
  revisions: DeploymentRevision[]
  events: DeploymentEvent[]
  model_version_created_at: string
}

export interface DeploymentCreated extends DeploymentDetail {
  api_key: string
}

export interface RotateKeyResponse {
  api_key: string
  api_key_prefix: string
}

export interface DeploymentHealth {
  deployment_id: string
  status: string
  healthy: boolean
  checks: Record<string, string | boolean | null>
  checked_at: string
}

export interface FeatureDrift {
  feature: string
  kind: string
  psi: number
  ks_statistic?: number | null
  ks_pvalue?: number | null
  drifted: boolean
  missing_rate: number
  reference_missing_rate?: number
}

export interface MonitoringDetails {
  data_drift?: {
    detected?: boolean
    drift_share?: number
    features?: FeatureDrift[]
  }
  prediction_drift?: { detected?: boolean; psi?: number }
  concept_drift?: { detected?: boolean; reason?: string; labels?: number }
  performance?: MetricMap | null
  drifted_features?: string[]
  reference_metrics?: MetricMap
}

export interface MonitoringResult {
  id: string
  deployment_id: string
  model_version_id: string
  status: string
  sample_count: number
  labeled_count: number
  data_drift_detected: boolean
  prediction_drift_detected: boolean
  concept_drift_detected: boolean
  drift_share: number
  psi_max: number
  ks_min_pvalue: number | null
  details: MonitoringDetails
  created_at: string
}

export interface TimeseriesPoint {
  bucket: string
  predictions: number
  failures: number
  avg_latency_ms: number
  p95_latency_ms: number
}

export interface Timeseries {
  deployment_id: string
  hours: number
  points: TimeseriesPoint[]
}

export interface PredictionLog {
  id: string
  deployment_id: string
  model_version_id: string
  request_id: string
  features: JsonObject | null
  prediction: unknown
  status: string
  error_message: string | null
  latency_ms: number
  actual: unknown
  actual_received_at: string | null
  created_at: string
}

export interface PredictionItem {
  prediction: unknown
  probabilities?: Record<string, number> | null
}

export interface PredictionResponse {
  request_id: string
  deployment_id: string
  model_version_id: string
  model_version: number
  predictions: PredictionItem[]
  latency_ms: number
  warnings: string[]
}

export interface FeedbackResponse {
  updated: number
  already_labeled: number
  not_found: number
}

export interface RetrainComparison {
  deployment_id: string
  incumbent: {
    model_version_id: string
    version: number
    algorithm: string
    metrics: MetricMap
  }
  candidates: ExperimentSummary[]
  metric_keys: string[]
  directions: Record<string, string>
  deltas: Record<string, Record<string, number>>
  recommended_experiment_id: string | null
  recommendation_reason: string
  latest_job_id: string | null
  latest_job_status: string | null
}

export interface TrainingActivityPoint {
  date: string
  completed: number
  failed: number
  running: number
  total: number
}

export interface PerformancePoint {
  date: string
  experiment_id: string
  name: string
  algorithm: string
  primary_metric: string
  value: number
  problem_type: string
}

export interface ModelPerformanceItem {
  algorithm: string
  algorithm_label: string
  runs: number
  primary_metric: string
  average: number
  best: number
}

export interface DeploymentHealthItem {
  id: string
  name: string
  status: string
  model_name: string
  model_version: number
  latest_monitoring_status: string | null
  last_request_at: string | null
  created_at: string
}

export interface RecentJobItem {
  id: string
  name: string
  status: string
  progress: number
  problem_type: string
  created_at: string
}

export interface RecentEventItem {
  id: number
  action: string
  resource_type: string
  resource_id: string | null
  details: JsonObject
  created_at: string
}

export interface LatestModelItem {
  id: string
  name: string
  version: number
  stage: string
  algorithm: string
  metrics: MetricMap
  created_at: string
}

export interface OverviewCounts {
  datasets: number
  dataset_versions: number
  experiments: number
  completed_experiments: number
  registered_models: number
  model_versions: number
  active_deployments: number
  training_jobs: number
  predictions_7d: number
}

export interface Overview {
  counts: OverviewCounts
  training_activity: TrainingActivityPoint[]
  experiment_performance: PerformancePoint[]
  model_performance: ModelPerformanceItem[]
  deployment_health: DeploymentHealthItem[]
  deployment_status_counts: Record<string, number>
  recent_jobs: RecentJobItem[]
  recent_events: RecentEventItem[]
  latest_models: LatestModelItem[]
  primary_metric: string | null
}

export interface AuditEvent {
  id: number
  action: string
  resource_type: string
  resource_id: string | null
  details: JsonObject
  user_email: string | null
  created_at: string
}

export interface SystemInfo {
  version: string
  environment: string
  execution_mode: string
  storage_backend: string
  mlflow_enabled: boolean
  mlflow_tracking_uri: string
  mlflow_reachable: boolean
  database: string
  monitoring_scheduler: boolean
  timestamp: string
}

export interface DatasetUploadResult {
  dataset: DatasetSummary
  version: DatasetVersion
}

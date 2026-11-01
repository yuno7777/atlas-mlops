# API Specification

Base URL: `/api/v1`  
OpenAPI: `GET /api/v1/openapi.json`, Swagger UI at `/api/v1/docs`, ReDoc at
`/api/v1/redoc`. Health probes live outside the versioned prefix: `/health`,
`/ready`, `/metrics`.

## Conventions

- JSON only except dataset upload/download (multipart/octet-stream).
- Auth: `Authorization: Bearer <jwt>` unless noted. External prediction calls may use
  `X-API-Key: <deployment key>`.
- Lists: `page` (default 1), `page_size` (default 20, max 100).
- Errors:
  ```json
  {"error": {"code": "validation_error", "message": "Human readable detail",
             "details": [{"field": "target_column", "message": "..."}],
             "request_id": "..."}}
  ```
  Codes: `authentication_required`, `invalid_credentials`, `forbidden`,
  `not_found`, `conflict`, `validation_error`, `rate_limited`,
  `payload_too_large`, `unsupported_media_type`, `service_unavailable`,
  `internal_error`.
- Created resources return `201`; async work returns `202`; deletes/`no content` use
  `204`.
- All timestamps are UTC ISO-8601.

## Meta

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness |
| GET | `/ready` | none | DB + storage readiness |
| GET | `/metrics` | none (network-scoped) | Prometheus text format |
| GET | `/api/v1/health` | none | API health with version |
| GET | `/api/v1/system/info` | JWT | Versions, execution mode, artifact backend, MLflow status |

## Authentication

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Create user + personal workspace |
| POST | `/auth/login` | Exchange credentials for JWT |
| GET | `/auth/me` | Current profile |
| PATCH | `/auth/me` | Update full name |
| POST | `/auth/change-password` | Rotate password |

`POST /auth/register` → `201`

```json
{"email": "engineer@example.com", "password": "correct-horse-staple", "full_name": "Engineer", "workspace_name": "Acme ML"}
```

Login response:

```json
{"access_token": "eyJ...", "token_type": "bearer", "expires_in": 43200,
 "user": {"id":"...","email":"...","full_name":"...","created_at":"..."}}
```

## Workspaces and Projects

| Method | Path | Purpose |
|---|---|---|
| GET | `/workspaces` | Workspaces for current user, with role |
| GET | `/workspaces/{id}/members` | Members (name, email, role) |
| GET | `/workspaces/{id}/projects` | Projects in workspace |
| POST | `/workspaces/{id}/projects` | Create project (`admin`+) |
| GET | `/projects/{id}` | Project detail |
| GET | `/projects/{id}/overview` | Dashboard aggregate |
| GET | `/projects/{id}/audit-events` | Recent audit trail |

## Datasets

| Method | Path | Purpose |
|---|---|---|
| POST | `/datasets` | Upload first version (multipart) |
| GET | `/datasets` | List (`project_id`, `search`, pagination) |
| GET | `/datasets/{id}` | Dataset + latest version summary |
| POST | `/datasets/{id}/versions` | Upload new version (multipart) |
| GET | `/datasets/{id}/versions` | Version history |
| GET | `/dataset-versions/{id}` | Full version detail incl. profile |
| GET | `/dataset-versions/{id}/preview` | `limit` rows (1–100) |
| GET | `/dataset-versions/{id}/download` | Original file stream |
| DELETE | `/datasets/{id}` | Delete dataset + versions + artifacts (no dependents) |

Multipart fields: `project_id`, `name` (1–120), `description`, `file`.

Validation: extensions `.csv`, `.parquet`, `.json`; MIME allowlist (CSV, Parquet,
JSON, octet-stream); size ≤ `MAX_UPLOAD_MB`; ≥1 column; ≥1 row; duplicate SHA-256
within a dataset is rejected with `409`.

Version detail (abridged):

```json
{
  "id": "...", "dataset_id": "...", "version": 2, "status": "ready",
  "original_filename": "churn.csv", "size_bytes": 182401, "row_count": 2000,
  "column_count": 21, "checksum": "sha256...", "created_at": "...",
  "schema": [{"name":"tenure","dtype":"int64","kind":"numeric","nullable":false}],
  "profile": {
    "missing": {"total": 0, "columns": [{"column":"age","count":3,"percent":0.15}]},
    "duplicates": {"rows": 0, "percent": 0.0},
    "numeric": [{"column":"age","mean":41.2,"std":9.4,"min":18,"p25":34,"p50":41,
                 "p75":48,"max":80,"zeros":0,"outliers_iqr":12}],
    "categorical": [{"column":"contract","unique":3,"top":[{"value":"monthly","count":1100,"percent":55.0}]}]
  },
  "validation": {"passed": true, "checks": [{"name":"row_count","status":"passed","message":"2000 rows"}]},
  "target_suggestions": [{"column":"churn","reason":"binary categorical"}]
}
```

## Training

| Method | Path | Purpose |
|---|---|---|
| GET | `/algorithms` | Catalog (`problem_type` filter) |
| POST | `/training-jobs` | Create and enqueue a job |
| GET | `/training-jobs` | List with filters |
| GET | `/training-jobs/{id}` | Job + per-algorithm experiments |
| GET | `/training-jobs/{id}/logs` | Logs (`after_id`, `limit`) |
| POST | `/training-jobs/{id}/cancel` | Request cooperative cancellation |

Create request:

```json
{
  "project_id": "...",
  "dataset_version_id": "...",
  "name": "Churn baseline sweep",
  "problem_type": "classification",
  "target_column": "churn",
  "feature_columns": null,
  "algorithms": [
    {"algorithm": "logistic_regression", "hyperparameters": {"C": 1.0, "max_iter": 500}},
    {"algorithm": "random_forest_classifier", "hyperparameters": {"n_estimators": 200}}
  ],
  "test_size": 0.2,
  "random_seed": 42,
  "cv_folds": 0
}
```

Rules: target required for classification/regression; target excluded from features;
minimum 2 feature columns after exclusion; algorithms must support the problem type;
hyperparameters are validated against the catalog; job names default to a timestamped
label. Returns `202` with the job.

`GET /training-jobs/{id}` response embeds experiments with `params`, `metrics`,
`status`, `duration`, and `mlflow_run_id`.

Log line: `{"id": 12, "timestamp": "...", "level": "info", "message": "Fitting logistic_regression"}`.

## Experiments

| Method | Path | Purpose |
|---|---|---|
| GET | `/experiments` | Filter by project, dataset, algorithm, status, problem type, search; sort |
| GET | `/experiments/{id}` | Detail incl. params/metrics/artifact metadata |
| POST | `/experiments/compare` | Compare 2–6 experiments of the same problem type |

Compare response: full experiment summaries plus `metric_keys`, per-metric `best`
experiment id and direction (`max` except rmse/mae/duration where `min`), and
`incomparable_reason` when problem types differ. Only problem-relevant metrics are
returned.

## Model Registry

| Method | Path | Purpose |
|---|---|---|
| POST | `/models` | Register an experiment as model version 1 |
| GET | `/models` | List (`project_id`, `search`) |
| GET | `/models/{id}` | Model + versions |
| GET | `/models/{id}/versions` | Versions |
| POST | `/models/{id}/versions` | Register another experiment as a new version |
| POST | `/model-versions/{id}/promote` | Set stage (`staging`, `production`, `none`) |
| POST | `/model-versions/{id}/archive` | Archive |
| GET | `/model-versions/{id}` | Version detail |
| GET | `/model-versions/{id}/download` | Stream artifact (audited) |
| POST | `/models/{id}/versions/compare` | Compare 2–6 versions |

Version uniqueness is enforced per model. Metrics are snapshotted at registration.
Promotion is independent of deployment; deploying pins a specific version.

## Deployments

| Method | Path | Purpose |
|---|---|---|
| POST | `/deployments` | Create from model version; returns API key once |
| GET | `/deployments` | List (`project_id`, status) |
| GET | `/deployments/{id}` | Detail, revisions, recent events |
| PATCH | `/deployments/{id}` | Name/description/monitoring config |
| POST | `/deployments/{id}/stop` | Deactivate |
| POST | `/deployments/{id}/start` | Activate/verify artifact |
| POST | `/deployments/{id}/rollback` | Activate previous revision |
| POST | `/deployments/{id}/rotate-key` | New API key (returned once) |
| GET | `/deployments/{id}/health` | Live artifact/cache health |
| GET | `/deployments/{id}/events` | Lifecycle log |
| GET | `/deployments/{id}/predictions` | Paginated prediction logs |
| POST | `/deployments/{id}/retrain` | Manual retraining job |

Monitoring config (defaults):

```json
{"psi_threshold": 0.2, "drift_share_threshold": 0.3,
 "performance_degradation_threshold": 0.15, "min_samples": 30,
 "window_hours": 24, "auto_retrain_on_drift": false,
 "auto_retrain_cooldown_hours": 12}
```

## Predictions

### POST `/predictions/{deployment_id}`

Auth: `X-API-Key` or JWT. Body:

```json
{"records": [{"tenure": 12, "monthly_charges": 79.5, "contract": "monthly"}]}
```

- 1–1000 records; keys must match the training feature schema; unknown keys rejected
  with field detail; missing features rejected (preprocessing imputes supported
  columns, but the contract still requires all contract fields — see ML_PIPELINE.md).
- Returns:
  ```json
  {"request_id":"...", "deployment_id":"...", "model_version":"3",
   "predictions":[{"prediction":"yes","probabilities":{"no":0.21,"yes":0.79}}],
   "latency_ms":14.2, "warnings":[]}
  ```
- `503` if the deployment is not active or the artifact is unavailable; `422` for
  invalid records; `429` when rate limited. Every request (success or failure) is logged.

### POST `/predictions/feedback`

Auth: `X-API-Key` or JWT. Body:

```json
{"items":[{"prediction_id":"...", "actual":"no"}]}
```

Rejects predictions from another deployment (API-key scope) or another workspace
(JWT). Idempotent per prediction.

### GET `/deployments/{id}/predictions`

Filters: `status`, `from`, `to`, pagination. Returns features (masked on request with
`include_features=false`), prediction, latency, actual.

## Monitoring

| Method | Path | Purpose |
|---|---|---|
| POST | `/deployments/{id}/monitoring/run` | Run analysis now |
| GET | `/deployments/{id}/monitoring/results` | History |
| GET | `/deployments/{id}/monitoring/latest` | Latest result |
| GET | `/deployments/{id}/monitoring/timeseries` | Volume/latency/error buckets (`hours`) |

Result shape:

```json
{
  "id":"...", "deployment_id":"...", "status":"warning",
  "sample_count": 240, "labeled_count": 0,
  "data_drift": {"detected": true, "drift_share": 0.36, "features":[
     {"feature":"monthly_charges","kind":"numeric","psi":0.31,"ks_statistic":0.18,
      "ks_pvalue":0.003,"drifted":true,"missing_rate":0.0}]},
  "prediction_drift": {"detected": false, "psi": 0.04},
  "concept_drift": {"detected": false, "reason":"No ground-truth labels yet",
                    "labels":0},
  "performance": null,
  "created_at":"..."
}
```

`insufficient_data` is returned when fewer than `min_samples` predictions exist.

## Retraining

`POST /deployments/{id}/retrain` body:

```json
{"dataset_version_id": "optional-newer-version", "name": "optional job name"}
```

Creates a training job with the deployment's algorithm, target, feature columns, and
approach. The new job stores `retrain_source_deployment_id`. Compare the resulting
experiment against the deployed version metrics in the console. Promotion remains
explicit via `/model-versions/{id}/promote` followed by deployment update/rollback
policy documented in the UI. The API never auto-promotes.

## Status Codes Summary

| Code | Use |
|---|---|
| 200 | Read/update success |
| 201 | Resource created |
| 202 | Job enqueued |
| 204 | Deletion |
| 400 | Malformed request |
| 401 | Missing/invalid credentials |
| 403 | Not a member or insufficient role |
| 404 | Not found in accessible scope |
| 409 | Duplicate, conflicting state, active dependents |
| 413 | Upload too large |
| 415 | Unsupported file type |
| 422 | Schema validation |
| 429 | Rate limit |
| 500 | Unexpected server error |
| 503 | Dependency unavailable / deployment inactive |

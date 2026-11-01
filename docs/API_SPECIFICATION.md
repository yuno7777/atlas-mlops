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
| GET | `/api/v1/system/slo` | JWT | Process-lifetime availability and latency SLO snapshot, plus trace-export configuration |

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
| PATCH | `/workspaces/{id}/members/{user_id}` | Change a member role (`admin`+) |
| DELETE | `/workspaces/{id}/members/{user_id}` | Remove a member (`admin`+) |
| GET | `/workspaces/{id}/invites` | List workspace invitations (`admin`+) |
| POST | `/workspaces/{id}/invites` | Invite an email with a workspace role (`admin`+) |
| DELETE | `/workspaces/{id}/invites/{invite_id}` | Revoke a pending invite (`admin`+) |
| GET | `/invites/{token}` | Preview an invite issued to the current user |
| POST | `/invites/{token}/accept` | Accept an invite issued to the current user |
| GET | `/workspaces/{id}/audit-events` | Paginated workspace audit trail (`admin`+) |
| GET | `/workspaces/{id}/projects` | Projects in workspace |
| POST | `/workspaces/{id}/projects` | Create project (`admin`+) |
| GET | `/projects/{id}` | Project detail |
| GET | `/projects/{id}/overview` | Dashboard aggregate |
| GET | `/projects/{id}/audit-events` | Recent audit trail |
| GET | `/projects/{id}/lineage` | Dataset-to-deployment lineage graph |

Invite creation returns a one-time token and `/invite/{token}` URL. Only the invited
email can preview and accept the invitation. The raw token is not stored; only its hash
is persisted. Workspace audit pagination uses `offset` and `limit`.

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
  "sensitive_columns": ["region"],
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
optional `sensitive_columns` are excluded from the default feature set, cannot overlap
explicit feature columns, and are used for subgroup fairness metrics on the held-out
evaluation split;
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
| GET | `/model-versions/{id}/card` | Generated JSON model card with evaluation, data, fairness, limitations, monitoring, and provenance |
| GET | `/model-versions/{id}/card.md` | Download the same model card as Markdown |
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
| GET | `/deployments/{id}/challenger` | Current champion/challenger versions and variant statistics |
| PUT | `/deployments/{id}/challenger` | Assign another version of the same registered model as challenger |
| PATCH | `/deployments/{id}/challenger` | Change challenger traffic share (0 to 80%) |
| DELETE | `/deployments/{id}/challenger` | Clear the challenger |
| POST | `/deployments/{id}/challenger/promote` | Promote challenger to champion |
| POST | `/deployments/{id}/challenger/reject` | Reject and clear the challenger |
| GET | `/deployments/{id}/rollout` | Latest progressive rollout and current gate evidence |
| POST | `/deployments/{id}/rollout` | Start a gated rollout for the challenger or supplied model version |
| POST | `/deployments/{id}/rollout/cancel` | Stop an active rollout and return traffic to the champion |
| POST | `/deployments/{id}/batch-predictions` | Score an uploaded CSV and store result CSV |
| GET | `/deployments/{id}/batch-predictions` | List batch prediction jobs |
| GET | `/deployments/{id}/batch-predictions/{batch_id}` | Batch status and output preview |
| GET | `/deployments/{id}/batch-predictions/{batch_id}/download` | Download prediction CSV |
| POST | `/deployments/{id}/explain` | Explain one record with permutation Shapley contributions |
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

### Progressive release gates

`POST /deployments/{id}/rollout` accepts an optional `model_version_id`, increasing
`traffic_steps` ending at 100, and gate thresholds. Defaults are 5/20/50/100% traffic,
100 candidate requests per stage, at most 2% candidate errors, 1000 ms maximum
candidate p95 latency, 20 labeled examples per variant, and at most 3% quality
regression. Example:

```json
{
  "model_version_id": "optional-version-id",
  "traffic_steps": [5, 20, 50, 100],
  "gates": {
    "min_samples": 100,
    "max_error_rate": 0.02,
    "max_p95_latency_ms": 1000,
    "min_labeled_samples": 20,
    "max_metric_regression": 0.03
  }
}
```

If the version is omitted, the configured challenger is used. Monitoring scans evaluate
the active stage. Classification uses labeled accuracy and regression uses relative
MAE change; a failed gate returns traffic to the champion. Passing the 100% stage
promotes the candidate and records a deployment revision. Feedback labels are required
to evaluate the quality gate; until then the rollout waits for enough labeled rows.

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

## Alert Channels

| Method | Path | Purpose |
|---|---|---|
| GET | `/projects/{id}/alert-channels` | List project alert destinations |
| POST | `/projects/{id}/alert-channels` | Create a Slack-compatible or generic webhook destination |
| PATCH | `/projects/{id}/alert-channels/{channel_id}` | Update destination, threshold, secret, or enabled state |
| DELETE | `/projects/{id}/alert-channels/{channel_id}` | Delete destination |
| POST | `/projects/{id}/alert-channels/{channel_id}/test` | Send a test notification |

Only `http://` and `https://` target URLs are accepted. The channel secret is never
returned; webhook requests include an `X-Atlas-Signature` HMAC when a secret is set.

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

## Reusable workflows and benchmark recipes

| Method | Path | Purpose |
|---|---|---|
| GET | `/workflows/templates` | List reusable recipes; optional `problem_type` filter |
| POST | `/workflows/runs` | Create a persisted pipeline run |
| GET | `/workflows/runs?project_id=...` | List recent project runs |
| GET | `/workflows/runs/{id}` | Inspect stages, linked job, experiments, cache state |
| POST | `/workflows/runs/{id}/retry` | Create a linked retry attempt |
| GET | `/benchmarks/catalog` | List popular model and pipeline recipes |
| POST | `/benchmarks/run` | Queue or schedule a benchmark recipe |
| GET | `/benchmarks/runs?project_id=...` | List benchmark workflow runs |
| GET | `/benchmarks/results?project_id=...` | Completed multi-model comparisons with protocol and metrics |

Recipes cover classification baselines, imbalanced classification, regression
baselines, small-data regression, and K-Means clustering. Supervised comparisons share
one dataset version, a seeded holdout, and cross-validation on training rows; reports
include held-out metrics, CV mean/spread, training duration, and optional fairness
summaries. Runs persist their step state and retry lineage. Exact successful matches
can be reused from a checksum/configuration cache. `scheduled_at` supports a single
future execution when the monitoring scheduler or Celery Beat is enabled; it is not a
recurring cron schedule.

## Tracing and SLO snapshot

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to enable OTLP/HTTP trace export and W3C
`traceparent` extraction; `OTEL_SERVICE_NAME` controls the reported service name.
Each response includes `X-Trace-ID` when tracing is enabled. `GET /system/slo` reports
availability and latency against 99.5% and 95%-under-500-ms objectives from the local
Prometheus registry. The reported window is process lifetime and resets when the API
restarts; use a Prometheus server or remote metrics backend for durable, aggregated
SLO history.

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

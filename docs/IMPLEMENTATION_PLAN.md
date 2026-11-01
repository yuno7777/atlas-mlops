# Implementation Plan

## Strategy

Build a complete vertical slice first (dataset → training → MLflow → registry →
deployment → prediction → drift → retraining), then polish the UI. Each phase ends
with executable tests and a documentation update. The backend contract is frozen before
frontend integration to avoid rework.

## Milestones

### M1 — Platform foundation

- Repository, docs, environment matrix, coding standards.
- FastAPI app factory, settings, structured logging, request IDs, error envelope,
  Prometheus metrics, CORS, security headers.
- SQLAlchemy engine/session, declarative base, naming conventions, Alembic baseline.
- Auth (register/login/me), JWT, bcrypt, rate limiting.
- Workspaces/projects and membership enforcement.
- Health/readiness and system info.

Exit criteria: `/api/v1/health` returns OK; migration creates all tables on PostgreSQL;
auth and tenancy tests pass.

### M2 — Datasets

- Storage abstraction (local, S3).
- Upload validation (extension, MIME, size, parse, duplicate checksum).
- Profiling: schema, missing values, duplicates, numeric/categorical statistics,
  preview, target suggestions.
- Versioning and safe download.
- Dataset list/detail UI data contracts.

Exit criteria: upload → ready → preview/profile/versions → invalid uploads rejected;
tests cover each.

### M3 — ML engine and tracking

- Algorithm catalog with validated hyperparameters.
- Leakage-safe pipeline, problem-type metrics, cross-validation.
- Artifact and reference-profile persistence.
- MLflow tracking with persistent store; degraded mode when unavailable.
- Async job runner (Celery + thread fallback), progress/logs/cancellation.
- Experiments list/detail/compare.

Exit criteria: a job trains ≥2 algorithms asynchronously, MLflow records runs, metrics
are visible and comparable, failure path is handled and tested.

### M4 — Registry and serving

- DB-backed registry with versioning, stages, promotion, archive, download.
- Artifact copy + SHA-256 integrity validation.
- Deployment lifecycle, revisions, API keys, health, events.
- Prediction API with Pydantic validation, managed cache, latency logging.
- Ground-truth feedback.

Exit criteria: register → deploy → predict (real model) → logs recorded; rollback and
key rotation tested.

### M5 — Monitoring and retraining

- Reference-profile capture, PSI/KS implementation, prediction drift, concept drift
  with labels.
- Configurable thresholds, stored results, timeseries, events.
- Periodic scan (Celery Beat or thread scheduler).
- Manual and drift-triggered retraining, challenger comparison, explicit promotion.
- Dashboard aggregation endpoint.

Exit criteria: inject drifted requests → drift report flags affected features with
distinct data/prediction/concept fields; feedback changes performance metrics; drift
triggers exactly one retraining job per threshold/cooldown.

### M6 — Frontend

- Design tokens, typography, base components, app shell.
- Overview, Datasets, Experiments, Training, Registry, Deployments, Monitoring,
  Settings.
- Loading/error/empty states; tables; charts; compare workflows; polling.
- API integration with shared request hooks, polling, and mutation toasts.

Exit criteria: full lifecycle operable from the UI against the live API.

### M7 — Testing, CI, delivery

- Backend unit/integration/e2e tests, Playwright browser workflows, CI.
- Compose bring-up with health checks; smoke test.
- Demo data generator + seed script; screenshots/instructions.
- Final docs, limitations, next steps.

### M8 - Advanced platform operations

- Workspace invitations, role changes, and paginated audit events.
- Dataset-to-deployment lineage, batch prediction artifacts, and per-record explanations.
- Alert channels with signed webhook delivery.
- Controlled champion/challenger traffic with explicit promotion or rejection.
- Playwright browser workflows run in CI against a clean migrated and seeded instance.

Exit criteria: backend integration and browser tests cover the workflows with real
trained models where inference behavior is involved. The browser suite uses a local
webhook receiver and does not call an external destination.

### M9 — Release quality, fairness, and benchmark workflows

- Progressive challenger rollouts with configurable traffic stages, quality gates,
  automatic rollback, audit events, and deployment revision promotion.
- Held-out subgroup fairness evaluation, exclusion of sensitive audit columns from
  model inputs, and generated model cards in JSON and Markdown.
- Reusable training/benchmark pipelines with persistent stage state, linked retries,
  checksum/config cache reuse, and one-time scheduled execution.
- Popular classification, imbalanced classification, regression, small-data, and
  clustering recipe catalog with reproducible holdout/CV protocols and comparisons.
- Optional OpenTelemetry OTLP request tracing and process-lifetime availability and
  latency SLO reporting in the monitoring view.

Exit criteria: rollout gate decisions are recorded and revert traffic safely; model
cards retain data/experiment provenance; benchmark runs expose protocol, held-out
metrics, CV spread, and duration; telemetry remains optional when no exporter is set.

## Work Breakdown and Dependencies

```text
M1 ──> M2 ──> M3 ──> M4 ──> M5
                │       │
                └──> M6 ┘
M1..M6 ──> M7
```

Frontend can start after M2 contracts stabilize, but M6 is scheduled after the backend
so responses are final.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Docker startup/resource issues on Windows | Compose verification blocked | Verify engine early; use SQLite + thread mode for local tests; document compose as the supported path |
| MLflow version/API drift | Training failures | Pin versions; isolate tracking in `MLflowTracker`; degraded mode; integration test in compose |
| Training blocks API | Poor UX | Worker process; thread fallback; progress persisted outside request |
| Large uploads/profile memory | OOM | Size limit, dtype-aware downcast, row cap for preview/profile sampling |
| Pickle security | RCE | Never load user paths; platform-only artifact keys + digest; document trust boundary |
| Class imbalance / bad metrics | Misleading results | Weighted metrics, problem-type validation, explicit metric list |
| Drift false positives | Noisy retraining | Minimum sample counts, thresholds, cooldown, no auto-promotion |
| Windows path semantics | Storage bugs | POSIX-style relative keys; path containment checks via `resolve().is_relative_to` |
| Celery/Redis availability | Enqueue failures | 503 with actionable message; thread mode for dev |
| SQLite vs Postgres divergence | Passing tests, broken deploy | Portable types; compose integration run against Postgres; avoid PG-only SQL in app layer |

## Definition of Done (per milestone)

- Code, migration, and tests committed together.
- No TODO-only paths or dead UI controls.
- Structured errors for failure paths.
- Audit events for sensitive operations.
- DOCUMENTING.md status updated with actual test results.
- CHANGELOG entry added.

# Engineering Journal — Atlas MLOps Platform

This document is the single source of truth for project status, decisions, and lessons
learned. It is updated after every implementation phase. No item is marked complete
until it is implemented and verified.

---

## 1. Project Objective and Scope

Build a production-oriented, self-hostable MLOps platform that covers the complete
model lifecycle:

1. Upload and version tabular datasets.
2. Validate, profile, and preview them.
3. Configure and run asynchronous multi-algorithm training jobs.
4. Track runs, parameters, metrics, and artifacts in MLflow.
5. Compare experiments and register model versions.
6. Deploy model versions behind a monitored prediction API.
7. Log predictions and detect data, prediction, and (when labels exist) concept drift.
8. Trigger controlled retraining and promote replacements explicitly.

Non-goals for this iteration:

- Multi-region or Kubernetes deployment.
- Streaming ingestion and online learning.
- LLM/agent experiment tracking.
- Image, text, or unstructured data pipelines.
- Full RBAC administration UI (roles are enforced by the API; UI is scoped to the
  authenticated user's workspaces).

## 2. Development Environment (Phase 0 findings)

Observed on 2026-11-01:

| Component | Observation |
|---|---|
| OS | Windows (win32), PowerShell 5.1 |
| Python | 3.13.15 |
| Node | 24.19.0, npm 11.17.0 |
| Docker | Docker Desktop 29.9.1, Linux engine, initially stopped; started for verification |
| GPU | NVIDIA RTX 4060 Laptop, 8 GB VRAM, CUDA 13.4 driver |
| Local PostgreSQL/Redis | Not installed on host; provided by Docker Compose |
| Repository | Empty at start; built end-to-end |
| Disk free | ~129 GB |

Implications:

- PyTorch is an **optional** dependency. The platform ships a real PyTorch MLP
  classifier implementation, but the default Docker image and local install use
  scikit-learn only to keep image size and build time sane. A build argument enables
  Torch.
- GPU acceleration is not required for any supported algorithm. Tabular models and
  the demo dataset train on CPU in seconds.
- Local development can use SQLite for the application DB when Docker is unavailable;
  PostgreSQL is the supported deployment target and is used by Docker Compose.

## 3. Architecture Summary

Browser (React 19 + Vite + TypeScript + custom design token system)
  → Nginx (static assets, `/api` reverse proxy)
  → FastAPI (`/api/v1`, JWT auth, Pydantic contracts)
  → PostgreSQL (system of record)
  → SQLAlchemy 2 + Alembic
  → Background execution: Celery + Redis (compose) or in-process thread executor (dev)
  → ML pipeline (scikit-learn Pipelines, optional PyTorch MLP)
  → MLflow tracking server (PostgreSQL backend store + persistent artifact volume)
  → Artifact store abstraction (local volume default, S3-compatible optional)
  → Prometheus text metrics, structured JSON logs, prediction/feedback/drift tables

Detailed design: [ARCHITECTURE.md](ARCHITECTURE.md).

## 4. Technology Choices and Justification

| Concern | Choice | Why |
|---|---|---|
| API | FastAPI | Typed contracts, OpenAPI generation, async I/O, strong ecosystem |
| ORM/migrations | SQLAlchemy 2 + Alembic | Explicit schema ownership, portable tests, mature migrations |
| App database | PostgreSQL | JSONB, reliable concurrency, required by spec; source of truth |
| Test database | SQLite (file-backed temp DB) | Fast, deterministic tests without external services; multi-connection isolation handled |
| Background jobs | Celery + Redis, with thread-executor fallback | Prevents long training from blocking requests; fallback keeps single-machine dev usable |
| Experiment tracking | MLflow (server mode in compose) | Purpose-built tracking/artifact store, avoids inventing a second tracking system |
| Registry | Application DB, integrated with MLflow artifacts | MLflow registry stages are deprecated in MLflow 3; a DB registry gives precise lifecycle and FK integrity. Documented in ADR-003 |
| Artifact storage | Local volume by default, S3-compatible adapter | Works without cloud credentials; AWS/MinIO supported via configuration |
| ML | scikit-learn pipelines, joblib, optional Torch | Leakage-safe preprocessing, serialization; no unnecessary abstraction |
| Drift | PSI + two-sample KS + performance monitoring | Interpretable, dependency-light, well understood by practitioners |
| Frontend | React 19 + Vite + TS | Fast builds, typed UI, modern tooling |
| Styling | Custom token system (`styles.css`) | Production dark-mode developer aesthetic without bloated utility classes |
| Primitives | Custom accessible components & SVG visualizations | Interactive charts, distribution bars, probability bars, full control |
| Metrics | prometheus-client | Standard scrape format; no agent required |

## 5. Repository Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/v1/            # HTTP routes (auth, workspaces, datasets, training, experiments, registry, deployments, predictions, alerts)
│   │   ├── core/              # config, logging, security, rate limiting, metrics
│   │   ├── db/                # engine/session, base, init_db
│   │   ├── ml/                # validation, profiling, preprocessing, algorithms,
│   │   │                      # training, evaluation, tracking, registry, inference, drift, explanations
│   │   ├── models/            # SQLAlchemy entities, including alerting, batch, and collaboration records
│   │   ├── repositories/      # query layer
│   │   ├── schemas/           # Pydantic DTOs
│   │   ├── services/          # use-case orchestration
│   │   ├── workers/           # Celery app, tasks, thread executor fallback
│   │   └── main.py
│   ├── alembic/               # versioned schema migrations
│   │   └── versions/0002_platform_features.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_api_endpoints.py
│   │   ├── test_e2e_workflow.py
│   │   ├── test_ml_pipeline.py
│   │   ├── test_security_and_storage.py
│   │   └── test_platform_features.py
│   ├── Dockerfile
│   └── e2e_server.py          # isolated migrated and seeded browser-test API
├── frontend/
│   ├── src/
│   │   ├── components/        # design system, prediction playground, team, audit, alerts, batch, challenger, charts
│   │   ├── pages/             # Overview, Datasets, Training, Experiments, Models, Deployments, Monitoring, Settings, Lineage, Invite
│   │   ├── lib/               # api client, auth, formatters
│   │   ├── hooks/             # useApi hook with automatic polling
│   │   └── styles.css         # token system & layout styles
│   ├── e2e/                   # Playwright browser workflows and teardown
│   ├── playwright.config.ts
│   ├── package.json
│   ├── Dockerfile
│   └── nginx.conf
├── docs/
│   ├── decisions/             # ADR-001 through ADR-004
│   ├── ARCHITECTURE.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── API_SPECIFICATION.md
│   ├── DATABASE_SCHEMA.md
│   ├── ML_PIPELINE.md
│   ├── TESTING_STRATEGY.md
│   ├── DEPLOYMENT.md
│   ├── SECURITY.md
│   ├── CHANGELOG.md
│   └── DOCUMENTING.md
├── demo-data/
│   ├── customer_churn.csv
│   ├── generate_mock_datasets.py
│   ├── run_mock_benchmarks.py
│   └── mock-benchmarks/        # six benchmark CSVs, manifest, and results
├── docker-compose.yml
└── README.md
```

## 6. Implementation Phases

| Phase | Description | Status |
|---|---|---|
| 0 | Environment and repository reconnaissance | Complete |
| 1 | Architecture, docs, contracts, schema, ADRs | Complete |
| 2 | Backend foundation, DB, auth, security | Complete |
| 3 | Tabular dataset management, validation & profiling | Complete |
| 4 | ML engine, algorithm catalog & leakage-safe preprocessing | Complete |
| 5 | Experiment tracking, async jobs & MLflow integration | Complete |
| 6 | Database-backed model registry & promotion stages | Complete |
| 7 | Prediction serving, API key auth, model cache & logging | Complete |
| 8 | Drift detection (PSI & KS), feedback & health monitoring | Complete |
| 9 | Model retraining, candidate comparison & rollback | Complete |
| 10 | Frontend application shell, 9 primary views & playground | Complete |
| 11 | Testing and hardening (21/21 pytest, ruff, oxlint, tsc) | Complete |
| 12 | Documentation, verified commands & delivery | Complete |
| 13 | Collaboration, batch scoring, explanations, lineage, alerts, and controlled challengers | Complete |
| 14 | Release automation, fairness/model cards, traces/SLOs, reusable workflows, benchmark lab | Implemented; integration checks pending |

## 7. Feature Checklist (actual, verified state)

### Platform foundation

- [x] FastAPI application with versioned API (`/api/v1`)
- [x] SQLAlchemy models + Alembic migrations
- [x] PostgreSQL connectivity (compose)
- [x] SQLite fallback for tests/local mode
- [x] JWT authentication, bcrypt password hashing
- [x] Workspace/project tenancy and authorization
- [x] Structured logging, request IDs
- [x] Prometheus metrics endpoint (`/metrics`)
- [x] Rate limiting
- [x] Audit events
- [x] Workspace invitations, membership role changes, and paginated workspace audit events
- [x] Project model lineage from dataset versions through deployments

### Datasets

- [x] Upload (CSV, Parquet, JSON)
- [x] Extension, MIME, size, and content validation
- [x] SHA-256 checksums + duplicate detection
- [x] Dataset versioning
- [x] Schema inference and profiling
- [x] Missing values and duplicate analysis
- [x] Preview rows
- [x] Safe artifact download
- [x] Dataset detail UI with schema & distributions

### ML engine and experiments

- [x] Leakage-safe preprocessing pipeline
- [x] Classification algorithms (LR, RF, DT, GB, SVM, KNN)
- [x] Regression algorithms (Linear, Ridge, RF, GB, SVR)
- [x] Clustering algorithms (K-Means, DBSCAN)
- [x] Optional PyTorch MLP classifier
- [x] Problem-type-aware metrics (accuracy, precision, recall, f1, roc_auc, mse, rmse, mae, r2)
- [x] Cross-validation
- [x] MLflow run logging with persistent artifacts
- [x] Asynchronous training jobs (Celery + Redis or thread executor)
- [x] Progress tracking, live logs, cancellation
- [x] Experiment search/filter/sort
- [x] Experiment detail and multi-run comparison

### Registry, serving, monitoring

- [x] Database-backed model registry with versions
- [x] Stage promotion (none, staging, production, archived)
- [x] Artifact integrity (SHA-256) and guarded loading
- [x] Deployment lifecycle (active, inactive, failed), revisions and rollbacks
- [x] Prediction API with API keys (`X-API-Key`) and input validation
- [x] Managed in-memory model cache with LRU eviction
- [x] Prediction logging and latency tracking
- [x] Ground-truth feedback ingestion
- [x] PSI/KS data drift detection
- [x] Prediction drift detection
- [x] Concept drift with ground-truth labels
- [x] Monitoring results and threshold alerting
- [x] Manual retraining and drift-triggered retraining
- [x] Challenger/champion comparison; explicit non-auto-promotion
- [x] Per-deployment challenger traffic assignment, variant logging, promotion, and rejection
- [x] CSV batch prediction jobs with result artifact downloads
- [x] Per-record Monte Carlo permutation Shapley explanations
- [x] Slack-compatible/webhook alert channels with optional HMAC signing and test delivery
- [x] Progressive release gates using candidate sample count, failure rate, p95 latency, and labeled quality
- [x] Held-out group fairness summaries; selected audit columns are excluded from model features
- [x] Generated model cards with provenance, metrics, fairness results, limitations, and monitoring guidance
- [x] Reusable workflow templates with persisted DAG state, retries, exact-result cache reuse, and one-time scheduling
- [x] Popular benchmark recipes and a measured comparison view with split/CV/runtime context
- [x] Optional OpenTelemetry OTLP request traces and an SLO dashboard backed by Prometheus process metrics

### Delivery

- [x] Frontend shell and ten views (Overview, Datasets, Training, Experiments, Models, Deployments, Monitoring, Benchmarks, Lineage, Settings)
- [x] Workspace invite and role management, audit filtering, and alert channel settings UI
- [x] Deployment batch scoring, challenger routing, and prediction explanation UI
- [x] Benchmark Lab with recipe catalog, workflow progress, CV comparisons, and prior training-job result comparisons
- [x] Progressive rollout controls, fairness panel, model-card downloads, and monitoring SLO panel
- [x] Playwright browser workflows for invitations, prediction and batch scoring, challenger setup, alerts, and lineage
- [x] Real data only; loading/error/empty states
- [x] Docker Compose for the full stack (Postgres, Redis, MLflow, Backend, Celery Worker, Frontend/Nginx)
- [x] Backend unit/integration/e2e tests (21 tests passing)
- [x] Frontend typecheck and production build (`tsc -b && vite build`)
- [x] Demo dataset and reproducible workflow
- [x] README and docs verified against code

## 8. Important Implementation Decisions

See `docs/decisions/` for ADRs. Key decisions:

- **ADR-001**: Modular monolith with a separate worker; no microservices.
- **ADR-002**: PostgreSQL as system of record; MLflow owns run metadata/artifacts.
- **ADR-003**: DB-backed model registry, MLflow artifact integration.
- **ADR-004**: In-process prediction with a bounded model cache, not a model server per deployment.

## 9. Problems Encountered & Resolutions

| Date | Problem | Resolution |
|---|---|---|
| 2026-11-01 | Docker Desktop installed but daemon stopped | Started Docker Desktop; verified engine 29.9.1 |
| 2026-11-01 | No host PostgreSQL/Redis | Provided via Docker Compose; tests use temporary file-based SQLite database with WAL |
| 2026-11-01 | `pgserver` unavailable for Windows | Use file-based SQLite in tests with WAL mode; compose manages Postgres |
| 2026-11-01 | `sqlite3.OperationalError: no such table: training_jobs` during sync job worker execution in tests | In-memory SQLite connections (`sqlite:///:memory:`) create separate isolated databases per connection. Fixed by binding test environment to a temporary file-based SQLite DB in `conftest.py`. |
| 2026-11-01 | Minimum rows requirement for training estimators | Test dataset needed at least 20 rows to train algorithms; created `training_csv` fixture with 30 realistic churn records. |
| 2026-11-01 | `ValueError: PSI inputs must have the same number of buckets` | `float_or_none` converted `-np.inf` and `np.inf` to `None` for JSON serialization, and `_numeric_edge_buckets` filtered out `None` edges, losing 2 buckets. Fixed `_numeric_edge_buckets` to preserve first and last edges as `-np.inf` and `np.inf`. |
| 2026-11-01 | Existing development SQLite had tables from `Base.metadata.create_all` but no Alembic history, so `upgrade head` collided with existing tables. | Preserved the database, applied the additive 0002 columns/index locally, and stamped the database at `0002_platform`. Fresh installs should run `alembic upgrade head` before starting the API or running `seed-demo`. |

## 10. Testing Performed

| Component | Command | Result |
|---|---|---|
| Reconnaissance | `python --version`, `node --version`, `docker info` | Python 3.13.15, Node 24.19.0, Docker 29.9.1 |
| Backend Tests | `..\.venv\Scripts\python.exe -m pytest -q` | **21/21 passed** in 12.12s, including categorical missing-value training and prediction |
| Backend Lint | `ruff check app tests e2e_server.py ..\demo-data\generate_mock_datasets.py ..\demo-data\run_mock_benchmarks.py` | **All checks passed!** (0 errors) |
| Backend Format | `ruff format --check app tests e2e_server.py ..\demo-data\generate_mock_datasets.py ..\demo-data\run_mock_benchmarks.py` | **111 files already formatted** |
| Frontend Lint | `npm run lint` (`oxlint`) | **0 errors** (non-blocking React hook/fast-refresh warnings remain) |
| Frontend Build | `npm run build` (`tsc -b && vite build`) | **Zero TypeScript errors**; Vite reports a non-blocking chunk-size advisory above 500 kB |
| Browser E2E | `npm run e2e` | **3/3 passed** on Chromium; clean SQLite Alembic migrations, invitation acceptance, batch/explanation/challenger, webhook, and lineage flows |
| Demo screenshots | `npm run screenshots` | Five 3x screenshots regenerated from the seeded Customer Churn project, including a live playground prediction |
| Synthetic Benchmarks | `python demo-data/run_mock_benchmarks.py` | **6 datasets / 18,000 rows / 12 completed experiments / 6 pairwise comparisons**, with 80/20 holdout and 3-fold CV |

## 11. Verified Verification Commands

```bash
# Run backend tests
cd backend
..\.venv\Scripts\python -m pytest -v

# Run backend linter & formatter checks
..\.venv\Scripts\ruff check app tests
..\.venv\Scripts\ruff format --check app tests

# Run frontend build
cd ../frontend
npm run build
```

## 12. Known Limitations & Operating Boundaries

- Tabular data focus: CSV, Parquet, and JSON records.
- Single-node deployment in default Docker Compose; Celery worker concurrency defaults to available host cores.
- Model cache is bounded per API process; eviction uses LRU policy when `MODEL_CACHE_SIZE` is reached.
- Concept drift is calculated upon arrival of ground-truth feedback via `/api/v1/predictions/feedback`.

## 13. Reconciled Progress from the Previous Development Run

This journal now records work completed before the current feature phase as well as
the new code below. The earlier run delivered the following:

- Added six deterministic, 3,000-row synthetic tabular datasets: SaaS churn, loan
  repayment/default, e-commerce conversion, retail demand, delivery ETA, and used
  vehicle prices. Generator, manifest, upload notes, results JSON/CSV, and a Markdown
  summary live under `demo-data/`.
- Ran the six datasets through paired baseline experiments with a shared 80/20 holdout,
  seed 42, and three-fold cross-validation. The successful report has 18,000 rows,
  12 completed experiments, and six pairwise comparisons. The report files are
  `demo-data/mock-benchmarks/benchmark_results.json`, `.csv`, and
  `benchmark_summary.md`.
- The first app training attempt exposed categorical `pd.NA` incompatibility in the
  scikit-learn preprocessing path. The preprocessing conversion and regression
  coverage were added, then all six datasets were uploaded and re-run successfully.
  Earlier failed job/experiment rows remain in project history; they were not removed
  from the audit trail. The benchmark report counts only the completed rerun.
- Replaced the Vite template favicon with the Atlas four-tile favicon in
  `frontend/public/favicon.svg` and pointed `frontend/index.html` at it. The prior
  browser capture pass also refreshed the five project screenshots at 3x resolution.
- Completed and documented workspace invites/roles, audit history, dataset-to-model
  lineage, batch prediction exports, local Shapley explanations, signed webhook
  alerts, and challenger traffic assignment. The previous reported browser run covered
  those flows, and the previous backend run reported 21 passing tests.

## 14. Advanced Model Operations and Benchmark Lab

### Release gates and progressive rollout

- Migration `0003_modelops_workflows.py` adds the `deployment_rollouts` table and a
  partial unique index that permits one running rollout per deployment.
- A rollout can use a configured challenger or a candidate version directly. It starts
  at 5% by default, then steps through 20%, 50%, and 100% (custom increasing steps are
  accepted, ending at 100%). The monitoring scan evaluates each step.
- Gates cover minimum candidate requests, maximum candidate error rate, candidate p95
  latency, minimum labeled examples for both variants, and maximum metric regression.
  Classification compares labeled accuracy; regression compares relative MAE change.
  A failed gate sets challenger traffic to zero and records an event. A final passed
  stage promotes the candidate, writes a revision, and audits the promotion.
- Manual challenger edits are rejected while an automated rollout is running. The
  rollout UI exposes gate thresholds, step state, sample evidence, and cancellation.

### Fairness evaluation and model cards

- Training requests can specify sensitive audit columns. The backend checks that the
  columns exist, rejects overlap with explicit model features, and omits them from the
  default feature set. Fairness is computed on the held-out split, not the training
  rows.
- Classification reports subgroup sample count and accuracy; for binary targets it
  also reports selection rate, TPR, FPR, and selection/accuracy gaps for the final
  estimator class. Regression reports subgroup MAE/RMSE and MAE gap. Small-group
  counts and interpretation notes accompany the result.
- Registered model versions expose JSON at
  `/api/v1/model-versions/{version_id}/card` and downloadable Markdown at
  `/api/v1/model-versions/{version_id}/card.md`. Cards are generated from immutable
  model-version, experiment, dataset-version, and artifact provenance; there is no
  separate mutable card table.

### OpenTelemetry and SLO dashboard

- When `OTEL_EXPORTER_OTLP_ENDPOINT` is set, the API creates HTTP request spans,
  accepts W3C `traceparent`, exports spans using OTLP/HTTP, and returns `X-Trace-ID`.
  Tracing stays disabled when the endpoint is unset. The Python OTLP exporter setup
  follows the [official OpenTelemetry exporter documentation](https://opentelemetry.io/docs/languages/python/exporters/).
- Authenticated `GET /api/v1/system/slo` backs the Monitoring page with a 99.5%
  availability objective and a 95% latency objective at 500 ms, plus p95 and error
  budget use. These values come from the in-process Prometheus registry and reset when
  the API process restarts; a Prometheus server or remote metrics store is needed for
  durable, multi-process, time-windowed SLO history.

### Reusable workflows and benchmarks

- `/api/v1/workflows/templates` lists the reusable graph recipes and
  `/api/v1/workflows/runs` creates, lists, inspects, or retries run records. Workflow
  state is persisted in `workflow_runs`, linked to the training job, and reports the
  validate → prepare → train → evaluate → fairness → register stages.
- Retries create a new attempt linked to the prior run (up to the configured limit).
  A SHA-256 cache key includes the dataset checksum and effective recipe/training
  configuration; an identical completed run can be reused. `scheduled_at` supports a
  one-time future run; scheduled runs need `ENABLE_MONITORING_SCHEDULER=true` in local
  thread mode or the existing Celery Beat service in Compose.
- The Benchmark Lab catalog includes classification baselines, imbalanced
  classification, regression baselines, small-data regression, and a clustering
  baseline. Supervised recipes use the same selected dataset version, seeded 80/20
  split, and three-fold CV by default. Training jobs record held-out metrics, CV mean
  and spread, training duration, and optional fairness summaries. The page also
  surfaces completed multi-model jobs already in project history, including the six
  synthetic dataset comparisons from the previous run.
- Templates are predefined and versioned in code rather than user-authored DAGs. Cache
  reuse operates at the completed-run level (not individual intermediate steps), and
  scheduling is one-time rather than cron recurrence.

## 15. Current Phase Verification

Completed on 2026-11-01 after this phase's edits:

| Check | Result |
|---|---|
| Python compile (`python -m compileall -q app alembic/versions/0003_modelops_workflows.py`) | Passed |
| Backend lint (`ruff check app alembic/versions/0003_modelops_workflows.py`) | Passed |
| Backend format (`ruff format --check app alembic/versions/0003_modelops_workflows.py`) | 112 files already formatted |
| Frontend lint (`npm run lint`) | Passed with non-blocking Oxlint warnings; no errors |
| Frontend production build (`npm run build`) | Passed with zero TypeScript errors; Vite emitted the >500 kB bundle advisory |
| Documentation/patch whitespace (`git diff --check`) | Passed |
| Backend pytest / browser E2E | Not rerun during this phase; earlier results are recorded in Section 10 |

The API specification, database schema, deployment configuration guide, README,
changelog, implementation plan, and this journal now describe the rollout, fairness,
model-card, benchmark workflow, and tracing/SLO contracts. No fresh unit, integration,
or browser test result is claimed for this phase.

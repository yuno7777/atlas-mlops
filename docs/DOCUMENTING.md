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
│   │   ├── api/v1/            # HTTP routes (auth, workspaces, datasets, training, experiments, registry, deployments, predictions, overview)
│   │   ├── core/              # config, logging, security, rate limiting, metrics
│   │   ├── db/                # engine/session, base, init_db
│   │   ├── ml/                # validation, profiling, preprocessing, algorithms,
│   │   │                      # training, evaluation, tracking, registry, inference, drift
│   │   ├── models/            # SQLAlchemy entities (User, Workspace, Dataset, TrainingJob, Experiment, ModelVersion, Deployment, PredictionLog, etc.)
│   │   ├── repositories/      # query layer
│   │   ├── schemas/           # Pydantic DTOs
│   │   ├── services/          # use-case orchestration
│   │   ├── workers/           # Celery app, tasks, thread executor fallback
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_api_endpoints.py
│   │   ├── test_e2e_workflow.py
│   │   ├── test_ml_pipeline.py
│   │   └── test_security_and_storage.py
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/        # design system, AppShell, PredictionPlayground, RetrainDialog, ToastProvider, SVG charts
│   │   ├── pages/             # Overview, Datasets, DatasetDetail, Training, NewTraining, Experiments, ExperimentDetail, Models, ModelDetail, Deployments, DeploymentDetail, Monitoring, Settings
│   │   ├── lib/               # api client, auth, formatters
│   │   ├── hooks/             # useApi hook with automatic polling
│   │   └── styles.css         # token system & layout styles
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
├── demo-data/                 # customer churn reference dataset
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
| 10 | Frontend application shell, 8 primary views & playground | Complete |
| 11 | Testing and hardening (18/18 pytest, ruff, oxlint, tsc) | Complete |
| 12 | Documentation, verified commands & delivery | Complete |

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

### Delivery

- [x] Frontend shell and all eight views (Overview, Datasets, Training, Experiments, Models, Deployments, Monitoring, Settings)
- [x] Real data only; loading/error/empty states
- [x] Docker Compose for the full stack (Postgres, Redis, MLflow, Backend, Celery Worker, Frontend/Nginx)
- [x] Backend unit/integration/e2e tests (18 tests passing)
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

## 10. Testing Performed

| Component | Command | Result |
|---|---|---|
| Reconnaissance | `python --version`, `node --version`, `docker info` | Python 3.13.15, Node 24.19.0, Docker 29.9.1 |
| Backend Tests | `python -m pytest -v` | **18/18 passed** in 3.81s (`test_api_endpoints.py`, `test_e2e_workflow.py`, `test_ml_pipeline.py`, `test_security_and_storage.py`) |
| Backend Lint | `ruff check app tests` | **All checks passed!** (0 errors) |
| Backend Format | `ruff format --check app tests` | **90 files checked, 90 files properly formatted** |
| Frontend Lint | `npm run lint` (`oxlint`) | **0 errors** (32 warnings, fast linter pass) |
| Frontend Build | `npm run build` (`tsc -b && vite build`) | **Zero TypeScript errors**, bundle built cleanly |

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

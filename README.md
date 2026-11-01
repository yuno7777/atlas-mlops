# Atlas — Production MLOps Platform

Atlas is a modern, modular, self-hostable Machine Learning Operations (MLOps) platform engineered to manage the entire lifecycle of production tabular models: dataset versioning, asynchronous multi-algorithm training, experiment tracking with MLflow, database-backed model registry with promotion stages, managed low-latency prediction serving with API keys, continuous drift detection (PSI + two-sample KS), and automated challenger retraining.

---

## Architecture Overview

```
                      ┌────────────────────────────────────────┐
                      │    Atlas Web UI (React 19 + Vite)      │
                      │  Custom Dark-Mode Token Design System   │
                      └───────────────────┬────────────────────┘
                                          │ HTTP / JSON
                                          ▼
                      ┌────────────────────────────────────────┐
                      │       Atlas API (FastAPI / ASGI)       │
                      │   Auth (JWT) · RBAC · Rate Limiting    │
                      └───────┬───────────────┬────────────────┘
                              │               │
            ┌─────────────────┴────┐     ┌────┴─────────────────┐
            │ PostgreSQL (App DB)  │     │ Redis Broker / Cache │
            │ SQLAlchemy 2+Alembic │     └──────────┬───────────┘
            └──────────────────────┘                │
                                                    ▼
            ┌──────────────────────┐     ┌──────────────────────┐
            │ MLflow Tracking      │◄────┤ Celery Worker        │
            │ Parameters & Metrics │     │ Multi-Algorithm Jobs │
            └──────────────────────┘     └──────────┬───────────┘
                                                    │
                                                    ▼
                                         ┌──────────────────────┐
                                         │ Artifact Store       │
                                         │ Local Volume or S3   │
                                         └──────────────────────┘
```

---

## Key Capabilities

1. **Tabular Dataset Management & Profiling**
   - Ingest CSV, Parquet, and JSON datasets.
   - Comprehensive validation: extension checks, MIME validation, schema inference, duplicate detection, and SHA-256 checksums.
   - Automated profiling: row/column counts, missing rates, cardinality, and target suggestions.

2. **Asynchronous Multi-Algorithm Training & Experiment Tracking**
   - Asynchronous job execution via Celery + Redis (with in-process synchronous/thread executor fallback for local testing).
   - Broad algorithm catalog across problem types:
     - **Classification:** Logistic Regression, Random Forest, Decision Tree, Gradient Boosting, SVM, KNN, optional PyTorch MLP.
     - **Regression:** Linear Regression, Ridge, Random Forest, Gradient Boosting, SVR.
     - **Clustering:** K-Means, DBSCAN.
   - Full MLflow tracking: parameters, cross-validation metrics, artifacts (`model.joblib`, `reference_profile.json`), and system tags.

3. **Database-Backed Model Registry**
   - Versioned model repository with cryptographic SHA-256 integrity validation.
   - Explicit lifecycle stage transitions: `none` → `staging` → `production` → `archived`.
   - Side-by-side experiment and version metric comparison.

4. **Guarded Prediction Serving & Monitoring**
   - High-performance, low-latency prediction endpoints authenticated via hashed API keys (`X-API-Key`).
   - In-memory thread-safe `ModelCache` with LRU eviction and automatic TTL invalidation.
   - Real-time prediction logging with latency capture and ground-truth feedback ingestion.
   - Multi-faceted drift detection:
     - **Data Drift:** Population Stability Index (PSI) and two-sample Kolmogorov-Smirnov (KS) tests on input features against reference distributions.
     - **Prediction Drift:** Output probability / score distribution drift.
     - **Concept Drift:** Performance degradation tracking upon receiving ground-truth feedback.

5. **Challenger Retraining & Candidate Comparison**
   - On-demand or drift-triggered retraining linked directly to deployed endpoints.
   - Automatic cooldown guards preventing duplicate retraining storms.
   - Side-by-side champion vs. challenger candidate comparison with explicit promotion approval.

---

## Tech Stack

- **Backend:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, scikit-learn, joblib, PyTorch (optional), Celery, Redis, MLflow.
- **Frontend:** React 19, TypeScript, Vite, custom dark-mode token system (`styles.css`), custom SVG visualizations.
- **Databases & Stores:** PostgreSQL (production), SQLite (local test suite), Local filesystem / AWS S3 storage.
- **Tooling:** Ruff (linter & formatter), Pytest, Oxlint, Docker & Docker Compose.

---

## Quickstart with Docker Compose

To launch the complete Atlas MLOps stack (Postgres, Redis, MLflow, Backend API, Worker, and Frontend UI) with a single command:

```bash
docker compose up -d --build
```

Access services:
- **Atlas Web Platform:** [http://localhost:3000](http://localhost:3000)
- **FastAPI Interactive Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **MLflow Tracking UI:** [http://localhost:5000](http://localhost:5000)
- **Prometheus Metrics:** [http://localhost:8000/metrics](http://localhost:8000/metrics)

---

## Local Development Setup

### Backend

```bash
# 1. Navigate to backend directory
cd backend

# 2. Activate virtual environment (Windows)
..\.venv\Scripts\activate

# 3. Run database migrations
alembic upgrade head

# 4. Start the FastAPI development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
# 1. Navigate to frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Start the Vite dev server
npm run dev
```

The frontend will run on [http://localhost:5173](http://localhost:5173) with automatic proxying to the backend at port 8000.

---

## Running Verification & Tests

### Backend Test Suite

Atlas includes unit, integration, and full end-to-end workflow test suites verifying everything from file validation and model training to deployment and drift detection:

```bash
cd backend
..\.venv\Scripts\python -m pytest -v
```

All 18 tests execute deterministically using an isolated SQLite database and pass in under 4 seconds.

### Backend Code Quality

```bash
# Linting
..\.venv\Scripts\ruff check app tests

# Formatting verification
..\.venv\Scripts\ruff format --check app tests
```

### Frontend Code Quality & Build

```bash
cd frontend

# Linting with oxlint
npm run lint

# TypeScript check & production bundle build
npm run build
```

---

## Documentation

Exhaustive design specifications, architecture decision records, and API contracts are available in `docs/`:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — System architecture, module boundaries, and concurrency model.
- [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md) — RESTful endpoints, schemas, and error conventions.
- [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) — Relational models, constraints, and indexes.
- [docs/ML_PIPELINE.md](docs/ML_PIPELINE.md) — Preprocessing, algorithm configurations, and drift math.
- [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md) — Test pyramid, fixtures, and verification standards.
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Production Docker Compose and configuration parameters.
- [docs/SECURITY.md](docs/SECURITY.md) — Authentication, secret management, and validation guards.
- [docs/DOCUMENTING.md](docs/DOCUMENTING.md) — Detailed engineering journal, verified command log, and problem resolutions.
- [docs/decisions/](docs/decisions/) — Architecture Decision Records (ADR-001 through ADR-004).

---

## License

MIT

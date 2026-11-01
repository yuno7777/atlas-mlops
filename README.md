# Atlas

**Self-hosted tabular MLOps platform for training, experiment tracking, versioned registry, real-time inference, and drift monitoring.**

[![Atlas CI](https://github.com/yuno7777/mlops-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/yuno7777/mlops-platform/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev)
[![MLflow](https://img.shields.io/badge/MLflow-3.17-0194E2?style=flat&logo=mlflow&logoColor=white)](https://mlflow.org)
[![Celery](https://img.shields.io/badge/Celery-5.6-37814A?style=flat&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

<br />

![Atlas Overview Dashboard](docs/assets/screenshots/overview.png)

Atlas provides a complete machine learning lifecycle stack in a single deployable repository. It handles tabular dataset validation, multi-algorithm model training, MLflow tracking, stage-based registration, sub-50ms authenticated inference, and automated statistical drift detection.

---

## Highlights

- **Dataset Validation & Profiling:** Ingest CSV, Parquet, and JSON files with schema inference, MIME checks, SHA-256 integrity hashing, and baseline statistical profiling.
- **Asynchronous Training Pipeline:** Train classification, regression, and clustering jobs asynchronously with Celery + Redis, recording parameters, cross-validation metrics, and serialized artifacts in MLflow.
- **Model Registry & Stage Gates:** Maintain strict model versioning with explicit lifecycle stage transitions (`none` -> `staging` -> `production` -> `archived`).
- **Low-Latency Inference Server:** Serve predictions through FastAPI endpoints protected by hashed API keys, backed by a thread-safe LRU model cache with automatic invalidation.
- **Continuous Drift Detection:** Track incoming feature distributions with Population Stability Index (PSI) and two-sample Kolmogorov-Smirnov (KS) tests to trigger automated challenger retraining before accuracy degrades.
- **Batch Scoring & Explanations:** Score CSV uploads through a deployment, download the result file, and inspect per-record permutation Shapley contributions.
- **Controlled Champion/Challenger Traffic:** Route a configurable share of prediction requests to a second version of the same registered model and compare variants before promotion.
- **Workspace Collaboration & Lineage:** Invite members with roles, audit workspace changes, configure signed alert webhooks, and trace datasets through deployed versions.
- **Gated Progressive Releases:** Increase challenger traffic in stages with sample, error, latency, and labeled-quality gates; failed stages roll back to the champion.
- **Fairness & Model Cards:** Audit held-out subgroup metrics while keeping sensitive columns out of model features; export provenance-rich JSON or Markdown cards.
- **Benchmark Lab & Pipelines:** Run reusable classification, regression, and clustering recipes with fixed seeds, cross-validation, timing, caching, and retry history.
- **Tracing & SLOs:** Export request traces over OTLP/HTTP and inspect API availability and latency objectives from Monitoring.

---

## System Architecture

```text
               +---------------------------------------+
               |        Atlas UI (React 19 + Vite)     |
               |     Custom Dark-Mode Token System     |
               +-------------------+-------------------+
                                   | HTTP / REST
                                   v
               +---------------------------------------+
               |        Atlas API (FastAPI / ASGI)     |
               |     JWT Auth | RBAC | API Key Guard   |
               +---------+-------------------+---------+
                         |                   |
            +------------+-------+   +-------+---------------+
            |  PostgreSQL / DB   |   |   Redis (Task Queue)  |
            | SQLAlchemy + Alembic|   +-------+---------------+
            +--------------------+           |
                                             v
            +--------------------+   +-----------------------+
            |  MLflow Tracking   |<--|     Celery Worker     |
            | Parameters & Runs  |   | Training & Drift Math |
            +--------------------+   +-------+---------------+
                                             |
                                             v
                                     +-----------------------+
                                     |    Artifact Store     |
                                     | Local Volume or S3    |
                                     +-----------------------+
```

---

## Interface & Workflows

### 1. Project Overview & Operational Health
Monitor active deployments, recent training jobs, tracked experiments, and model inventory from a unified workspace dashboard.

![Project Overview](docs/assets/screenshots/overview.png)

### 2. Interactive Prediction Playground
Validate deployed endpoints in real time. Inspect sample payloads, execute inference, and review predicted class probabilities alongside latency metrics.

![Prediction Playground](docs/assets/screenshots/playground.png)

### 3. Experiment Tracking & Run Comparisons
Compare hyperparameter configurations, cross-validation metrics (ROC-AUC, F1, Log Loss, RMSE), and training artifacts across runs tracked by MLflow.

![Experiment Tracking](docs/assets/screenshots/experiments.png)

### 4. Real-Time Drift Detection & Monitoring
Monitor live feature distributions, output score shift, and statistical drift alerts (PSI and two-sample KS tests) computed against reference baselines.

![Monitoring & Drift Detection](docs/assets/screenshots/monitoring.png)

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Backend API** | Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, Uvicorn |
| **Distributed Tasks** | Celery, Redis |
| **ML Engine** | scikit-learn, joblib, NumPy, pandas, SciPy, PyTorch (optional MLP) |
| **Experiment Tracking** | MLflow |
| **Frontend** | React 19, TypeScript, Vite, custom dark token design system |
| **Storage & DB** | PostgreSQL, SQLite (testing), Local filesystem / AWS S3 |
| **DevOps & QA** | Docker Compose, Pytest, Playwright, Ruff, Oxlint |

---

## Quickstart with Docker Compose

Spin up the entire stack (PostgreSQL, Redis, MLflow, Backend API, Celery Worker, and Frontend UI) with one command:

```bash
docker compose up -d --build
```

### Service Endpoints

| Service | URL | Default Credentials |
|---|---|---|
| Atlas Web Platform | [http://localhost:3000](http://localhost:3000) | demo@atlasmlops.dev / demo-password-123 |
| FastAPI Interactive Docs | [http://localhost:8000/docs](http://localhost:8000/docs) | None |
| MLflow Tracking Dashboard | [http://localhost:5000](http://localhost:5000) | None |
| Prometheus Metrics | [http://localhost:8000/metrics](http://localhost:8000/metrics) | None |

### Deploy to a VPS

The production override puts the full stack behind Caddy with automatic HTTPS and closes
every port except 80 and 443:

```bash
# Set DOMAIN, SECRET_KEY, and POSTGRES_PASSWORD in .env first
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the single-server checklist.

---

## Local Development

### Prerequisites

- Python 3.11+ (Python 3.13 recommended)
- Node.js 20+ and npm
- Docker (optional, for Redis and PostgreSQL)

### 1. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Run database migrations
alembic upgrade head

# Seed sample project, dataset, trained model, and active deployment
python -m app.cli seed-demo

# Start the API server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The UI will be accessible at [http://127.0.0.1:5173](http://127.0.0.1:5173). Requests to `/api` proxy automatically to the backend running on port 8000.

---

## Synthetic Model Benchmarks

The repository includes six reproducible synthetic datasets with 3,000 rows each:
SaaS churn, loan repayment risk, e-commerce conversion, retail demand, delivery ETA,
and used vehicle prices. Three are classification tasks and three are regression
tasks. Their feature columns include a small, intentional amount of missing data to
exercise Atlas preprocessing. Training fits numeric median imputation and scaling,
plus categorical most-frequent imputation and one-hot encoding within each split.

After starting Atlas and seeding the demo account, generate, upload, and train them
from the repository root:

```bash
python demo-data/generate_mock_datasets.py
python demo-data/run_mock_benchmarks.py
```

The workflow creates a `Synthetic Model Benchmarks` project, runs two algorithms per
dataset with an 80/20 holdout and 3-fold cross-validation, and compares each pair of
experiments. Dataset descriptions, preprocessing notes, and the resulting metrics are
in [demo-data/mock-benchmarks](demo-data/mock-benchmarks/README.md). The data is
synthetic and intended for pipeline testing, not production decisions.

### Popular model and pipeline recipes

The authenticated **Benchmark Lab** page offers reusable recipes for common tabular
baselines:

| Recipe | Popular models | Main comparison metrics |
|---|---|---|
| Classification baselines | Logistic Regression, Random Forest, Gradient Boosting | Accuracy, weighted F1, ROC AUC |
| Imbalanced classification | Class-weighted Logistic Regression, Random Forest, Gradient Boosting | Weighted F1, ROC AUC, accuracy |
| Regression baselines | Linear Regression, Ridge, Random Forest, Gradient Boosting | R-squared, RMSE, MAE |
| Small-data regression | Ridge, constrained Random Forest, Gradient Boosting | R-squared, RMSE, MAE |
| Clustering baseline | K-Means | Silhouette, Davies-Bouldin, Calinski-Harabasz |

Supervised runs compare models on the same dataset version and seeded holdout, with
cross-validation computed on the training partition. The page records CV mean and
spread, held-out metrics, training time, subgroup fairness results when requested, and
the full pipeline attempt history. The API contract and generated synthetic results
are documented in [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md) and
[demo-data/mock-benchmarks](demo-data/mock-benchmarks/README.md).

## Testing & Code Quality

Automated checks cover dataset validation, training and serving workflows, drift calculations, collaboration, batch scoring, explanations, challenger routing, alert delivery, and lineage.

### Backend Tests

```bash
cd backend
python -m pytest -v
```

All 20 backend tests run against an isolated SQLite test database and complete in seconds.

### Browser End-to-End Tests

```bash
cd frontend
npm ci
npm run e2e
```

The Playwright suite starts the API and Vite app on isolated ports, creates a temporary SQLite database, applies Alembic migrations, and seeds the Customer Churn project. It exercises invitation acceptance, workspace audit filtering, live prediction and explanation, batch scoring, challenger setup, webhook delivery, and lineage navigation.

### Linting & Formatting

```bash
# Python linting and formatting checks
ruff check app tests
ruff format --check app tests

# Frontend linting and type checking
cd frontend
npm run lint
npm run build
```

---

## Core Capabilities

### Tabular Dataset Profiling
- Upload CSV, Parquet, or JSON datasets with automatic MIME and extension verification.
- Calculates row counts, column types, null percentages, unique value counts, and cardinality.
- Generates SHA-256 checksums to ensure dataset version immutability.

### Training & Algorithms
- **Classification:** Logistic Regression, Random Forest, Decision Tree, Gradient Boosting, SVM, KNN, PyTorch MLP.
- **Regression:** Linear Regression, Ridge, Random Forest, Gradient Boosting, SVR.
- **Clustering:** K-Means, DBSCAN.
- Automatic metric logging: ROC-AUC, Precision, Recall, F1 score, Accuracy, Log Loss, RMSE, MAE, R-squared, Silhouette score.

### Deployment & Serving
- Deploy any registered model version to a dedicated REST endpoint.
- Authenticate external scoring requests using hashed `X-API-Key` headers.
- Thread-safe `ModelCache` loads models into memory on first request with LRU eviction and TTL expiry.
- Every prediction request logs input features, output probability scores, and latency in milliseconds.

### Drift & Continuous Monitoring
- **Data Drift:** Compares incoming feature distributions against training reference profiles using Population Stability Index (PSI) and two-sample Kolmogorov-Smirnov (KS) tests.
- **Concept Drift:** Tracks ground-truth feedback against prior predictions to detect performance regression.
- **Automated Challenger Retraining:** Triggers new training runs when drift thresholds are breached, with cooldown guards preventing duplicate retraining jobs.

---

## Repository Documentation

Detailed engineering documentation and architecture decision records:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): System architecture, process boundaries, and concurrency model.
- [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md): REST endpoints, request/response schemas, and error codes.
- [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md): Relational tables, indexes, constraints, and relationships.
- [docs/ML_PIPELINE.md](docs/ML_PIPELINE.md): Data preprocessing, algorithm configs, and drift mathematics.
- [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md): Testing pyramid, fixtures, and verification strategy.
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): Production deployment guides and environment variables.
- [docs/SECURITY.md](docs/SECURITY.md): Authentication, RBAC, input validation, and secret handling.
- [docs/decisions/](docs/decisions/): Architecture Decision Records (ADR-001 to ADR-004).

---

## License

This project is licensed under the MIT License.

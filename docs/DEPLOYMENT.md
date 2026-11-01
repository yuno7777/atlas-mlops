# Deployment

## Local Development (Docker Compose — recommended)

Prerequisites: Docker Desktop/Engine 24+, 8 GB RAM available, free ports 3000, 8000,
5000, 5432, 6379.

```bash
cp .env.example .env
# edit SECRET_KEY and database passwords; defaults are development-only
docker compose up -d --build
```

Services:

| Service | URL | Notes |
|---|---|---|
| Frontend | http://localhost:3000 | Nginx + built SPA |
| API | http://localhost:8000/api/v1/docs | OpenAPI/Swagger |
| MLflow | http://localhost:5000 | Tracking UI |
| PostgreSQL | localhost:5432 | `atlas` database |
| Redis | localhost:6379 | Broker (not exposed by default in compose? kept internal) |

First run:

```bash
docker compose exec backend python -m app.cli seed-demo
```

Or register through the UI. To load the demo dataset and train models:

```bash
python scripts/generate_demo_data.py
docker compose exec -T backend python -m app.cli seed-demo
```

Check health:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
docker compose ps
```

Artifacts persist in named volumes. `docker compose down` keeps data;
`docker compose down -v` destroys databases and artifacts.

## Production on a Single VPS (Caddy + TLS)

The production override closes every port except 80 and 443. Caddy obtains a Let's
Encrypt certificate for `DOMAIN` and proxies to the frontend; nginx forwards `/api` to
the backend. A 4 GB RAM server is enough for the full stack with a small demo dataset.

1. Point an A/AAAA record at the server and install Docker with the Compose plugin.
2. Copy `.env.example` to `.env` and set the deployment values:

```env
DOMAIN=atlas.example.com
SECRET_KEY=<32+ random characters>
POSTGRES_PASSWORD=<strong password>
```

3. Start the stack with both compose files:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python -m app.cli seed-demo
```

4. Open `https://atlas.example.com`.

The first Caddy start can take a minute while certificates are issued. Postgres, Redis,
MLflow, and the API stay on the private Compose network. Keep `.env` out of git.

## Configuration

All configuration is environment-based (`backend/app/core/config.py`, `.env.example`).
Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | dev placeholder | JWT signing; must be changed |
| `DOMAIN` | none | Public hostname for the production Caddy override |
| `DATABASE_URL` | postgres in compose | SQLAlchemy URL |
| `REDIS_URL` | redis://redis:6379/0 | Celery broker/backend |
| `JOB_EXECUTION_MODE` | thread (local), celery (compose) | Worker strategy |
| `MLFLOW_TRACKING_URI` | http://mlflow:5000 | Tracking server |
| `MLFLOW_ENABLED` | true | Disable for tests/degraded mode |
| `ARTIFACT_ROOT` | /data/artifacts | Local artifact volume |
| `STORAGE_BACKEND` | local | `local` or `s3` |
| `MAX_UPLOAD_MB` | 100 | Upload limit |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 720 | JWT lifetime |
| `ENABLE_MONITORING_SCHEDULER` | false (api), true (beat) | Periodic scans |
| `CORS_ORIGINS` | http://localhost:3000 | Allowed origins |
| `RATE_LIMIT_PREDICTIONS_PER_MINUTE` | 120 | Per-deployment |
| `OTEL_SERVICE_NAME` | atlas-api | OpenTelemetry resource service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | blank | Optional OTLP/HTTP collector base URL; blank disables trace export |
| `LOG_LEVEL` | INFO | |

When an OTLP endpoint is configured, the API exports request spans and accepts W3C
`traceparent` context. The Monitoring view's SLO snapshot uses the process-local
Prometheus registry and resets on API restart; durable multi-process SLO history needs
a Prometheus server or remote metrics backend.

Secrets are never baked into images. Compose reads `.env`; Kubernetes/ECS should use a
secret manager. Rotate `SECRET_KEY` invalidates existing tokens; rotate deployment API
keys per deployment.

## Database Migrations

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
docker compose exec backend alembic downgrade base   # destructive, dev only
```

The API does not auto-create tables in production. The entrypoint waits for PostgreSQL
and applies migrations (`scripts/entrypoint.sh`), which is safe for a single-node
deployment. For multiple replicas, run migrations as a separate job.

## AWS / S3 Artifact Storage

The artifact MAL is storage-backend agnostic:

```env
STORAGE_BACKEND=s3
S3_BUCKET=my-atlas-artifacts
S3_REGION=us-east-1
S3_ENDPOINT_URL=            # blank for AWS; set for MinIO
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
```

Use an IAM role/task role in production instead of static keys. Datasets and model
artifacts are addressed by platform-generated keys; downloads still stream through the
API so authorization and audit are preserved.

Optional MinIO profile (local S3-compatible testing):

```bash
docker compose --profile s3 up -d
```

MLflow artifacts remain on a persistent volume by default. To use S3 for MLflow, set
`--artifacts-destination s3://...` in the MLflow command and provide credentials; this
is documented as a deployment variant, not enabled by default to keep local setup
credential-free.

## Production Topology (single node)

- Reverse proxy (Nginx/ALB) terminating TLS to the frontend and API.
- 1–N API replicas, 1–N Celery workers, 1 Celery beat, MLflow, PostgreSQL, Redis.
- Managed PostgreSQL with backups/PITR; Redis with persistence.
- Artifacts on S3 with versioning and lifecycle rules.
- Prometheus scrapes `/metrics`; logs to stdout collected by the platform.
- Run migrations as a release step before deploying API replicas.
- Do not expose PostgreSQL, Redis, or the MLflow tracking port publicly; MLflow has no
  built-in auth in server mode (see SECURITY.md).

## GitHub Actions

`ci.yml` runs on push/PR:

1. `backend-lint`: Ruff.
2. `backend-tests`: pytest with a SQLite test DB and MLflow disabled.
3. `frontend-checks`: npm ci, lint, typecheck, tests, build.
4. `docker-build`: builds both images and validates `docker compose config`.

Deployment workflows (ECR push, ECS/Kubernetes rollout) are intentionally separate and
not included with credentials. Documented as a next step.

## Verification Checklist

- [ ] `.env` created from example, secrets changed.
- [ ] `docker compose up -d --build` healthy.
- [ ] `/ready` returns 200 and reports DB/storage.
- [ ] Alembic current revision matches head.
- [ ] MLflow UI reachable, backend logs "tracking enabled".
- [ ] Seed demo or register + upload.
- [ ] Training job transitions queued → running → completed.
- [ ] Model registered and deployed; prediction succeeds.
- [ ] Monitoring scan produces a stored result.
- [ ] Frontend all eight routes render with real data.
- [ ] `docker compose down && docker compose up -d` preserves data.

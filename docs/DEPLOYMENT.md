# Deployment runbook

## Local Compose

Use Docker Engine or Desktop with Compose v2.24.4 or newer. Allow roughly 5 GB of container memory for the full stack. For a low-resource workstation, use the SQLite quickstart in the [README](../README.md).

```bash
cp .env.example .env
# Set a different random hex value for SECRET_KEY and POSTGRES_PASSWORD.
CODE_REVISION=$(git rev-parse HEAD) docker compose up -d --build --wait
curl -fsS http://127.0.0.1:8000/ready
python3 scripts/compose_smoke.py
```

Compose binds the UI, API, MLflow, PostgreSQL, and Redis host ports to loopback. The smoke check uses the UI proxy on port 3000 and creates a test account. The production overlay unpublishes those ports and exposes Caddy on TCP 80 and 443, plus UDP 443.

## Public single-node installation

1. Point DNS at the host and set `DOMAIN`, `SECRET_KEY`, and `POSTGRES_PASSWORD` in `.env`. Use a separate random value for each secret. Use URL-safe characters for the database password because Compose embeds it in a connection URL.
2. For the initial account, temporarily set `ATLAS_PRODUCTION_ALLOW_REGISTRATION=true`. If the host is publicly reachable, restrict inbound access to the bootstrap operator during this window.
3. Build and start the overlay, register through the UI, then set `ATLAS_PRODUCTION_ALLOW_REGISTRATION=false` and recreate the backend with the same two Compose files.
4. Scrape telemetry only on the private network. Set `ATLAS_PRODUCTION_DOCS_ENABLED=true` explicitly if this host should expose interactive API docs.

```bash
CODE_REVISION=$(git rev-parse HEAD) docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
```

The API trusts the forwarded client address in this overlay. Keep the API and frontend private behind Caddy and allow only trusted services on the Compose network. The application rate limiter and model cache are process-local. Plan shared rate limiting, a separate migration job, scoped database accounts, and a tested backup and restore process before moving to multiple nodes or accepting high-risk workloads.

## Upgrading an existing installation

Back up PostgreSQL metadata and the artifact volume together. Inventory any existing MLflow data before switching the tracking server to its separate database, `atlas_mlflow` by default. A one-shot Compose service creates that database on both new and existing PostgreSQL volumes. Preserve prior tracking artifacts and their original location until you have migrated and verified the tracking data. Set a distinct database name for MLflow and Atlas.

The application images run as UID/GID 10001. Fresh managed volumes inherit the artifact directory ownership. For an existing root-owned volume, stop the stack, confirm the volume name, and back it up before giving the new application user ownership. Use the name reported by `docker volume ls` in place of the example below.

```bash
make docker-build
docker run --rm --user 0:0 --entrypoint chown \
  -v atlas-mlops_artifacts_data:/data/artifacts \
  atlas-backend:local -R 10001:10001 /data/artifacts
```

The API container runs `alembic upgrade head` before starting Uvicorn. Confirm the applied revision with `docker compose exec backend alembic current`. Back up before downgrading. Plain `docker compose down` preserves volumes. The `--volumes` option deletes them.

## Storage and model trust

For S3, pass `STORAGE_BACKEND=s3`, `S3_BUCKET`, optional `S3_REGION` and `S3_ENDPOINT_URL`, and credentials or workload identity to both the API and worker through a deployment override. Use a private bucket with workload-scoped access and object versioning. To move MLflow artifacts separately, set its `--artifacts-destination` and grant the tracking process access.

Atlas loads joblib models created by its own workers. Limit write access to the artifact store and registry database to trusted processes. A digest verifies that the stored artifact matches the registry record. A checksum provides no isolation from a compromised registry, storage writer, or training worker. Previously registered models retain their stored artifact locations and digests.

## Failure response

| Symptom | Check |
| --- | --- |
| `/ready` returns 503 | Inspect the named lifecycle, database, storage, or Redis check. Use `docker compose logs backend postgres redis` for context. |
| Training remains queued | Inspect `docker compose logs worker beat`. Beat reconciles older queued jobs and workers claim each job atomically. If a running worker is lost, stale-job recovery marks that run failed after the configured threshold. |
| Tracking warning in a completed run | Check `docker compose logs mlflow mlflow-db-init`, tracking URI, and MLflow artifact permissions. The Atlas experiment and registry remain available independently. |
| Prediction returns 503 or 504 | Check deployment status, verified model bytes, and inference worker saturation. A timed-out scoring thread holds its slot until it exits. Use the response's `X-Request-ID` to find its log. |
| Drift metrics are empty | Check `ENABLE_MONITORING_SCHEDULER`, beat logs, the deployment sample threshold, and availability of labels. Scrape `backend:8000/metrics` and `worker:9101/metrics` from the internal network. |
| Client tokens fail after rotation | A new `SECRET_KEY` invalidates existing JWTs. Sign in again after rolling the API to the new key. Deployment API keys have independent rotation. |

MLflow usage telemetry defaults to disabled in Atlas and its images.

The worker exporter aggregates Celery child-process counters. The API's SLO view is process-local, and its metrics reset on restart. Set `OTEL_EXPORTER_OTLP_ENDPOINT` for traces and collect JSON logs from both processes. Request logs carry `request_id`. Training logs carry `run_id` and the request ID when training came from an HTTP call.

## Reproducing the build

`backend/requirements.txt` contains direct pins. `backend/requirements.lock` contains Python 3.12 runtime pins and hashes. After changing requirements, regenerate it with the following command. Use `npm ci` to install exactly the frontend lockfile. Update Docker image tags and manifest digests together.

```bash
uv pip compile backend/requirements.txt --python-version 3.12 --universal --generate-hashes --output-file backend/requirements.lock
make setup
make lint typecheck test train-smoke audit
make docker-build
```

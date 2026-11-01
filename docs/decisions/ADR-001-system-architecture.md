# ADR-001: Modular Monolith with a Dedicated Worker

- Status: Accepted
- Date: 2026-11-01

## Context

The platform must run on a single machine via Docker Compose while still separating
long-running training from HTTP request handling. The specification warns against
premature distributed infrastructure. A pure monolith that trains inside request
handlers would violate the async requirement; a microservice-per-domain design would add
operational cost with no benefit at this scale.

## Decision

Build a modular monolith:

- One FastAPI service with internal layers (api → services → repositories → models, and
  an independent `ml` package).
- One background worker running the same application code (Celery in compose). A
  bounded thread executor is the local fallback, and a synchronous mode is used in
  tests.
- One React SPA served by Nginx, proxying `/api`.
- PostgreSQL and Redis as backing services; MLflow and artifact storage are supporting
  systems, not business services.

Boundaries are enforced by package structure and tests rather than network calls.

## Consequences

Positive:

- A single deployable artifact for API and worker minimizes drift.
- Transactions remain local; no distributed sagas.
- Local development works without Redis/Celery via thread mode.
- Clear extraction path: training could move to a dedicated service if scale demands.

Negative:

- API and worker share a deployment image and dependency set.
- In-memory caches and rate limits are process-local until Redis-backed.
- A misbehaving training process can affect the worker host (mitigated by Docker
  resource limits and bounded concurrency).

## Alternatives Considered

- **All-in-one synchronous API**: rejected — blocks requests, poor UX, violates the
  async requirement.
- **Microservices (datasets/training/registry/serving)**: rejected — network
  complexity, distributed tracing, and duplicated auth for a single-team deployment.
- **Managed MLOps SaaS**: rejected — the objective is to demonstrate building the
  platform, and the spec requires local reproducibility without cloud credentials.

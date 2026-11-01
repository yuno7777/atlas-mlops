# ADR-002: PostgreSQL as System of Record, MLflow for Run Metadata

- Status: Accepted
- Date: 2026-11-01

## Context

Two persistence concerns coexist:

1. Application entities (users, datasets, jobs, registry, deployments, predictions,
   drift) need relational integrity, authorization-friendly queries, and transactional
   updates.
2. Experiment parameters, metrics, artifacts, and run history are a specialized domain
   with an existing tool, MLflow.

Storing everything twice creates drift; storing app state only in MLflow limits
relational queries and authorization.

## Decision

- PostgreSQL is the single source of truth for all application entities. Normalized
  tables with explicit foreign keys, unique constraints, and indexes.
- MLflow is the source of truth for experiment run metadata and logged artifacts. The
  application stores only the `mlflow_run_id` and a link to its own experiment row.
- MLflow uses PostgreSQL for its backend store in compose (separate schema/database
  user recommended) and a persistent volume or S3 for artifacts.
- The app DB does **not** duplicate params/metrics from MLflow for display? It does
  snapshot metrics on the experiment row and again on model versions to keep lists and
  comparisons fast and available during MLflow outages. MLflow remains authoritative
  for run details; app snapshots are immutable records of what was accepted at
  registration.
- The model registry is DB-backed (see ADR-003), since MLflow 3 deprecated model
  registry stages and we require app-level lifecycle and deployment referential
  integrity.

## Consequences

Positive:

- Authorization and tenancy are relational and testable.
- Registry/deployment FKs prevent serving deleted artifacts.
- Dashboard queries are efficient without calling MLflow.
- If MLflow is down, training can still complete with a tracking warning; app history
  remains usable.

Negative:

- Metrics are intentionally duplicated (explained above) and must be written in one
  transaction after training.
- Two schemas to migrate/back up (app + MLflow).
- Compose must run migrations for both.

## Alternatives Considered

- **MLflow-only persistence**: rejected — cannot model workspaces, deployments,
  predictions, feedback, or drift results cleanly.
- **App-only tracking (no MLflow)**: rejected — spec requires proper MLflow integration
  and persistent experiment artifacts.
- **No metric snapshots**: rejected — list/compare endpoints would depend on MLflow
  availability and be slower; snapshot immutability is desirable for audit.

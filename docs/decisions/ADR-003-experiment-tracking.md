# ADR-003: Database-Backed Model Registry with MLflow Artifacts

- Status: Accepted
- Date: 2026-11-01

## Context

MLflow Model Registry historically provided versions, stages, and annotations. In
MLflow 3, registry stages are deprecated in favor of aliases, and the registry does not
integrate directly with our application entities (workspaces, deployments, audit,
promotion policy). The specification permits a documented DB-backed registry integrated
with MLflow artifacts.

## Decision

Implement the registry in the application database:

- `registered_models` (per project, unique name) and `model_versions` (immutable
  snapshots of experiment params/metrics, artifact copy, SHA-256, reference profile).
- Stages: `none`, `staging`, `production`, `archived`. Promotion is explicit and
  audited. Multiple production versions are allowed per model (deployment pinning
  decides what is actually serving); the UI makes this visible. This avoids silently
  demoting another version and breaking a deployment.
- On registration, the platform copies the trained artifact from the training key to a
  registry key, computes SHA-256, re-loads it once to verify integrity, and stores the
  reference profile.
- MLflow remains the experiment tracking/artifact history. The training run's MLflow
  artifact URI is recorded on the experiment; the registry copy is what serving uses.
- No MLflow model registry API calls are required for correctness. The integration is
  documented, and a future adapter could mirror versions to MLflow aliases.

## Consequences

Positive:

- Strong referential integrity with deployments and workspaces.
- Serving loads only platform-copied, hashed artifacts.
- Promotion policy and audit live where authorization lives.
- No dependency on deprecated MLflow stage APIs.

Negative:

- We own registry semantics (versioning, promotion, archive) rather than delegating.
- MLflow UI does not show registry stages for these models.
- Artifact bytes are stored twice (training + registry). Accepted for serving
  integrity; storage lifecycle rules can expire training artifacts later.

## Alternatives Considered

- **MLflow Model Registry only**: rejected — weak linkage to app tenancy/deployments and
  deprecated stages in MLflow 3.
- **Reference training artifacts directly**: rejected — experiments could be deleted or
  artifacts modified; serving requires an immutable, verified copy.

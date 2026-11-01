# ADR-004: In-Process Model Serving with a Managed Cache

- Status: Accepted
- Date: 2026-11-01

## Context

Deployments must expose low-latency prediction endpoints, support multiple model
versions, roll back, and avoid reloading models per request. Options:

1. One model server (e.g., MLServer/TorchServe) per deployment.
2. Load models into the API process with a bounded, versioned cache.
3. Proxy predictions to MLflow model serving.

Option 1 adds container orchestration, ports, and health management for every
deployment — too much for a single-node platform. Option 3 delegates serving to
MLflow's built-in server, which is not designed for multi-tenant lifecycle and adds a
network hop.

## Decision

Serve predictions from the FastAPI process through a managed `ModelCache`:

- Cache key: deployment id + model version id + artifact digest.
- LRU with a maximum size (default 8) and TTL (default 300s), guarded by an RLock and
  per-key load locks to avoid duplicate loads.
- Artifact existence and SHA-256 verified on load; failures mark deployment health
  unhealthy and return 503.
- Deployment stop/start, rollback, or version change invalidates relevant keys.
- Inference runs in a bounded thread pool so CPU-bound predict calls do not block the
  event loop.
- Every call writes a prediction log with latency and status.

## Consequences

Positive:

- Simple single-node operation, no per-deployment orchestration.
- Warm predictions are fast (no disk read).
- Rollback is immediate; caches are version-keyed.
- Integrity checks centralize the pickle trust boundary.

Negative:

- Each API replica has an independent cache (cold start per replica).
- A very large model can consume API memory; bounded cache size mitigates but does not
  isolate per-tenant memory.
- Scaling serving horizontally requires sticky routing or shared model cache/object
  storage. Documented scaling path: dedicated inference service.

## Alternatives Considered

- **Model server per deployment**: rejected — operational overhead, premature
  distributed infrastructure.
- **MLflow model serving proxy**: rejected — insufficient lifecycle, auth, and cache
  control.
- **No cache (load per request)**: rejected — unacceptable latency and disk churn.

# Testing Strategy

## Principles

- Tests assert observable behavior and invariants, not implementation details.
- ML tests train **real** estimators on small synthetic data; no mocked metrics.
- API tests run against a real FastAPI app, real SQLAlchemy models, real file storage,
  and the real training runner in synchronous mode.
- External MLflow is disabled in unit/integration tests for speed; a dedicated
  integration test exercises local MLflow when installed. Compose verification covers
  the server deployment.
- Every fixed bug gets a regression test.

## Test Layers

### Backend unit

| Area | What is verified |
|---|---|
| `ml/validation.py` | File signatures, size/type rejection, delimiter/encoding failures, schema checks, row caps |
| `ml/profiling.py` | Missing counts, duplicates, numeric/categorical stats, target suggestions |
| `ml/preprocessing.py` | Numeric/categorical splitting, imputation, unknown-category handling, leakage guard (transform before fit fails) |
| `ml/algorithms.py` | Catalog integrity, hyperparameter validation (unknown key, bounds, type) |
| `ml/training.py` | Classification/regression/clustering execution, metrics presence, determinism, invalid target, reference profile |
| `ml/drift.py` | PSI identical=0, shifted distribution high, KS sensitivity, categorical PSI, insufficient samples |
| `core/security.py` | bcrypt round-trip, JWT expiry/tamper rejection, API key hashing |
| `services/storage.py` | Path containment, checksum, local read/write/delete |
| `services/model_cache.py` | Cache hit, TTL expiry, invalidation, digest mismatch rejection |
| `services/monitoring.py` | Status computation, thresholds, concept drift gating, retraining trigger cooldown |

### Backend integration (API)

Fixtures: temporary SQLite DB (foreign keys ON), temp artifact root, synchronous job
execution, MLflow disabled, seeded demo user/project. Tests use `httpx` + FastAPI
`ASGITransport`.

- Auth: register, login, wrong password, expired/invalid token, duplicate email,
  password policy, rate limit on repeated failures.
- Tenancy: user B cannot read user A's project (404, not 403 leakage), viewer cannot
  mutate.
- Datasets: upload CSV/Parquet, profile values, versioning, preview limit, duplicate
  checksum, unsupported extension, oversized file, malformed CSV, download headers.
- Training: validation errors (bad target, mismatched algorithm), multi-algorithm job
  completion, experiments/metrics, comparison of same/different problem types, cancel
  before start, failure path.
- Registry: register version 1/2, unique experiment constraint, promotion, archive,
  download, cross-workspace denial.
- Deployments: create, API key returned once, health, stop/start, rollback revision,
  rotate key invalidates old key.
- Prediction: API-key and JWT auth, missing/unknown fields, batch limit, inactive
  deployment, real prediction values, prediction log, latency > 0, feedback, duplicate
  feedback handling, rate limit.
- Monitoring: insufficient data, drift after shifted inputs, prediction drift, concept
  drift with labels, result persistence, threshold effects, timeseries.
- Retraining: creates a job linked to deployment, uses newer dataset version, never
  auto-promotes; drift-triggered policy creates at most one job per cooldown.
- Overview: counts match inserted entities, no invented values.

### Backend end-to-end

`tests/test_e2e_workflow.py` performs the complete definition-of-done workflow through
HTTP endpoints with a real training runner:

1. Register → project.
2. Upload demo dataset.
3. Confirm ready + profile.
4. Create training job with two classification algorithms.
5. Verify both experiments completed with real metrics.
6. Compare; pick best.
7. Register; promote.
8. Deploy.
9. Predict normal records; submit labels.
10. Inject drifted records; run monitoring; assert data drift flag.
11. Trigger retraining; verify a challenger job completes.
12. Verify dashboard reflects the data.

SQLite is used for speed; the same test suite is run against PostgreSQL in the compose
verification job using `DATABASE_URL` overriding the test URL (documented command).

### Database tests

- Alembic upgrade from empty on SQLite and PostgreSQL.
- Unique constraints (dataset name/version, model version, deployment name).
- FK cascades (delete deployment → predictions/revisions/events/monitoring).
- Index existence smoke test via SQLAlchemy metadata.
- JSON round-trip for profiles and monitoring details.

### Frontend

Vitest + React Testing Library + jsdom:

- Design primitives: Button variants, Badge tones, EmptyState actions, form error.
- Formatters: metric formats, durations, relative time, latency.
- Status badge mapping (job/deployment/drift).
- API error normalization (envelope → message).
- A page-level test with mocked `fetch`: loading → data, empty state, error state.
- Train job form validation (target required, algorithms required).

ESLint and `tsc --noEmit` are treated as tests in CI.

Browser E2E (Playwright) is documented as a future enhancement; API-level E2E covers
the functional workflow in CI without browser flake. This is an explicit trade-off.

## Commands

```bash
# Backend (from backend/)
..\.venv\Scripts\python -m pytest -q
..\.venv\Scripts\ruff check app tests
..\.venv\Scripts\ruff format --check app tests

# Frontend (from frontend/)
npm test
npm run lint
npm run typecheck
npm run build

# Full stack
docker compose up -d --build
docker compose exec backend python -m pytest -q
```

## Fixtures and Determinism

- Synthetic datasets are generated in code with fixed seeds, not committed large files
  (except the demo CSV, generated by a deterministic script).
- Tests never depend on wall-clock ordering beyond explicit timestamps supplied in the
  fixture or tolerance windows.
- Drift tests use clearly separated distributions to avoid flakiness; KS p-values are
  checked directionally with a large effect size.
- Rate-limit tests reset limiter state between runs.

## Coverage Targets

- ML modules: ≥85% line coverage.
- Services: ≥75%.
- Overall backend: ≥70% (reported, not gated initially).
- Frontend: critical components and form logic covered; no vanity percentage target.

## Not Covered (documented)

- Multi-process concurrency and Celery failure injection.
- Browser rendering/e2e automation.
- Load tests beyond a modest smoke script.
- PyTorch tests run only when torch is installed (`pytest.mark.skipif`).

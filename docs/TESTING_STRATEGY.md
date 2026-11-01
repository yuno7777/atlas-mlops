# Testing Strategy

## Principles

- Tests assert observable behavior and invariants, not implementation details.
- ML tests train **real** estimators on small synthetic data; no mocked metrics.
- API tests run against a real FastAPI app, real SQLAlchemy models, real file storage,
  and the real training runner in synchronous mode.
- External MLflow is disabled in the automated test fixtures. The automated suite does
  not currently validate a live MLflow or PostgreSQL service.
- Every fixed bug gets a regression test.

## Test Layers

### Backend unit

| Area | What is verified |
|---|---|
| `ml/validation.py` | File signatures, size/type rejection, delimiter/encoding failures, schema checks, row caps |
| `ml/profiling.py` | Missing counts, duplicates, numeric/categorical stats, target suggestions |
| `ml/preprocessing.py` | Numeric/categorical splitting, missing-value imputation including pandas `pd.NA`, unknown-category handling, leakage guard (transform before fit fails) |
| `ml/algorithms.py` | Catalog integrity, hyperparameter validation (unknown key, bounds, type) |
| `ml/training.py` | Classification/regression/clustering execution, metrics presence, determinism, invalid target, reference profile |
| `ml/drift.py` | PSI identical=0, shifted distribution high, KS sensitivity, categorical PSI, insufficient samples |
| `core/security.py` | bcrypt round-trip, JWT expiry/tamper rejection, API key hashing |
| `services/storage.py` | Path containment, checksum, local read/write/delete |
| `services/model_cache.py` | Cache hit, TTL expiry, invalidation, digest mismatch rejection |
| `services/monitoring.py` | Status computation, thresholds, concept drift gating, retraining trigger cooldown |

### Backend integration (API)

Fixtures: temporary SQLite DB (foreign keys ON), temp artifact root, synchronous job
execution, MLflow disabled, seeded demo user/project. API tests use Starlette's
`TestClient` against the FastAPI app.

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
- Collaboration and alerting: create and accept a role-scoped invitation, update member
  role, verify workspace audit pagination, and create/update/test/delete a signed alert
  channel without making an external network request.
- Advanced deployment workflows: score and download a real batch CSV, explain a real
  model prediction, configure challenger traffic, and verify dataset-to-deployment
  lineage.
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

The automated suite uses SQLite for speed and isolation. PostgreSQL service and migration
checks are separate deployment checks; the current pytest fixture sets its SQLite URL
unconditionally.

### Database validation

The API tests exercise SQLAlchemy constraints indirectly while using the temporary
SQLite database. Playwright also applies all Alembic migrations to a fresh SQLite file
before starting the seeded browser-test server. PostgreSQL migration, FK cascade, and
explicit index inspection remain part of deployment acceptance, not the automated suite.
### Frontend

The frontend has no component unit-test runner. `npm run e2e` runs three Chromium
workflows against a temporary SQLite database and a locally started webhook receiver:

- Invitation creation, sign-in redirect, acceptance, and workspace audit filtering.
- Live prediction, feature explanation, batch CSV scoring/download, and challenger
  traffic setup.
- Alert webhook test delivery and project lineage navigation.

The test server runs `alembic upgrade head` against a clean database before seeding.
No external webhook endpoint is called. `npm run lint` (Oxlint), `npm run build`
(TypeScript checks plus Vite production build), and `npm run screenshots` are the other
frontend checks. Screenshot automation captures demo artifacts and is separate from
the browser regression suite.
## Commands

```bash
# Backend (from backend/)
..\.venv\Scripts\python -m pytest -q
..\.venv\Scripts\ruff check app tests
..\.venv\Scripts\ruff format --check app tests

# Frontend (from frontend/)
npm run lint
npm run build
npm run e2e
# With the API and seeded demo running, regenerate screenshot artifacts:
npm run screenshots

# Full stack
docker compose up -d --build
```
## Fixtures and Determinism

- The six benchmark CSVs in `demo-data/mock-benchmarks/` are committed and regenerated
  deterministically from fixed seeds; unit tests also use small in-memory synthetic data.
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
- Exhaustive browser regression coverage. Playwright covers the critical advanced
  workflows listed above, not every UI state or responsive breakpoint.
- Load tests beyond a modest smoke script.
- PyTorch tests run only when torch is installed (`pytest.mark.skipif`).

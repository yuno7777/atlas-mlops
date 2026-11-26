# Security

## Threat Model

Atlas is an internal MLOps platform for a trusted team on a single deployment. It still
defends against:

- Unauthenticated access to datasets, models, and predictions.
- Cross-workspace data access by authenticated users.
- Malicious uploads (oversized, wrong type, parser abuse).
- Path traversal via filenames or storage keys.
- API abuse and brute-force credential attempts.
- Accidental secret leakage in source/logs.

Out of scope for this iteration: multi-tenant isolation at the infrastructure level,
fine-grained per-resource ACLs, SSO/SAML/MFA, malware scanning, supply-chain attestation.

## Authentication

- Passwords hashed with bcrypt (cost 12). Minimum 10 characters; maximum 128 to avoid
  CPU abuse; common-password rejection is not implemented.
- JWT HS256, signed with `SECRET_KEY` (≥32 characters required in production), 12-hour
  expiry, `sub` = user id, `iat`, `exp`, `iss`, `aud`.
- Invalid/expired tokens → 401 with `WWW-Authenticate: Bearer`.
- Login/register rate-limited per IP + email. Multiple 401s remain generic
  ("invalid email or password") to avoid account enumeration.
- Registration is open by default. Set `ALLOW_REGISTRATION=false` and provision users
  via CLI for locked-down deployments.

## Authorization

- Every project-scoped operation resolves workspace membership.
- Roles: `owner`, `admin` (manage project/settings), `member` (datasets, training,
  registry, deployments), `viewer` (read-only).
- Data access uses scoped queries (`project_id` + membership), not post-filtering.
- Not-found responses are used for resources outside the caller's workspaces to avoid
  leaking existence.

## Prediction API

- External callers authenticate with `X-API-Key` scoped to one deployment.
- Keys are 32 random bytes (URL-safe), shown once, stored as SHA-256; prefix stored for
  display. Rotation invalidates the old key immediately.
- Per-deployment in-memory rate limit (default 120 req/min); 429 with `Retry-After`.
- Input limits: max 1000 records per request, max 1000 fields per request, value depth
  bounded by JSON parser; non-finite numbers rejected.
- Only values matching the model schema are accepted; unknown keys fail closed.
- Prediction logs may contain customer feature data. The UI masks logs by default;
  operators should configure retention and access accordingly. `PREDICTION_LOG_FEATURES`
  can be disabled at the deployment level in a future iteration (documented limitation).

## File Upload and Artifacts

- Extension + declared MIME + sniffed content checks for CSV/Parquet/JSON.
- `MAX_UPLOAD_MB` enforced while streaming to a temp file (not only via Content-Length).
- Filenames are sanitized for display; storage keys are generated server-side (UUID
  based). Path containment is checked with `Path.resolve()` and `is_relative_to`.
- Parsing uses pandas defaults; CSV formula injection is not relevant to storage, but
  exported previews escape cell values in the UI.
- Model artifacts are only loaded from platform-generated registry keys. A SHA-256 is
  recorded at registration and verified before deserialization.
- **Trust boundary:** joblib uses pickle. The platform never loads user-uploaded
  pickle/model files; only artifacts produced by its own training workers. This must be
  preserved in future import features. Model downloads are authorized and audited.

## Web Security

- CORS restricted to configured origins; credentials disabled (bearer tokens).
- Security headers set by Nginx/API middleware: CSP, X-Content-Type-Options,
  X-Frame-Options/frame-ancestors, Referrer-Policy, Permissions-Policy.
- JWT stored in `localStorage` for this SPA. Trade-off: simpler cross-origin setup, but
  XSS would expose the token. The CSP and React escaping mitigate; HttpOnly cookie
  sessions are the recommended next hardening step.
- All user text is rendered through React (escaped); no `dangerouslySetInnerHTML`.
- OpenAPI docs are enabled by default for demos; disable in locked environments.

## Alert deliveries

Production alert targets must use an administrator-approved HTTPS hostname on port 443.
Delivery never follows redirects. Configure `ALERT_WEBHOOK_ALLOWED_HOSTS` on both the API
and worker, and restrict their network egress as appropriate for the deployment.

## Database

- Parameterized queries via SQLAlchemy ORM; no string-built SQL.
- Alembic migrations, no runtime auto-create in production.
- Least-privilege DB user recommended; Compose uses a dedicated app database.
- JSON fields are treated as data and validated by Pydantic on write.

## Audit Logging

Events include actor, workspace, action, resource, IP, and non-sensitive metadata for:
registration/login, dataset upload/download/delete, training create/cancel/retrain,
model registration/promotion/archive/download, deployment create/start/stop/rollback/key
rotation, monitoring scan, feedback ingestion. Secrets and full feature payloads are
never written to audit metadata.

## Secrets Management

- `.env` ignored; `.env.example` contains placeholders only.
- Container database and signing credentials are provided at runtime. CI generates and masks ephemeral credentials.
- MLflow server in compose has no auth; it is bound to localhost/network-internal only.
  Production must front it with an authenticating proxy or private networking.
- Rotate `SECRET_KEY`, database passwords, S3 credentials, and deployment keys on
  exposure.

## Reliability Controls

- Training jobs have bounded upload sizes and algorithm/hyperparameter validation.
- Batch prediction limit and bounded inference concurrency.
- Graceful shutdown: API stops accepting requests; worker finishes the current algorithm
  or reports the job as failed after restart (startup recovery for stale jobs).
- Structured logs include request ids and never log tokens/passwords.
- Dependency versions pinned; CI runs lint/tests; images run as non-root.

## Known Limitations

1. In-memory rate limiting is per process; use Redis for multi-replica deployments.
2. No refresh-token rotation or server-side token revocation.
3. No MFA/SSO.
4. CI audits locked Python and npm dependencies. Scanning operating-system packages in the container images is a separate control.
5. MLflow server has no built-in authentication; keep it private.
6. Joblib/pickle artifacts remain a trusted-artifact boundary.
7. No per-field data classification/redaction beyond UI masking.

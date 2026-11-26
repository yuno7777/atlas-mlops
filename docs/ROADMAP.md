# Atlas delivery goal

A clean Windows or Linux checkout can run the same local training and serving
workflow. The production deployment can recover from interrupted jobs, release
models deliberately, and be restored from backup.

| Milestone | Work | Acceptance |
| --- | --- | --- |
| 1. Native Windows and Linux | Shared Python commands, environment diagnostics, native SQLite and thread-worker mode, portable storage writes, native CI and browser coverage. | Both runners install from locks, migrate, train on the same fixture, register a model, and predict over HTTP. A user can start the UI and API from one command. |
| 2. Durable training | Transactional dispatch, worker leases and heartbeats, fencing for expired attempts, bounded retries, stage resume, deadlines, priorities, and project resource budgets. | Crash tests cover failure before publish, during training, and during registration. Only one attempt publishes a version, and unfinished work becomes terminal or eligible to retry. |
| 3. Data and experiments | Versioned dataset contracts, schema changes, quality and leakage checks, streaming ingestion, group and time splits, baseline comparisons, calibration, subgroup checks, tuning, and scheduled retraining. | Invalid data is rejected with row-level guidance. A recorded dataset and split can reproduce the evaluation on either OS. Retraining produces an auditable candidate. |
| 4. Serving and releases | Immutable release manifests, approval gates, shadow inference, resumable batch scoring, signed artifacts, retention, ONNX parity where supported, quotas, and cache budgets. | A trained candidate can be shadow-tested, approved, rolled out, and rolled back. Tampered artifacts fail closed and interrupted batch runs can resume. |
| 5. Platform operations | Operator dashboards, drift investigation, alert deduplication, SDKs, UI timelines and dataset diff, scoped credentials, retention and redaction, backup and restore drills, SBOMs, image scanning, and upgrade checks. | Operators can diagnose a stuck run, restore models and metadata to a fresh deployment, and validate security and availability checks on a release. |

Milestone 2 includes transactional dispatch, execution leases, heartbeats, a bounded
worker-loss retry, and reuse of completed algorithm runs. Regression coverage includes
failure after commit, lost broker messages, competing dispatchers, loss during fitting,
cancellation, and rollback when ownership expires during registration. Next are
per-job deadlines and retry policies, queue priorities, per-project resource limits,
and failure drills against the deployed broker and worker.

Native Windows and Linux runs use SQLite, local artifacts, and the thread worker.
The Linux Compose profile keeps PostgreSQL, Redis, Celery, MLflow, and the production
images. Changes that affect the API, database, or artifact contract should exercise
both execution profiles.

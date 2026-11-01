# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is pre-1.0.

## [Unreleased]

### Added

- Workspace invitations, member role changes, paginated workspace audit events, and
  project-level dataset-to-deployment lineage.
- Alert destination management for Slack-compatible and generic webhook channels,
  including HMAC signing and test delivery.
- CSV batch prediction jobs with stored result files and download endpoints.
- Per-record Monte Carlo permutation Shapley explanations.
- Champion/challenger deployment traffic controls and variant logging.
- Settings workflows for invitations, member roles, audit filters, and alert channels.
- Deployment views for batch scoring, challenger traffic, and prediction explanations.
- A project lineage view linking datasets, training, experiments, model versions, and deployments.
- Playwright browser coverage for invitation acceptance, prediction workflows, alerts, and lineage.
- Six reproducible synthetic benchmark datasets (18,000 rows total) and scripts for upload,
  training, cross-validation, experiment comparison, and metric reports.
- Progressive deployment rollouts with configurable sample, error-rate, latency,
  labeled-quality, and regression gates; failed gates return traffic to the champion.
- Held-out subgroup fairness metrics and generated JSON/Markdown model cards.
- Reusable workflow runs with retry lineage, exact-result caching, one-time scheduling,
  and popular classification, regression, and clustering benchmark recipes.
- A Benchmark Lab page for recipe selection, comparable model scores, CV mean/spread,
  training duration, fairness summaries, and prior multi-model results.
- Optional OTLP/HTTP request tracing with W3C trace propagation and an in-process SLO
  snapshot for availability and latency.

### Changed

- Demo screenshots now use 3x capture resolution, larger UI scale, and the seeded
  Customer Churn workspace, including a real prediction playground result.
- The screenshot runner selects the custom project switcher and an existing deployment,
  and accepts `ATLAS_BASE_URL` for local preview ports.
- The browser favicon uses the Atlas four-tile brand mark instead of the Vite template icon.
- Categorical preprocessing converts pandas `pd.NA` to scikit-learn-compatible missing
  values, so categorical imputation works during training and inference.
- API, schema, README, and implementation-plan documentation now cover the rollout,
  fairness, model-card, benchmark-workflow, and tracing/SLO contracts.

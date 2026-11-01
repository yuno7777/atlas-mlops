# ML Pipeline

## Goals

- One reusable path for every algorithm and problem type.
- No data leakage: all imputers/encoders/scalers are fit **inside** a scikit-learn
  `Pipeline` on training data only.
- Deterministic given a seed.
- Independently testable: preprocessing, training, evaluation, and drift are pure
  modules with dataframe/array inputs.

## Stages

```text
load → validate schema → clean target → infer feature types → split
     → Pipeline(fit) → predict → evaluate → optional CV
     → persist artifact + reference profile → MLflow log → register (optional)
```

### 1. Loading

- Dataset artifacts are CSV/Parquet/JSON, stored under the platform artifact root.
- Loading is streaming-free but size-limited at upload; profile uses sampling caps.
- Parquet is read from the local buffer/path. CSV uses UTF-8 with a fallback error
  message (no silent encoding guessing).

### 2. Schema validation

- Target must exist and not be all-null.
- For classification: target cardinality must be 2–50; a single class is rejected.
- For regression: target must be numeric or safely coercible; rows with unparseable
  targets are dropped and counted in the job log.
- Feature columns default to all columns except target; explicit selections are
  validated. Columns with 100% missing values are dropped with a warning.
- Clustering has no target; the target field is ignored.

### 3. Cleaning

- Drop rows where the target is missing.
- Trim whitespace in object columns; normalize empty strings to null.
- Do not impute the target.
- Cast boolean strings as categorical.

### 4. Preprocessing

```text
ColumnTransformer
├── numeric: SimpleImputer(median) → StandardScaler
└── categorical: SimpleImputer(most_frequent)
                → OneHotEncoder(handle_unknown="ignore", min_frequency=...)
```

- Numeric = int/float/bool-like numeric columns.
- Categorical = object/category/string/bool.
- Datetime columns are converted to ordinal seconds; high-cardinality IDs are kept only
  if explicitly selected (documented risk).
- The full transformer + estimator is one pipeline, serialized as one artifact.

### 5. Split and training

- Default hold-out: 80/20 (`test_size` configurable 0.10–0.40), `random_state` from the
  request.
- Stratified split for classification when the smallest class has ≥2 members.
- Clustering: fit on the training split; metrics on the held-out split.
- Cross-validation (optional, 2–10 folds) runs on the training split only.
- Random seed applies to split, estimators with randomness, and CV.

### 6. Algorithms

| ID | Label | Problem | Notable hyperparameters |
|---|---|---|---|
| logistic_regression | Logistic Regression | classification | C (0.001–100), max_iter |
| random_forest_classifier | Random Forest | classification | n_estimators (10–1000), max_depth, min_samples_split |
| decision_tree_classifier | Decision Tree | classification | max_depth, min_samples_split |
| gradient_boosting_classifier | Gradient Boosting | classification | n_estimators, learning_rate, max_depth |
| svm_classifier | Support Vector Machine | classification | C, kernel (rbf/linear), gamma |
| knn_classifier | K-Nearest Neighbors | classification | n_neighbors (1–50), weights |
| linear_regression | Linear Regression | regression | fit_intercept |
| ridge_regression | Ridge Regression | regression | alpha (1e-6–1000) |
| random_forest_regressor | Random Forest | regression | n_estimators, max_depth |
| gradient_boosting_regressor | Gradient Boosting | regression | n_estimators, learning_rate |
| svr | Support Vector Regression | regression | C, epsilon, kernel |
| kmeans | K-Means | clustering | n_clusters (2–50), n_init |
| dbscan | DBSCAN | clustering | eps (0.01–100), min_samples |
| mlp_torch | PyTorch MLP (optional) | classification | hidden_dim, epochs (1–200), learning_rate |

Hyperparameters are validated against a per-algorithm schema (allowed keys, numeric
bounds, choices). Unknown keys are rejected, not silently ignored.

**PyTorch implementation:** a small `torch.nn.Sequential` classifier wrapped as a
scikit-learn-compatible estimator (`fit/predict/predict_proba`). It trains on the
transformed feature matrix with Adam + cross-entropy, batches, seeded initialization,
and early stopping on a validation split. It is included in the catalog only when
`torch` is importable; the Dockerfile has an optional build arg.

### 7. Metrics

| Problem | Metrics | Direction |
|---|---|---|
| classification | accuracy, precision_weighted, recall_weighted, f1_weighted, roc_auc (OVR, when probabilities available) | max |
| regression | rmse, mae, r2 | rmse/mae min, r2 max |
| clustering | silhouette, davies_bouldin, calinski_harabasz | silhouette/CH max, DB min |

Only relevant metrics are returned. Additional data: samples (train/test), classes,
feature counts, duration.

### 8. Reference profile (for drift)

Computed from the **training split raw features** and test predictions:

- numeric: decile bin edges + bin proportions, mean/std, missing rate
- categorical: top 20 frequencies + other bucket, missing rate
- predictions: class distribution (classification) or 20 quantiles (regression)
- performance: test metrics baseline
- schema: exact feature names and types expected by the served pipeline

Stored as JSON next to the model and copied into the model version row. Serving accepts
only keys in this schema.

### 9. Artifacts

- `model.joblib` — full fitted pipeline.
- `reference_profile.json` — drift baseline + expected schema.
- MLflow run logs params, metrics, tags (`job_id`, `dataset_version_id`, `project_id`),
  and the model artifact; MLflow is not used as the system of record for app entities.

### 10. Failure semantics

- Any algorithm failure is caught, recorded on its experiment, and logged; other
  algorithms continue.
- The job fails only if no algorithm completes.
- An artifact is only considered valid if joblib serialization succeeded and the saved
  file can be re-loaded once in-process (sanity check). The registry then copies and
  hashes it.

## Prediction Path

1. Validate deployment active and API key/JWT.
2. Load cached pipeline (verify artifact existence + digest).
3. Validate record keys against the schema; reject unknown keys and missing features.
4. Coerce values to expected dtypes (numeric → float, categorical → string); reject
   non-coercible values with field-level errors.
5. `pipeline.predict` in a thread pool for CPU-bound inference (bounded concurrency).
6. Build classification probabilities when supported; otherwise omit.
7. Persist prediction log with latency; update deployment `last_request_at`.
8. Return predictions.

Inference is synchronous per request but off the event loop. Batch size is limited to
1000 to bound latency and memory.

## Drift Methods

- **PSI**: proportional distributions over reference bins; `sum((a-b) * ln(a/b))` with
  epsilon smoothing. Numeric bins come from reference deciles; categorical buckets from
  reference top values + other.
- **KS**: `scipy.stats.ks_2samp` for numeric features; reported with p-value.
- **Prediction drift**: PSI between recent predicted labels (classification) or
  binned predictions (regression) and baseline test predictions.
- **Concept drift**: requires labels. Compute accuracy/f1 (classification) or
  RMSE/MAE (regression) over labeled recent predictions; compare to baseline.
  If labels are insufficient, report `detected: false` with a reason — never infer
  concept drift from unlabeled data.

Threshold defaults (per deployment): PSI > 0.2 (feature drift), drift share > 0.3
(overall), performance degradation > 15% relative, minimum 30 samples.

## Determinism and Reproducibility

- Seeds are recorded in experiment params.
- Library versions are logged to MLflow tags.
- Dataset version + checksum are linked to each experiment.
- The demo generator uses a fixed seed.

# Synthetic model benchmarks

These CSV files are deterministic synthetic data for exercising Atlas dataset
profiling, preprocessing, training, cross-validation, and experiment comparison.
They are not copied from real people or organizations and are not suitable for
operational decisions.

The generator creates six datasets with 3,000 rows each:

| Dataset | Task | Target | Rows | Description |
|---|---|---|---:|---|
| SaaS Customer Churn | Classification | `churned` | 3,000 | Subscription, usage, support, and billing signals |
| Loan Repayment Risk | Classification | `defaulted` | 3,000 | Credit utilization, affordability, loan, and repayment history |
| E-commerce Conversion | Classification | `converted` | 3,000 | Session, cart, channel, device, and return-visit signals |
| Retail Demand Forecast | Regression | `units_sold` | 3,000 | Pricing, promotions, inventory, store, calendar, and category signals |
| Delivery ETA Forecast | Regression | `eta_minutes` | 3,000 | Distance, traffic, weather, package, area, and driver signals |
| Used Vehicle Prices | Regression | `sale_price` | 3,000 | Age, mileage, condition, features, and vehicle segment signals |

The numeric and categorical features include a small amount of missing data on
purpose. Atlas keeps these source CSVs unchanged. Its training pipeline fits the
preprocessing separately inside each training split: numeric columns use median
imputation and standard scaling; categorical columns use most-frequent imputation
and one-hot encoding. That keeps preprocessing leakage out of the held-out test
set and each cross-validation fold.

Regenerate the CSVs and the manifest with:

```powershell
..\.venv\Scripts\python.exe demo-data\generate_mock_datasets.py
```

Upload them to the local Atlas instance, train two models per dataset, run a
stratified 3-fold (classification) or 3-fold (regression) cross-validation, and
write the metrics report with:

```powershell
..\.venv\Scripts\python.exe demo-data\run_mock_benchmarks.py
```

The run creates a dedicated `Synthetic Model Benchmarks` project in the demo
workspace. Results are written to `benchmark_results.json`,
`benchmark_results.csv`, and `benchmark_summary.md` in this directory.

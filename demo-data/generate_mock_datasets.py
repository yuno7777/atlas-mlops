"""Generate reproducible tabular benchmarks for the Atlas MLOps demo."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parent / "mock-benchmarks"
ROWS = 3_000


def _sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(value, -30, 30)))


def _missing_values(
    frame: pd.DataFrame, rng: np.random.Generator, rate: float = 0.018
) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if column in {
            "churned",
            "defaulted",
            "converted",
            "units_sold",
            "eta_minutes",
            "sale_price",
        }:
            continue
        mask = rng.random(len(output)) < rate
        output.loc[mask, column] = np.nan
    return output


def _saas_churn(seed: int) -> tuple[pd.DataFrame, str, str]:
    rng = np.random.default_rng(seed)
    n = ROWS
    tenure = rng.integers(1, 73, n)
    fee = np.clip(rng.normal(74, 22, n), 18, 160)
    logins = np.clip(rng.poisson(12, n), 0, 50)
    tickets = np.clip(rng.poisson(1.1, n), 0, 12)
    usage_change = np.clip(rng.normal(2, 23, n), -80, 100)
    contract = rng.choice(["monthly", "annual", "two_year"], n, p=[0.58, 0.29, 0.13])
    payment = rng.choice(
        ["card", "bank_transfer", "invoice", "wallet"], n, p=[0.48, 0.25, 0.17, 0.10]
    )
    tier = rng.choice(["starter", "growth", "enterprise"], n, p=[0.50, 0.37, 0.13])
    autopay = rng.choice(["yes", "no"], n, p=[0.63, 0.37])
    score = (
        -1.75
        + 1.0 * (contract == "monthly")
        - 0.7 * (contract == "two_year")
        + 0.014 * (fee - 70)
        - 0.035 * (tenure - 24)
        + 0.37 * tickets
        - 0.045 * logins
        - 0.012 * usage_change
        + 0.38 * (autopay == "no")
        + 0.25 * (tier == "starter")
    )
    churned = np.where(rng.random(n) < _sigmoid(score), "yes", "no")
    frame = pd.DataFrame(
        {
            "tenure_months": tenure,
            "monthly_fee_usd": np.round(fee, 2),
            "logins_last_30d": logins,
            "support_tickets_last_90d": tickets,
            "usage_change_pct": np.round(usage_change, 1),
            "contract_type": contract,
            "payment_method": payment,
            "customer_tier": tier,
            "autopay": autopay,
            "churned": churned,
        }
    )
    return _missing_values(frame, rng), "churned", "classification"


def _loan_default(seed: int) -> tuple[pd.DataFrame, str, str]:
    rng = np.random.default_rng(seed)
    n = ROWS
    utilization = np.clip(rng.beta(2.1, 2.4, n), 0, 1)
    dti = np.clip(rng.beta(2.0, 3.8, n), 0, 1)
    income = np.clip(rng.lognormal(np.log(68_000), 0.52, n), 18_000, 260_000)
    loan = np.clip(rng.lognormal(np.log(16_000), 0.58, n), 1_000, 80_000)
    delinquencies = np.clip(rng.poisson(0.55, n), 0, 7)
    employment = rng.integers(0, 31, n)
    savings = np.clip(rng.gamma(2.2, 3.8, n), 0, 48)
    purpose = rng.choice(
        ["debt_consolidation", "vehicle", "home_improvement", "education", "other"],
        n,
        p=[0.35, 0.22, 0.19, 0.12, 0.12],
    )
    term = rng.choice([36, 48, 60, 72], n, p=[0.18, 0.25, 0.47, 0.10])
    score = (
        -2.05
        + 2.15 * utilization
        + 2.7 * dti
        + 0.48 * delinquencies
        - 0.045 * employment
        - 0.07 * savings
        + 0.000012 * (loan - income * 0.20)
        + 0.30 * (purpose == "debt_consolidation")
        + 0.15 * (term >= 60)
    )
    defaulted = np.where(rng.random(n) < _sigmoid(score), "yes", "no")
    frame = pd.DataFrame(
        {
            "credit_utilization": np.round(utilization, 3),
            "debt_to_income_ratio": np.round(dti, 3),
            "annual_income_usd": np.round(income, 2),
            "requested_loan_usd": np.round(loan, 2),
            "prior_delinquencies": delinquencies,
            "employment_years": employment,
            "liquid_savings_months": np.round(savings, 1),
            "loan_purpose": purpose,
            "term_months": term,
            "defaulted": defaulted,
        }
    )
    return _missing_values(frame, rng), "defaulted", "classification"


def _ecommerce_conversion(seed: int) -> tuple[pd.DataFrame, str, str]:
    rng = np.random.default_rng(seed)
    n = ROWS
    pages = np.clip(rng.poisson(6, n) + 1, 1, 35)
    duration = np.clip(rng.gamma(2.3, 85, n), 5, 1_800)
    cart_value = np.where(rng.random(n) < 0.36, rng.gamma(2.0, 34, n), 0)
    visits = np.clip(rng.poisson(3.2, n), 0, 25)
    discount = np.clip(rng.normal(8, 11, n), 0, 60)
    channel = rng.choice(
        ["organic", "paid_search", "email", "social", "affiliate"],
        n,
        p=[0.34, 0.24, 0.16, 0.17, 0.09],
    )
    device = rng.choice(["mobile", "desktop", "tablet"], n, p=[0.62, 0.32, 0.06])
    category = rng.choice(["home", "electronics", "apparel", "beauty", "outdoors"], n)
    returning = rng.choice(["yes", "no"], n, p=[0.43, 0.57])
    hour = rng.integers(0, 24, n)
    score = (
        -2.35
        + 0.08 * pages
        + 0.0015 * duration
        + 0.010 * discount
        + 0.30 * visits
        + 0.85 * (cart_value > 0)
        + 0.52 * (returning == "yes")
        + 0.32 * (channel == "email")
        + 0.16 * (channel == "organic")
        - 0.32 * (device == "mobile")
        + 0.12 * ((hour >= 18) | (hour <= 1))
    )
    converted = np.where(rng.random(n) < _sigmoid(score), "yes", "no")
    frame = pd.DataFrame(
        {
            "pages_viewed": pages,
            "session_seconds": np.round(duration, 1),
            "cart_value_usd": np.round(cart_value, 2),
            "visits_last_30d": visits,
            "discount_pct": np.round(discount, 1),
            "marketing_channel": channel,
            "device_type": device,
            "product_category": category,
            "returning_customer": returning,
            "local_hour": hour,
            "converted": converted,
        }
    )
    return _missing_values(frame, rng), "converted", "classification"


def _retail_demand(seed: int) -> tuple[pd.DataFrame, str, str]:
    rng = np.random.default_rng(seed)
    n = ROWS
    price = np.clip(rng.normal(34, 13, n), 4, 120)
    promotion = rng.choice([0, 1], n, p=[0.68, 0.32])
    ad_spend = np.clip(rng.gamma(2, 75, n), 0, 900)
    stock = np.clip(rng.normal(90, 36, n), 5, 260)
    weekday = rng.choice(["mon", "tue", "wed", "thu", "fri", "sat", "sun"], n)
    season = rng.choice(["winter", "spring", "summer", "fall"], n)
    category = rng.choice(["grocery", "home", "electronics", "apparel", "personal_care"], n)
    store_size = rng.choice(["small", "medium", "large"], n, p=[0.28, 0.49, 0.23])
    seasonal_lift = np.select([season == "winter", season == "summer"], [8, 5], default=0)
    category_lift = np.select(
        [category == "grocery", category == "electronics"], [18, -7], default=0
    )
    weekday_lift = np.where(np.isin(weekday, ["sat", "sun"]), 13, 0)
    expected = (
        42
        + 0.035 * stock
        - 0.42 * price
        + 24 * promotion
        + 0.055 * ad_spend
        + seasonal_lift
        + category_lift
        + weekday_lift
        + 12 * (store_size == "large")
        + 5 * (store_size == "medium")
    )
    units = np.maximum(0, expected + rng.normal(0, 13, n)).round().astype(int)
    frame = pd.DataFrame(
        {
            "unit_price_usd": np.round(price, 2),
            "promotion_active": promotion,
            "ad_spend_usd": np.round(ad_spend, 2),
            "inventory_available": stock.round().astype(int),
            "weekday": weekday,
            "season": season,
            "product_category": category,
            "store_size": store_size,
            "units_sold": units,
        }
    )
    return _missing_values(frame, rng), "units_sold", "regression"


def _delivery_eta(seed: int) -> tuple[pd.DataFrame, str, str]:
    rng = np.random.default_rng(seed)
    n = ROWS
    distance = np.clip(rng.gamma(2.2, 5, n), 0.5, 45)
    traffic = rng.integers(0, 101, n)
    weather = rng.choice(["clear", "rain", "snow", "windy"], n, p=[0.69, 0.20, 0.04, 0.07])
    vehicle = rng.choice(["bike", "car", "van", "scooter"], n, p=[0.18, 0.42, 0.22, 0.18])
    hour = rng.integers(0, 24, n)
    queue = np.clip(rng.gamma(1.7, 3.5, n), 0, 40)
    weight = np.clip(rng.gamma(2.0, 2.2, n), 0.1, 30)
    urban = rng.choice(["urban", "suburban", "rural"], n, p=[0.54, 0.33, 0.13])
    experience = rng.integers(0, 16, n)
    weather_penalty = np.select(
        [weather == "rain", weather == "snow", weather == "windy"],
        [8, 20, 4],
        default=0,
    )
    vehicle_penalty = np.select([vehicle == "bike", vehicle == "van"], [-4, 5], default=0)
    peak_penalty = np.where(np.isin(hour, [7, 8, 9, 16, 17, 18]), 8, 0)
    eta = (
        8
        + 2.15 * distance
        + 0.12 * traffic
        + weather_penalty
        + vehicle_penalty
        + peak_penalty
        + 0.65 * queue
        + 0.28 * weight
        - 0.35 * experience
        + 5 * (urban == "rural")
        + 2 * (urban == "suburban")
        + rng.normal(0, 5, n)
    )
    frame = pd.DataFrame(
        {
            "distance_km": np.round(distance, 2),
            "traffic_index": traffic,
            "weather": weather,
            "vehicle_type": vehicle,
            "pickup_hour": hour,
            "pickup_queue_minutes": np.round(queue, 1),
            "package_weight_kg": np.round(weight, 2),
            "area_type": urban,
            "driver_experience_years": experience,
            "eta_minutes": np.maximum(5, eta).round(1),
        }
    )
    return _missing_values(frame, rng), "eta_minutes", "regression"


def _vehicle_prices(seed: int) -> tuple[pd.DataFrame, str, str]:
    rng = np.random.default_rng(seed)
    n = ROWS
    age = rng.integers(0, 19, n)
    mileage = np.maximum(
        500, (age * rng.normal(13_500, 3_300, n) + rng.normal(8_000, 12_000, n))
    ).astype(int)
    engine = rng.choice([1.2, 1.5, 1.8, 2.0, 2.5, 3.0], n, p=[0.10, 0.22, 0.26, 0.22, 0.14, 0.06])
    owners = rng.choice([1, 2, 3, 4], n, p=[0.47, 0.33, 0.15, 0.05])
    accident = rng.choice(["none", "minor", "major"], n, p=[0.78, 0.17, 0.05])
    brand = rng.choice(["value", "mainstream", "premium"], n, p=[0.28, 0.58, 0.14])
    transmission = rng.choice(["automatic", "manual"], n, p=[0.71, 0.29])
    fuel = rng.choice(["petrol", "diesel", "hybrid", "electric"], n, p=[0.49, 0.28, 0.16, 0.07])
    condition = rng.choice(["fair", "good", "excellent"], n, p=[0.20, 0.56, 0.24])
    brand_lift = np.select([brand == "premium", brand == "mainstream"], [12_000, 4_000], default=0)
    fuel_lift = np.select([fuel == "hybrid", fuel == "electric"], [2_500, 4_500], default=0)
    accident_penalty = np.select(
        [accident == "minor", accident == "major"], [2_000, 7_000], default=0
    )
    condition_lift = np.select(
        [condition == "excellent", condition == "fair"], [2_500, -2_000], default=0
    )
    price = (
        30_000
        - 1_450 * age
        - 0.085 * mileage
        + 1_500 * (engine - 1.5)
        - 1_150 * (owners - 1)
        + brand_lift
        + fuel_lift
        - accident_penalty
        + condition_lift
        + 1_600 * (transmission == "automatic")
        + rng.normal(0, 2_700, n)
    )
    frame = pd.DataFrame(
        {
            "vehicle_age_years": age,
            "mileage_km": mileage,
            "engine_liters": engine,
            "previous_owners": owners,
            "accident_history": accident,
            "brand_segment": brand,
            "transmission": transmission,
            "fuel_type": fuel,
            "condition": condition,
            "sale_price": np.maximum(1_200, price).round(2),
        }
    )
    return _missing_values(frame, rng), "sale_price", "regression"


DATASETS = [
    ("SaaS Customer Churn", "saas_churn.csv", 11_101, _saas_churn),
    ("Loan Repayment Risk", "loan_repayment.csv", 22_202, _loan_default),
    (
        "E-commerce Conversion",
        "ecommerce_conversion.csv",
        33_303,
        _ecommerce_conversion,
    ),
    ("Retail Demand Forecast", "retail_demand.csv", 44_404, _retail_demand),
    ("Delivery ETA Forecast", "delivery_eta.csv", 55_505, _delivery_eta),
    ("Used Vehicle Prices", "used_vehicle_prices.csv", 66_606, _vehicle_prices),
]


def generate() -> list[dict[str, object]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for name, filename, seed, builder in DATASETS:
        frame, target, problem_type = builder(seed)
        path = OUT_DIR / filename
        frame.to_csv(path, index=False)
        missing_cells = int(frame.isna().sum().sum())
        target_summary: dict[str, object]
        if problem_type == "classification":
            target_summary = {
                str(label): round(float(share), 4)
                for label, share in frame[target].value_counts(normalize=True).sort_index().items()
            }
        else:
            target_summary = {
                "min": round(float(frame[target].min()), 2),
                "median": round(float(frame[target].median()), 2),
                "max": round(float(frame[target].max()), 2),
            }
        manifest.append(
            {
                "name": name,
                "filename": filename,
                "seed": seed,
                "rows": len(frame),
                "columns": len(frame.columns),
                "problem_type": problem_type,
                "target": target,
                "missing_feature_cells": missing_cells,
                "target_summary": target_summary,
                "size_bytes": path.stat().st_size,
            }
        )
        print(
            f"Generated {path.name}: {len(frame):,} rows, {len(frame.columns)} columns, target={target}"
        )
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    generate()

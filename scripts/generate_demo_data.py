"""Generate the deterministic synthetic customer-churn dataset used in demos."""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "demo-data" / "customer_churn.csv"


def main() -> None:
    rng = np.random.default_rng(42)
    rows = 1500
    tenure = rng.integers(1, 73, rows)
    contract = rng.choice(
        ["monthly", "one_year", "two_year"], rows, p=[0.55, 0.25, 0.20]
    )
    internet = rng.choice(["fiber", "dsl", "none"], rows, p=[0.45, 0.35, 0.20])
    payment = rng.choice(
        ["electronic_check", "mailed_check", "bank_transfer", "credit_card"],
        rows,
        p=[0.35, 0.20, 0.20, 0.25],
    )
    autopay = np.where(
        np.isin(payment, ["electronic_check", "mailed_check"]),
        rng.choice(["yes", "no"], rows, p=[0.25, 0.75]),
        rng.choice(["yes", "no"], rows, p=[0.75, 0.25]),
    )
    support_tickets = rng.poisson(0.55, rows)

    service_base = np.select(
        [internet == "fiber", internet == "dsl"], [78.0, 48.0], default=26.0
    )
    monthly = np.clip(
        service_base + rng.normal(0, 11, rows) + support_tickets * 2.5, 18, 125
    ).round(2)
    total = (monthly * tenure * rng.uniform(0.96, 1.04, rows)).round(2)

    z = (
        -2.1
        + 0.026 * monthly
        - 0.045 * tenure
        + 0.85 * (contract == "monthly")
        - 0.28 * (contract == "two_year")
        + 0.42 * (internet == "fiber")
        + 0.55 * (payment == "electronic_check")
        + 0.38 * (autopay == "no")
        + 0.44 * support_tickets
        + rng.normal(0, 0.45, rows)
    )
    churn = np.where(1 / (1 + np.exp(-z)) > rng.uniform(0, 1, rows), "yes", "no")

    frame = pd.DataFrame(
        {
            "customer_id": [f"CUST-{index:05d}" for index in range(1, rows + 1)],
            "tenure_months": tenure,
            "monthly_charges": monthly,
            "total_charges": total,
            "contract_type": contract,
            "payment_method": payment,
            "internet_service": internet,
            "support_tickets": support_tickets,
            "autopay": autopay,
            "churn": churn,
        }
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT, index=False)
    rate = (frame["churn"] == "yes").mean()
    print(f"Wrote {len(frame)} rows to {OUTPUT} (churn rate {rate:.1%})")


if __name__ == "__main__":
    main()

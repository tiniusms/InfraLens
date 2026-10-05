"""Post-hoc description of the already scored final EIA holdout.

Reads ``data/processed/final_holdout/final_holdout_cases.parquet`` only.
Does not fit a model, select a penalty, or call the holdout runner.
Printed numbers are descriptive. They are not a new evaluation.
Narrative: ``docs/final_eia_holdout_posthoc_analysis.md``.
"""

from __future__ import annotations

import pandas as pd

STATES = ("MD", "NJ", "OH", "PA", "VA")
MONTHS = tuple(f"2025-{month:02d}" for month in range(7, 13)) + tuple(
    f"2026-{month:02d}" for month in range(1, 7)
)


def _direction(signed: pd.Series) -> str:
    return (
        f"mean={float(signed.mean()):.6f} "
        f"median={float(signed.median()):.4f} "
        f"under={int((signed > 0).sum())} "
        f"over={int((signed < 0).sum())} "
        f"exact={int((signed == 0).sum())}"
    )


def main() -> None:
    cases = pd.read_parquet("data/processed/final_holdout/final_holdout_cases.parquet")
    cases["target_month"] = cases["target_month"].astype(str)
    cases["ridge_signed_error"] = cases["actual"] - cases["ridge_prediction"]
    cases["seasonal_signed_error"] = cases["actual"] - cases["seasonal_naive_prediction"]
    half_width = (cases["interval_upper"] - cases["interval_lower"]) / 2.0
    above = cases["actual"] > cases["interval_upper"]
    below = cases["actual"] < cases["interval_lower"]
    distance = pd.Series(0.0, index=cases.index)
    distance.loc[above] = cases.loc[above, "actual"] - cases.loc[above, "interval_upper"]
    distance.loc[below] = cases.loc[below, "interval_lower"] - cases.loc[below, "actual"]
    advantage = cases["baseline_absolute_error"] - cases["ridge_absolute_error"]

    print("POST-HOC ANALYSIS — NOT USED FOR MODEL SELECTION")
    print("cases", len(cases))
    print("ridge", _direction(cases["ridge_signed_error"]))
    print("seasonal", _direction(cases["seasonal_signed_error"]))
    print("above_upper", int(above.sum()), "below_lower", int(below.sum()))
    print(
        "distance_outside",
        f"min={float(distance.min()):.4f}",
        f"median={float(distance.median()):.4f}",
        f"mean={float(distance.mean()):.4f}",
        f"max={float(distance.max()):.4f}",
    )
    print(
        "case_comparison",
        f"ridge_lower_ae={int((advantage > 0).sum())}",
        f"seasonal_lower_ae={int((advantage < 0).sum())}",
        f"ties={int((advantage == 0).sum())}",
        f"mean_advantage={float(advantage.mean()):.6f}",
    )
    print("states", ",".join(STATES))
    print("months", ",".join(MONTHS))
    same_sign_months = 0
    for month in MONTHS:
        signed = cases.loc[cases["target_month"] == month, "ridge_signed_error"]
        if int((signed > 0).sum()) == len(STATES) or int((signed < 0).sum()) == len(STATES):
            same_sign_months += 1
    print("months_with_all_five_states_same_ridge_sign", same_sign_months)


if __name__ == "__main__":
    main()

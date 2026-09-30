"""State-specific empirical absolute-residual intervals for frozen Ridge forecasts.

The interval layer does not fit Ridge. It reads rolling-origin point forecasts
that were already produced out of sample and wraps each one in a symmetric
interval. Nominal coverage is 80 percent. That is the order statistic requested
in ``EVALUATION.md``. It is not a guarantee of future coverage.

At origin ``T`` for state ``s``, the calibration pool is earlier Ridge cases
for ``s`` whose target month is before the final holdout and whose target
``assumed_available_at`` is on or before ``T``. The case being scored is not
in that pool. If fewer than 24 such residuals exist, or the order-statistic
index falls past the sample, the point forecast is kept and no interval is
emitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil

import numpy as np
import pandas as pd

from infralens.evaluation.backtest import (
    HOLDOUT_TARGET_START,
    latest_eia_parquet,
    load_price_panel,
    run_expanding_backtest,
)
from infralens.evaluation.linear import run_ridge_backtest

NOMINAL_COVERAGE: float = 0.8
MIN_CALIBRATION_RESIDUALS: int = 24
STATUS_INTERVAL: str = "interval"
STATUS_INSUFFICIENT_RESIDUAL_HISTORY: str = "insufficient_residual_history"

_REQUIRED_COLUMNS: tuple[str, ...] = (
    "state_id",
    "forecast_origin",
    "target_period",
    "ridge_prediction_cents_per_kwh",
    "actual_cents_per_kwh",
    "label_assumed_available_at",
)

INTERVAL_COLUMNS: tuple[str, ...] = (
    "state_id",
    "forecast_origin",
    "target_period",
    "ridge_prediction_cents_per_kwh",
    "actual_cents_per_kwh",
    "n_calibration_residuals",
    "k",
    "half_width_cents_per_kwh",
    "lower_cents_per_kwh",
    "upper_cents_per_kwh",
    "interval_status",
    "covered",
)

# Frozen development point result. A material mismatch stops the evaluation.
_FROZEN_RIDGE_N: int = 1145
_FROZEN_RIDGE_MAE_ROUNDED: float = 0.7075


class IntervalError(ValueError):
    """Raised when an interval would leak, score the holdout, or be unauditable."""


def order_statistic_index(n: int) -> int:
    """Return 1-based ``k = ceil((n + 1) * 0.8)`` with exact fifths arithmetic.

    ``0.8`` is ``4/5``. Integer ceiling avoids binary-float rounding and does
    not interpolate between residual order statistics.
    """
    if n < 0:
        raise IntervalError("Calibration count cannot be negative.")
    return ceil((n + 1) * 4 / 5)


def eligible_calibration_mask(
    predictions: pd.DataFrame,
    *,
    state_id: str,
    forecast_origin: pd.Timestamp,
    holdout_target_start: str = HOLDOUT_TARGET_START,
) -> pd.Series:
    """True for earlier out-of-sample Ridge rows that may calibrate ``state_id`` at ``T``.

    A row qualifies only when its state matches, its origin is strictly earlier
    than ``T``, its target actual is already available at ``T``, and its target
    month is before the final holdout. The row at ``T`` fails the origin test.
    """
    _require_columns(predictions)
    origin = pd.Timestamp(forecast_origin)
    return (
        (predictions["state_id"].astype(str) == str(state_id))
        & (pd.to_datetime(predictions["forecast_origin"]) < origin)
        & (pd.to_datetime(predictions["label_assumed_available_at"]) <= origin)
        & (predictions["target_period"].astype(str) < holdout_target_start)
    )


def absolute_residuals(predictions: pd.DataFrame) -> pd.Series:
    """Absolute error of the stored rolling-origin Ridge prediction."""
    _require_columns(predictions)
    actual = predictions["actual_cents_per_kwh"].astype(float)
    predicted = predictions["ridge_prediction_cents_per_kwh"].astype(float)
    return (actual - predicted).abs()


def absolute_residual_interval(
    *,
    point_prediction: float,
    actual: float | None,
    residuals: np.ndarray,
) -> dict[str, object]:
    """Symmetric 80% interval around one point forecast.

    ``residuals`` are absolute errors from earlier out-of-sample predictions.
    The scored case is not part of this array. No mean residual is subtracted.
    """
    ordered = np.sort(np.asarray(residuals, dtype=float))
    n = int(ordered.size)
    k = order_statistic_index(n)
    point = float(point_prediction)
    result: dict[str, object] = {
        "n_calibration_residuals": n,
        "k": k,
        "half_width_cents_per_kwh": None,
        "lower_cents_per_kwh": None,
        "upper_cents_per_kwh": None,
        "width_cents_per_kwh": None,
        "interval_status": STATUS_INSUFFICIENT_RESIDUAL_HISTORY,
        "covered": None,
    }
    if n >= MIN_CALIBRATION_RESIDUALS and k <= n:
        half_width = float(ordered[k - 1])
        lower = point - half_width
        upper = point + half_width
        result["half_width_cents_per_kwh"] = half_width
        result["lower_cents_per_kwh"] = lower
        result["upper_cents_per_kwh"] = upper
        result["width_cents_per_kwh"] = half_width * 2.0
        result["interval_status"] = STATUS_INTERVAL
        if actual is not None and not pd.isna(actual):
            result["covered"] = bool(lower <= float(actual) <= upper)
    return result


def build_ridge_intervals(
    predictions: pd.DataFrame,
    *,
    holdout_target_start: str = HOLDOUT_TARGET_START,
) -> pd.DataFrame:
    """Attach an 80% absolute-residual interval to each frozen Ridge forecast.

    ``predictions`` must already be the rolling-origin Ridge output. This
    function does not fit a model and does not modify ``predictions``.
    """
    if holdout_target_start > HOLDOUT_TARGET_START:
        raise IntervalError("The final holdout cannot be moved later than 2025-07.")
    _require_columns(predictions)
    if predictions.empty:
        raise IntervalError("Ridge predictions are empty.")
    if predictions["target_period"].astype(str).ge(holdout_target_start).any():
        raise IntervalError("Holdout target was scored.")
    keys = predictions[["state_id", "forecast_origin"]].copy()
    keys["forecast_origin"] = pd.to_datetime(keys["forecast_origin"])
    if keys.duplicated().any():
        raise IntervalError("Each state and forecast origin must appear once.")

    # Work on a copy so the caller's Ridge table stays byte-for-byte usable.
    source = predictions.loc[:, list(_REQUIRED_COLUMNS)].copy()
    source["forecast_origin"] = pd.to_datetime(source["forecast_origin"])
    source["label_assumed_available_at"] = pd.to_datetime(source["label_assumed_available_at"])
    source["target_period"] = source["target_period"].astype(str)
    source["state_id"] = source["state_id"].astype(str)

    records: list[dict[str, object]] = []
    for position in range(len(source)):
        case = source.iloc[position]
        mask = eligible_calibration_mask(
            source,
            state_id=str(case["state_id"]),
            forecast_origin=pd.Timestamp(case["forecast_origin"]),
            holdout_target_start=holdout_target_start,
        )
        pool = source.loc[mask]
        residuals = absolute_residuals(pool).to_numpy(dtype=float)
        point = float(case["ridge_prediction_cents_per_kwh"])
        actual = float(case["actual_cents_per_kwh"])
        interval = absolute_residual_interval(
            point_prediction=point,
            actual=actual,
            residuals=residuals,
        )
        record: dict[str, object] = {
            "state_id": str(case["state_id"]),
            "forecast_origin": pd.Timestamp(case["forecast_origin"]),
            "target_period": str(case["target_period"]),
            "ridge_prediction_cents_per_kwh": point,
            "actual_cents_per_kwh": actual,
            "n_calibration_residuals": interval["n_calibration_residuals"],
            "k": interval["k"],
            "half_width_cents_per_kwh": (
                pd.NA
                if interval["half_width_cents_per_kwh"] is None
                else interval["half_width_cents_per_kwh"]
            ),
            "lower_cents_per_kwh": (
                pd.NA
                if interval["lower_cents_per_kwh"] is None
                else interval["lower_cents_per_kwh"]
            ),
            "upper_cents_per_kwh": (
                pd.NA
                if interval["upper_cents_per_kwh"] is None
                else interval["upper_cents_per_kwh"]
            ),
            "interval_status": interval["interval_status"],
            "covered": pd.NA if interval["covered"] is None else interval["covered"],
        }
        records.append(record)

    intervals = pd.DataFrame.from_records(records, columns=list(INTERVAL_COLUMNS))
    if intervals["target_period"].astype(str).ge(holdout_target_start).any():
        raise IntervalError("Holdout target was scored.")
    point_changed = (
        intervals["ridge_prediction_cents_per_kwh"].to_numpy(dtype=float)
        != source["ridge_prediction_cents_per_kwh"].to_numpy(dtype=float)
    )
    if point_changed.any():
        raise IntervalError("Interval construction changed a Ridge point prediction.")
    return intervals


@dataclass(frozen=True)
class IntervalEvaluation:
    """Development diagnostics for intervals that were actually emitted."""

    n_point_forecasts: int
    n_intervals: int
    n_insufficient_residual_history: int
    nominal_coverage: float
    empirical_coverage: float | None
    empirical_coverage_by_state: dict[str, float]
    mean_width: float | None
    mean_width_by_state: dict[str, float]
    median_width: float | None
    first_interval_origin_by_state: dict[str, pd.Timestamp]
    residuals_at_first_interval_by_state: dict[str, int]
    residuals_at_final_origin_by_state: dict[str, int]
    mean_width_by_year: dict[int, float]


def evaluate_intervals(intervals: pd.DataFrame) -> IntervalEvaluation:
    """Summarize coverage and width on rows that received an interval."""
    if list(intervals.columns) != list(INTERVAL_COLUMNS):
        raise IntervalError("Interval table is missing the audit columns.")
    if intervals.empty:
        raise IntervalError("Interval table is empty.")
    if intervals["target_period"].astype(str).ge(HOLDOUT_TARGET_START).any():
        raise IntervalError("Holdout target was scored.")
    emitted = intervals.loc[intervals["interval_status"] == STATUS_INTERVAL].copy()
    insufficient = intervals["interval_status"] == STATUS_INSUFFICIENT_RESIDUAL_HISTORY
    if len(emitted) + int(insufficient.sum()) != len(intervals):
        raise IntervalError("Interval status was not one of the two allowed values.")

    coverage_by_state: dict[str, float] = {}
    width_by_state: dict[str, float] = {}
    first_origin: dict[str, pd.Timestamp] = {}
    residuals_at_first: dict[str, int] = {}
    if not emitted.empty:
        emitted["width"] = emitted["half_width_cents_per_kwh"].astype(float) * 2.0
        for state, group in emitted.groupby("state_id", sort=True):
            coverage_by_state[str(state)] = float(group["covered"].astype(bool).mean())
            width_by_state[str(state)] = float(group["width"].mean())
            earliest = group.loc[group["forecast_origin"].idxmin()]
            first_origin[str(state)] = pd.Timestamp(earliest["forecast_origin"])
            residuals_at_first[str(state)] = int(earliest["n_calibration_residuals"])

    final_origin = pd.Timestamp(intervals["forecast_origin"].max())
    final_rows = intervals.loc[intervals["forecast_origin"] == final_origin]
    residuals_at_final = {
        str(state): int(group["n_calibration_residuals"].iloc[0])
        for state, group in final_rows.groupby("state_id", sort=True)
    }
    width_by_year: dict[int, float] = {}
    if not emitted.empty:
        years = pd.to_datetime(emitted["forecast_origin"]).dt.year
        for year, group in emitted.groupby(years, sort=True):
            width_by_year[int(year)] = float(group["width"].mean())

    return IntervalEvaluation(
        n_point_forecasts=int(len(intervals)),
        n_intervals=int(len(emitted)),
        n_insufficient_residual_history=int(insufficient.sum()),
        nominal_coverage=NOMINAL_COVERAGE,
        empirical_coverage=(
            None if emitted.empty else float(emitted["covered"].astype(bool).mean())
        ),
        empirical_coverage_by_state=coverage_by_state,
        mean_width=None if emitted.empty else float(emitted["width"].mean()),
        mean_width_by_state=width_by_state,
        median_width=None if emitted.empty else float(emitted["width"].median()),
        first_interval_origin_by_state=first_origin,
        residuals_at_first_interval_by_state=residuals_at_first,
        residuals_at_final_origin_by_state=residuals_at_final,
        mean_width_by_year=width_by_year,
    )


def _require_columns(predictions: pd.DataFrame) -> None:
    missing = [column for column in _REQUIRED_COLUMNS if column not in predictions.columns]
    if missing:
        raise IntervalError(f"Ridge predictions are missing columns: {missing}.")


def _print_evaluation(
    evaluation: IntervalEvaluation,
    *,
    parquet_path: object,
    ridge_mae: float,
    ridge_n: int,
    max_target_period: str,
    final_origin: pd.Timestamp,
) -> None:
    print(f"window: development")
    print(f"parquet: {parquet_path}")
    print(f"ridge_mae_cents_per_kwh: {ridge_mae:.4f}")
    print(f"n_point_forecasts: {evaluation.n_point_forecasts}")
    print(f"n_scored_ridge_check: {ridge_n}")
    print(f"n_intervals: {evaluation.n_intervals}")
    print(f"n_insufficient_residual_history: {evaluation.n_insufficient_residual_history}")
    print(f"nominal_coverage: {evaluation.nominal_coverage:.1f}")
    if evaluation.empirical_coverage is None:
        print("empirical_coverage: none")
    else:
        print(f"empirical_coverage: {evaluation.empirical_coverage:.4f}")
        outside = not 0.75 <= evaluation.empirical_coverage <= 0.85
        if outside:
            print(
                "development_coverage_check: outside 75-85%. "
                "The interval method was not changed."
            )
        else:
            print("development_coverage_check: inside 75-85%. Not a tuning result.")
    print("empirical_coverage_by_state:")
    for state, coverage in evaluation.empirical_coverage_by_state.items():
        print(f"  {state}: {coverage:.4f}")
    if evaluation.mean_width is None:
        print("mean_width_cents_per_kwh: none")
        print("median_width_cents_per_kwh: none")
    else:
        print(f"mean_width_cents_per_kwh: {evaluation.mean_width:.4f}")
        print(f"median_width_cents_per_kwh: {evaluation.median_width:.4f}")
    print("mean_width_by_state_cents_per_kwh:")
    for state, width in evaluation.mean_width_by_state.items():
        print(f"  {state}: {width:.4f}")
    print("first_interval_origin:")
    for state, origin in evaluation.first_interval_origin_by_state.items():
        count = evaluation.residuals_at_first_interval_by_state[state]
        print(f"  {state}: {origin.date()} n_residuals={count}")
    print(f"final_development_origin: {final_origin.date()}")
    print("residuals_at_final_origin:")
    for state, count in evaluation.residuals_at_final_origin_by_state.items():
        print(f"  {state}: {count}")
    print("mean_width_by_origin_year_cents_per_kwh:")
    for year, width in evaluation.mean_width_by_year.items():
        print(f"  {year}: {width:.4f}")
    print(f"max_target_period: {max_target_period}")
    print(f"run_at: {datetime.now().isoformat(timespec='seconds')}")


def main() -> int:
    """Score development intervals from one frozen Ridge backtest.

    Stops before reporting intervals if the Ridge point MAE or case count
    differs from the frozen development result.
    """
    parquet_path = latest_eia_parquet()
    frame = load_price_panel(parquet_path)
    ridge = run_ridge_backtest(frame)
    rounded_mae = round(ridge.mae_ridge, 4)
    if ridge.n_forecasts != _FROZEN_RIDGE_N or rounded_mae != _FROZEN_RIDGE_MAE_ROUNDED:
        print(
            "STOP: Ridge point predictions differ from the frozen development result. "
            f"n={ridge.n_forecasts} mae={ridge.mae_ridge:.10f}"
        )
        return 2
    # Full-window baseline is printed only so this run does not replace it.
    baseline = run_expanding_backtest(frame)
    if baseline.n_forecasts != 1350 or round(baseline.mae_overall, 4) != 0.7793:
        print(
            "STOP: full-development seasonal-naive result changed. "
            f"n={baseline.n_forecasts} mae={baseline.mae_overall:.10f}"
        )
        return 2
    before = ridge.predictions.copy()
    intervals = build_ridge_intervals(ridge.predictions)
    if not ridge.predictions.equals(before):
        print("STOP: building intervals mutated the Ridge prediction table.")
        return 2
    evaluation = evaluate_intervals(intervals)
    if evaluation.n_point_forecasts != ridge.n_forecasts:
        print("STOP: interval rows do not match Ridge point forecasts.")
        return 2
    max_target = str(intervals["target_period"].max())
    if max_target >= HOLDOUT_TARGET_START:
        print("STOP: a holdout target month was scored.")
        return 2
    _print_evaluation(
        evaluation,
        parquet_path=parquet_path,
        ridge_mae=ridge.mae_ridge,
        ridge_n=ridge.n_forecasts,
        max_target_period=max_target,
        final_origin=pd.Timestamp(intervals["forecast_origin"].max()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

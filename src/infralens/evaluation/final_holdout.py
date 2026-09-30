"""Locked final EIA holdout runner.

This module is the only entry point that may score target months 2025-07
through 2026-06. It reuses the frozen Ridge helpers (``select_alpha``,
``fit_ridge``, ``training_cases_for_origin``) and the frozen seasonal-naive
baseline. It does not define a second model, feature set, or interval rule.

``python -m infralens.evaluation.final_holdout`` accepts no options. Do not
run it until this runner has been reviewed. Development commands still refuse
to score the holdout.

Holdout explanations are not part of this command. A prediction can be
explained afterward with ``explain_prediction`` and the alpha stored on the
scored row. That explanation does not affect the primary comparison.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from infralens.data import USER_FACING_STATES, repository_root
from infralens.evaluation.backtest import (
    HOLDOUT_TARGET_START,
    latest_eia_parquet,
    load_price_panel,
    month_end_origins,
)
from infralens.evaluation.baseline import (
    NoAnalogError,
    availability_adjusted_seasonal_naive,
    target_period_for_origin,
)
from infralens.evaluation.features import MODEL_FEATURES
from infralens.evaluation.intervals import (
    MIN_CALIBRATION_RESIDUALS,
    NOMINAL_COVERAGE,
    STATUS_INSUFFICIENT_RESIDUAL_HISTORY,
    STATUS_INTERVAL,
    absolute_residual_interval,
    eligible_calibration_mask,
    absolute_residuals,
)
from infralens.evaluation.linear import (
    ALPHA_GRID,
    HISTORY_ORIGIN_START,
    INNER_VALIDATION_ORIGINS,
    MIN_FIT_ORIGINS,
    SKIP_FEATURE_GAP,
    SKIP_INSUFFICIENT_TRAIN,
    SKIP_MISSING_ACTUAL,
    build_feature_cases,
    design_matrix,
    fit_ridge,
    frame_categories_known,
    numeric_scaler_means,
    run_ridge_backtest,
    select_alpha,
    training_cases_for_origin,
)
from infralens.evaluation.selection import FEATURE_SET_ID, FINAL_HOLDOUT_STAGE, FROZEN_FEATURES

FINAL_ORIGIN_START = "2024-07"
FINAL_ORIGIN_END = "2025-06"
FINAL_STATES: tuple[str, ...] = ("MD", "NJ", "OH", "PA", "VA")
PRIMARY_RELATIVE_IMPROVEMENT = 0.10
LOCKED_FEATURES: tuple[str, ...] = (
    "price_latest",
    "price_same_month",
    "price_yoy_change",
    "price_trail12_mean",
    "sales_latest",
    "sales_yoy_change",
    "state_id",
    "target_calendar_month",
)
LOCKED_ALPHA_GRID: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
LOCKED_ORIGIN_TARGETS: tuple[tuple[str, str], ...] = (
    ("2024-07-31", "2025-07"),
    ("2024-08-31", "2025-08"),
    ("2024-09-30", "2025-09"),
    ("2024-10-31", "2025-10"),
    ("2024-11-30", "2025-11"),
    ("2024-12-31", "2025-12"),
    ("2025-01-31", "2026-01"),
    ("2025-02-28", "2026-02"),
    ("2025-03-31", "2026-03"),
    ("2025-04-30", "2026-04"),
    ("2025-05-31", "2026-05"),
    ("2025-06-30", "2026-06"),
)
SKIP_NO_ANALOG = "no_analog"

CASE_COLUMNS: tuple[str, ...] = (
    "evaluation_stage",
    "state_id",
    "forecast_origin",
    "target_month",
    "actual",
    "ridge_prediction",
    "seasonal_naive_prediction",
    "ridge_absolute_error",
    "baseline_absolute_error",
    "selected_alpha",
    "interval_lower",
    "interval_upper",
    "interval_width",
    "interval_status",
    "interval_covered",
    "skip_reason",
    "n_train_rows",
    "max_training_target_period",
)


class FinalHoldoutError(RuntimeError):
    """Raised when the locked holdout contract would be violated."""


@dataclass(frozen=True)
class FinalHoldoutResult:
    """Case table and summary for one final-holdout run."""

    cases: pd.DataFrame
    summary: dict[str, object]


def locked_cells() -> list[tuple[pd.Timestamp, str, str]]:
    """Return the 60 origin/state/target cells in deterministic order."""
    _assert_frozen_contract()
    origins = [pd.Timestamp(value).normalize() for value in month_end_origins(
        FINAL_ORIGIN_START,
        FINAL_ORIGIN_END,
    )]
    if len(origins) != len(LOCKED_ORIGIN_TARGETS):
        raise FinalHoldoutError("The holdout origin grid is not the locked 12 months.")
    cells: list[tuple[pd.Timestamp, str, str]] = []
    for origin, (expected_day, expected_target) in zip(
        origins,
        LOCKED_ORIGIN_TARGETS,
        strict=True,
    ):
        if origin.date().isoformat() != expected_day:
            raise FinalHoldoutError(
                f"Origin {origin.date().isoformat()} is not the locked date {expected_day}."
            )
        target = target_period_for_origin(origin)
        if target != expected_target:
            raise FinalHoldoutError(
                f"Origin {expected_day} maps to {target}, not {expected_target}."
            )
        for state in FINAL_STATES:
            cells.append((origin, state, target))
    if len(cells) != 60:
        raise FinalHoldoutError("The holdout grid is not 60 cells.")
    return cells


def relative_improvement(baseline_mae: float, ridge_mae: float) -> float:
    """Paired relative MAE reduction. This is the primary comparison ratio."""
    if baseline_mae <= 0:
        raise FinalHoldoutError("Paired baseline MAE must be positive.")
    return (float(baseline_mae) - float(ridge_mae)) / float(baseline_mae)


def primary_criterion_passes(improvement: float) -> bool:
    """True only when the paired relative improvement is at least 10%."""
    return float(improvement) >= PRIMARY_RELATIVE_IMPROVEMENT


def holdout_interval(
    history: pd.DataFrame,
    *,
    state_id: str,
    forecast_origin: pd.Timestamp,
    point_prediction: float,
    actual: float | None,
) -> dict[str, object]:
    """Interval for one holdout point using only pre-2025-07 calibration targets.

    ``history`` is the development out-of-sample Ridge table. The scored
    holdout row is not added to it. ``build_ridge_intervals`` is not called,
    so its refusal to score a holdout table stays in place.
    """
    if (history["target_period"].astype(str) >= HOLDOUT_TARGET_START).any():
        raise FinalHoldoutError("A holdout target entered the calibration history.")
    mask = eligible_calibration_mask(
        history,
        state_id=state_id,
        forecast_origin=forecast_origin,
    )
    if history.loc[mask, "target_period"].astype(str).ge(HOLDOUT_TARGET_START).any():
        raise FinalHoldoutError("Calibration retained a holdout target month.")
    if (pd.to_datetime(history.loc[mask, "forecast_origin"]) >= pd.Timestamp(forecast_origin)).any():
        raise FinalHoldoutError("Calibration retained the scored origin or a later one.")
    residuals = absolute_residuals(history.loc[mask]).to_numpy(dtype=float)
    return absolute_residual_interval(
        point_prediction=point_prediction,
        actual=actual,
        residuals=residuals,
    )


def run_final_holdout(
    frame: pd.DataFrame,
    *,
    extract_id: str,
) -> FinalHoldoutResult:
    """Score the locked holdout grid. Development residuals come from ``run_ridge_backtest``."""
    _assert_frozen_contract()
    development = run_ridge_backtest(frame)
    if development.window != "development":
        raise FinalHoldoutError("Calibration residuals did not come from the development window.")
    if (development.predictions["target_period"].astype(str) >= HOLDOUT_TARGET_START).any():
        raise FinalHoldoutError("Development scoring included a holdout target.")
    return _score_locked_grid(
        frame,
        development.predictions,
        extract_id=extract_id,
    )


def _score_locked_grid(
    frame: pd.DataFrame,
    development_predictions: pd.DataFrame,
    *,
    extract_id: str,
) -> FinalHoldoutResult:
    _assert_frozen_contract()
    if development_predictions.empty:
        raise FinalHoldoutError("Development Ridge predictions are empty.")
    if (development_predictions["target_period"].astype(str) >= HOLDOUT_TARGET_START).any():
        raise FinalHoldoutError("A holdout target entered the calibration history.")
    cells = locked_cells()
    history_origins = month_end_origins(HISTORY_ORIGIN_START, FINAL_ORIGIN_END)
    cases, gaps = build_feature_cases(frame, origins=history_origins, states=FINAL_STATES)
    case_index = {
        (pd.Timestamp(row.forecast_origin).normalize(), str(row.state_id)): row
        for row in cases.itertuples(index=False)
    }
    actuals = {
        (str(row.state_id).upper(), str(row.period)): row.price_cents_per_kwh
        for row in frame.itertuples(index=False)
        if hasattr(row, "period")
    }
    records: list[dict[str, object]] = []
    fitted_by_origin: dict[pd.Timestamp, tuple[object, float, pd.DataFrame]] = {}

    for origin, _state, target in cells:
        if origin in fitted_by_origin:
            continue
        train = training_cases_for_origin(
            cases,
            forecast_origin=origin,
            holdout_target_start=HOLDOUT_TARGET_START,
        )
        if not train.empty:
            if (pd.to_datetime(train["forecast_origin"]) >= origin).any():
                raise FinalHoldoutError("The scored origin entered its training rows.")
            if (train["target_period"].astype(str) >= HOLDOUT_TARGET_START).any():
                raise FinalHoldoutError("A holdout target entered training.")
            if (pd.to_datetime(train["label_assumed_available_at"]) > origin).any():
                raise FinalHoldoutError("A training label was not available at the origin.")
        selection = select_alpha(
            train,
            alpha_grid=ALPHA_GRID,
            inner_validation_origins=INNER_VALIDATION_ORIGINS,
            min_fit_origins=MIN_FIT_ORIGINS,
        )
        model = None
        if selection is not None:
            if float(selection.alpha) not in LOCKED_ALPHA_GRID:
                raise FinalHoldoutError("Selected alpha is outside the frozen grid.")
            model = fit_ridge(train, selection.alpha)
            fitted_means = numeric_scaler_means(model)
            for name, fitted_mean in fitted_means.items():
                if abs(fitted_mean - float(train[name].mean())) > 1e-8:
                    raise FinalHoldoutError(
                        f"Scaler for {name} was not fit on the eligible training rows."
                    )
            if pd.to_datetime(train["forecast_origin"]).max() >= origin:
                raise FinalHoldoutError("Fitted training rows are not strictly before the origin.")
        fitted_by_origin[origin] = (model, None if selection is None else float(selection.alpha), train)

    for origin, state, target in cells:
        model, alpha, train = fitted_by_origin[origin]
        actual_value = actuals.get((state, target))
        actual = None if actual_value is None or pd.isna(actual_value) else float(actual_value)
        key = (origin, state)
        base = {
            "evaluation_stage": FINAL_HOLDOUT_STAGE,
            "state_id": state,
            "forecast_origin": origin,
            "target_month": target,
            "actual": actual,
            "ridge_prediction": None,
            "seasonal_naive_prediction": None,
            "ridge_absolute_error": None,
            "baseline_absolute_error": None,
            "selected_alpha": None,
            "interval_lower": None,
            "interval_upper": None,
            "interval_width": None,
            "interval_status": None,
            "interval_covered": None,
            "skip_reason": None,
            "n_train_rows": None if train is None else int(len(train)),
            "max_training_target_period": (
                None if train is None or train.empty else str(train["target_period"].max())
            ),
        }
        if key in gaps:
            base["skip_reason"] = SKIP_FEATURE_GAP
            records.append(base)
            continue
        case = case_index.get(key)
        if case is None:
            raise FinalHoldoutError(f"Missing feature row for {state} at {origin.date()} without a skip.")
        if str(case.target_period) != target:
            raise FinalHoldoutError("Scored target is not 12 months after the origin.")
        if actual is None or pd.isna(case.actual_cents_per_kwh):
            base["skip_reason"] = SKIP_MISSING_ACTUAL
            records.append(base)
            continue
        if model is None or alpha is None:
            base["skip_reason"] = SKIP_INSUFFICIENT_TRAIN
            records.append(base)
            continue
        row_frame = pd.DataFrame([case._asdict()])
        if not frame_categories_known(model, row_frame):
            base["skip_reason"] = SKIP_INSUFFICIENT_TRAIN
            records.append(base)
            continue
        for stamp_name in (
            "latest_assumed_available_at",
            "same_month_assumed_available_at",
            "yoy_assumed_available_at",
            "trail_max_assumed_available_at",
        ):
            if pd.Timestamp(getattr(case, stamp_name)) > origin:
                raise FinalHoldoutError(f"Feature {stamp_name} is after the forecast origin.")
        try:
            baseline = availability_adjusted_seasonal_naive(
                frame,
                forecast_origin=origin,
                state_id=state,
            )
        except NoAnalogError:
            base["skip_reason"] = SKIP_NO_ANALOG
            records.append(base)
            continue
        baseline_prediction = float(baseline["prediction_cents_per_kwh"])
        if baseline_prediction != float(case.price_same_month):
            raise FinalHoldoutError("price_same_month diverges from the seasonal-naive baseline.")
        if str(baseline["target_period"]) != target or str(baseline["state_id"]) != state:
            raise FinalHoldoutError("Baseline case does not match the Ridge case.")
        predicted = float(model.predict(design_matrix(row_frame))[0])
        interval = holdout_interval(
            development_predictions,
            state_id=state,
            forecast_origin=origin,
            point_prediction=predicted,
            actual=actual,
        )
        base.update(
            {
                "ridge_prediction": predicted,
                "seasonal_naive_prediction": baseline_prediction,
                "ridge_absolute_error": abs(predicted - actual),
                "baseline_absolute_error": abs(baseline_prediction - actual),
                "selected_alpha": alpha,
                "interval_lower": interval["lower_cents_per_kwh"],
                "interval_upper": interval["upper_cents_per_kwh"],
                "interval_width": interval["width_cents_per_kwh"],
                "interval_status": interval["interval_status"],
                "interval_covered": interval["covered"],
            }
        )
        records.append(base)

    table = pd.DataFrame.from_records(records, columns=list(CASE_COLUMNS))
    table = table.sort_values(["forecast_origin", "state_id"], kind="mergesort").reset_index(drop=True)
    _assert_case_table(table, cells)
    summary = _summary(table, extract_id=extract_id)
    return FinalHoldoutResult(cases=table, summary=summary)


def write_holdout_result(result: FinalHoldoutResult, directory: Path) -> tuple[Path, Path]:
    """Write the case table and summary. This does not score anything."""
    directory.mkdir(parents=True, exist_ok=True)
    cases_path = directory / "final_holdout_cases.parquet"
    summary_path = directory / "final_holdout_summary.json"
    result.cases.to_parquet(cases_path, index=False)
    summary_path.write_text(
        json.dumps(result.summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return cases_path, summary_path


def _summary(table: pd.DataFrame, *, extract_id: str) -> dict[str, object]:
    attempted = int(len(table))
    scored = table.loc[table["skip_reason"].isna()].copy()
    skip_counts = {
        reason: int((table["skip_reason"] == reason).sum())
        for reason in (
            SKIP_FEATURE_GAP,
            SKIP_INSUFFICIENT_TRAIN,
            SKIP_MISSING_ACTUAL,
            SKIP_NO_ANALOG,
        )
    }
    n_scored = int(len(scored))
    if attempted != n_scored + sum(skip_counts.values()):
        raise FinalHoldoutError("Attempted cases do not equal scored cases plus skips.")
    if n_scored == 0:
        raise FinalHoldoutError("No paired holdout cases were scored.")
    ridge_mae = float(scored["ridge_absolute_error"].mean())
    baseline_mae = float(scored["baseline_absolute_error"].mean())
    improvement = relative_improvement(baseline_mae, ridge_mae)
    passed = primary_criterion_passes(improvement)
    by_state: dict[str, dict[str, float | None]] = {}
    interval_by_state: dict[str, dict[str, float | None]] = {}
    for state in FINAL_STATES:
        state_rows = scored.loc[scored["state_id"] == state]
        if state_rows.empty:
            by_state[state] = {"ridge_mae": None, "paired_baseline_mae": None, "n_scored": 0}
        else:
            by_state[state] = {
                "ridge_mae": float(state_rows["ridge_absolute_error"].mean()),
                "paired_baseline_mae": float(state_rows["baseline_absolute_error"].mean()),
                "n_scored": int(len(state_rows)),
            }
        intervals = state_rows.loc[state_rows["interval_status"] == STATUS_INTERVAL]
        if intervals.empty:
            interval_by_state[state] = {"coverage": None, "mean_width": None, "n_intervals": 0}
        else:
            interval_by_state[state] = {
                "coverage": float(intervals["interval_covered"].astype(bool).mean()),
                "mean_width": float(intervals["interval_width"].astype(float).mean()),
                "n_intervals": int(len(intervals)),
            }
    all_intervals = scored.loc[scored["interval_status"] == STATUS_INTERVAL]
    coverage = (
        None
        if all_intervals.empty
        else float(all_intervals["interval_covered"].astype(bool).mean())
    )
    mean_width = (
        None
        if all_intervals.empty
        else float(all_intervals["interval_width"].astype(float).mean())
    )
    # State MAE and interval coverage are reported and then ignored by the gate.
    return {
        "evaluation_stage": FINAL_HOLDOUT_STAGE,
        "extract_id": extract_id,
        "feature_set_id": FEATURE_SET_ID,
        "git_commit": _git_commit(),
        "attempted": attempted,
        "scored_paired": n_scored,
        "skip_counts": skip_counts,
        "ridge_mae": ridge_mae,
        "paired_baseline_mae": baseline_mae,
        "mae_difference": baseline_mae - ridge_mae,
        "mae_improvement_ratio": improvement,
        "mae_improvement_percent": 100.0 * improvement,
        "primary_threshold_ratio": PRIMARY_RELATIVE_IMPROVEMENT,
        "primary_threshold_percent": 10,
        "primary_criterion": "PASS" if passed else "FAIL",
        "mae_by_state": by_state,
        "n_intervals": int(len(all_intervals)),
        "n_insufficient_residual_history": int(
            (scored["interval_status"] == STATUS_INSUFFICIENT_RESIDUAL_HISTORY).sum()
        ),
        "interval_coverage": coverage,
        "mean_interval_width": mean_width,
        "interval_by_state": interval_by_state,
        "nominal_interval_coverage": NOMINAL_COVERAGE,
        "min_calibration_residuals": MIN_CALIBRATION_RESIDUALS,
    }


def _assert_case_table(
    table: pd.DataFrame,
    cells: list[tuple[pd.Timestamp, str, str]],
) -> None:
    if len(table) != 60:
        raise FinalHoldoutError("The case table does not contain 60 cells.")
    if table["evaluation_stage"].nunique() != 1 or table["evaluation_stage"].iloc[0] != FINAL_HOLDOUT_STAGE:
        raise FinalHoldoutError("Evaluation stage is not final_holdout.")
    if set(table["state_id"]) != set(FINAL_STATES):
        raise FinalHoldoutError("Holdout states are not the locked five.")
    observed = list(
        zip(
            table["forecast_origin"].map(lambda value: pd.Timestamp(value).date().isoformat()),
            table["state_id"],
            table["target_month"],
            strict=True,
        )
    )
    expected = [(origin.date().isoformat(), state, target) for origin, state, target in cells]
    if observed != expected:
        raise FinalHoldoutError("Case order or target alignment does not match the locked grid.")
    scored = table.loc[table["skip_reason"].isna()]
    if not scored.empty:
        same_actual = np.isclose(
            scored["ridge_absolute_error"].to_numpy(dtype=float),
            (scored["actual"] - scored["ridge_prediction"]).abs().to_numpy(dtype=float),
        )
        same_baseline = np.isclose(
            scored["baseline_absolute_error"].to_numpy(dtype=float),
            (scored["actual"] - scored["seasonal_naive_prediction"]).abs().to_numpy(dtype=float),
        )
        if not same_actual.all() or not same_baseline.all():
            raise FinalHoldoutError("Paired errors do not use the same actual.")
        if (scored["max_training_target_period"].astype(str) >= HOLDOUT_TARGET_START).any():
            raise FinalHoldoutError("A scored row trained on a holdout target.")


def _assert_frozen_contract() -> None:
    if HOLDOUT_TARGET_START != "2025-07":
        raise FinalHoldoutError("The holdout boundary is no longer 2025-07.")
    if FEATURE_SET_ID != "eia_commercial_price_v1":
        raise FinalHoldoutError("Feature-set identifier is not eia_commercial_price_v1.")
    if FROZEN_FEATURES != LOCKED_FEATURES or MODEL_FEATURES != LOCKED_FEATURES:
        raise FinalHoldoutError("The frozen feature list changed.")
    if ALPHA_GRID != LOCKED_ALPHA_GRID:
        raise FinalHoldoutError("The Ridge penalty grid changed.")
    if INNER_VALIDATION_ORIGINS != 12 or MIN_FIT_ORIGINS != 12:
        raise FinalHoldoutError("The inner validation split changed.")
    if set(USER_FACING_STATES) != set(FINAL_STATES) or len(FINAL_STATES) != 5:
        raise FinalHoldoutError("The state set changed.")
    if FINAL_HOLDOUT_STAGE != "final_holdout":
        raise FinalHoldoutError("The final stage label changed.")
    if PRIMARY_RELATIVE_IMPROVEMENT != 0.10:
        raise FinalHoldoutError("The primary threshold changed.")
    if NOMINAL_COVERAGE != 0.8 or MIN_CALIBRATION_RESIDUALS != 24:
        raise FinalHoldoutError("The interval rule changed.")


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root(),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv: list[str] | None = None) -> int:
    """Score the real final holdout. This function accepts no configuration."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        raise FinalHoldoutError(
            "The final holdout runner accepts no options. "
            "Dates, states, features, penalty grid, threshold, and interval rule are fixed."
        )
    parquet_path = latest_eia_parquet()
    frame = load_price_panel(parquet_path)
    result = run_final_holdout(frame, extract_id=parquet_path.name)
    cases_path, summary_path = write_holdout_result(
        result,
        repository_root() / "data" / "processed" / "final_holdout",
    )
    print(f"evaluation_stage: {result.summary['evaluation_stage']}")
    print(f"extract_id: {result.summary['extract_id']}")
    print(f"git_commit: {result.summary['git_commit']}")
    print(f"attempted: {result.summary['attempted']}")
    print(f"scored_paired: {result.summary['scored_paired']}")
    print(f"skip_counts: {result.summary['skip_counts']}")
    print(f"ridge_mae: {result.summary['ridge_mae']:.6f}")
    print(f"paired_baseline_mae: {result.summary['paired_baseline_mae']:.6f}")
    print(f"mae_improvement_percent: {result.summary['mae_improvement_percent']:.4f}")
    print(f"primary_threshold_percent: {result.summary['primary_threshold_percent']}")
    print(f"primary_criterion: {result.summary['primary_criterion']}")
    print(f"n_intervals: {result.summary['n_intervals']}")
    print(f"interval_coverage: {result.summary['interval_coverage']}")
    print(f"mean_interval_width: {result.summary['mean_interval_width']}")
    print(f"cases: {cases_path}")
    print(f"summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

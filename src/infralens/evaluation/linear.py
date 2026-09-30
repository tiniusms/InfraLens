"""Expanding-origin Ridge baseline on the EIA commercial-price panel.

Same development grid as the availability-adjusted seasonal-naive backtest.
Final holdout target months (2025-07 through 2026-06) are never fit,
never used to pick the penalty, and never scored.

At each scored origin the scaler, one-hot encoder, and Ridge penalty are
fit only on earlier origins whose target price is already available.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from infralens.data import USER_FACING_STATES
from infralens.data.availability import assumed_available_at
from infralens.evaluation.backtest import (
    HOLDOUT_TARGET_START,
    latest_eia_parquet,
    load_price_panel,
    month_end_origins,
    run_expanding_backtest,
)
from infralens.evaluation.baseline import (
    availability_adjusted_seasonal_naive,
    target_period_for_origin,
)
from infralens.evaluation.features import (
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
    FeatureGapError,
    OriginFeatures,
    build_origin_features,
)

# Log-spaced penalty grid. Ties break toward the stronger penalty.
ALPHA_GRID: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
INNER_VALIDATION_ORIGINS: int = 12
MIN_FIT_ORIGINS: int = 12
HISTORY_ORIGIN_START: str = "2001-01"

SKIP_FEATURE_GAP = "feature_gap"
SKIP_INSUFFICIENT_TRAIN = "insufficient_train"
SKIP_MISSING_ACTUAL = "missing_actual"


class LinearModelError(ValueError):
    """Raised when the Ridge backtest would leak or cannot be accounted for."""


@dataclass(frozen=True)
class AlphaSelection:
    """Penalty chosen on one origin's training rows only."""

    alpha: float
    inner_mae: float
    n_fit_rows: int
    n_validation_rows: int
    fit_price_latest_mean: float


@dataclass(frozen=True)
class RidgeBacktestResult:
    """Paired development comparison of Ridge and the seasonal-naive baseline."""

    predictions: pd.DataFrame
    skips: pd.DataFrame
    mae_ridge: float
    mae_baseline_same_cases: float
    mae_improvement: float
    mae_improvement_pct: float
    mae_ridge_by_state: dict[str, float]
    mae_baseline_by_state: dict[str, float]
    n_forecasts: int
    n_attempted: int
    n_skipped_feature_gap: int
    n_skipped_insufficient_train: int
    n_skipped_missing_actual: int
    window: str
    alpha_counts: dict[float, int]
    alpha_at_last_origin: float
    last_origin: pd.Timestamp
    n_train_at_last_origin: int
    features: tuple[str, ...]
    alpha_grid: tuple[float, ...]
    max_training_target_period: str


def make_ridge_pipeline(alpha: float) -> Pipeline:
    """Scaler and one-hot encoder live inside the pipeline so they refit per fold."""
    preprocess = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), list(NUMERIC_FEATURES)),
            (
                "cat",
                OneHotEncoder(
                    drop="first",
                    handle_unknown="error",
                    sparse_output=False,
                ),
                list(CATEGORICAL_FEATURES),
            ),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocess", preprocess),
            ("model", Ridge(alpha=float(alpha), solver="cholesky")),
        ]
    )


def design_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Columns the pipeline is allowed to see."""
    missing = [column for column in MODEL_FEATURES if column not in frame.columns]
    if missing:
        raise LinearModelError(f"Design matrix is missing columns: {missing}.")
    out = frame.loc[:, list(MODEL_FEATURES)].copy()
    for column in NUMERIC_FEATURES:
        out[column] = out[column].astype(float)
    for column in CATEGORICAL_FEATURES:
        out[column] = out[column].astype(str)
    return out


def _reject_final_holdout(frame: pd.DataFrame) -> None:
    """Block the reserved target months even if a caller widens the window."""
    if frame.empty or "target_period" not in frame.columns:
        return
    if (frame["target_period"].astype(str) >= HOLDOUT_TARGET_START).any():
        raise LinearModelError("Holdout target entered training or model selection.")


def categorical_levels(pipeline: Pipeline) -> dict[str, set[str]]:
    """Categories seen by the one-hot encoder, including the dropped level."""
    encoder: OneHotEncoder = pipeline.named_steps["preprocess"].named_transformers_["cat"]
    return {
        name: {str(level) for level in levels}
        for name, levels in zip(CATEGORICAL_FEATURES, encoder.categories_, strict=True)
    }


def frame_categories_known(pipeline: Pipeline, frame: pd.DataFrame) -> bool:
    """False when scoring would require an unseen state or calendar month.

    Unseen levels are a history gap. They are not encoded as zeros.
    """
    known = categorical_levels(pipeline)
    for name, levels in known.items():
        observed = set(frame[name].astype(str))
        if not observed.issubset(levels):
            return False
    return True


def fit_ridge(train: pd.DataFrame, alpha: float) -> Pipeline:
    """Fit preprocessing and Ridge on ``train`` only."""
    if train.empty:
        raise LinearModelError("Cannot fit Ridge on an empty training frame.")
    _reject_final_holdout(train)
    pipeline = make_ridge_pipeline(alpha)
    pipeline.fit(design_matrix(train), train["actual_cents_per_kwh"].to_numpy(dtype=float))
    return pipeline


def numeric_scaler_means(pipeline: Pipeline) -> dict[str, float]:
    """Training means stored on the fitted numeric scaler, in feature order."""
    scaler: StandardScaler = pipeline.named_steps["preprocess"].named_transformers_["num"]
    return {
        name: float(value)
        for name, value in zip(NUMERIC_FEATURES, scaler.mean_, strict=True)
    }


def inner_fit_and_validation(
    train: pd.DataFrame,
    *,
    inner_validation_origins: int = INNER_VALIDATION_ORIGINS,
    min_fit_origins: int = MIN_FIT_ORIGINS,
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Split training origins into an earlier fit slice and a later validation slice.

    Returns ``None`` when the origin does not yet have enough past origins.
    The validation slice is still before the scored origin; it is only held
    out of the penalty-selection fit.
    """
    if train.empty or "forecast_origin" not in train.columns:
        return None
    if inner_validation_origins < 1 or min_fit_origins < 1:
        raise LinearModelError("Inner split sizes must be positive.")
    origins = sorted(pd.Timestamp(value) for value in train["forecast_origin"].unique())
    if len(origins) < inner_validation_origins + min_fit_origins:
        return None
    fit_origins = set(origins[:-inner_validation_origins])
    val_origins = set(origins[-inner_validation_origins:])
    fit = train.loc[train["forecast_origin"].isin(fit_origins)].copy()
    validation = train.loc[train["forecast_origin"].isin(val_origins)].copy()
    if fit.empty or validation.empty:
        return None
    if fit["forecast_origin"].max() >= validation["forecast_origin"].min():
        raise LinearModelError("Inner validation origins are not after the fit slice.")
    return fit, validation


def select_alpha(
    train: pd.DataFrame,
    *,
    alpha_grid: tuple[float, ...] = ALPHA_GRID,
    inner_validation_origins: int = INNER_VALIDATION_ORIGINS,
    min_fit_origins: int = MIN_FIT_ORIGINS,
) -> AlphaSelection | None:
    """Pick the penalty with the lowest inner-validation MAE.

    Preprocessing for each candidate is fit on the earlier slice only.
    Equal MAE (to 0.000001 ¢/kWh) keeps the larger penalty.
    """
    split = inner_fit_and_validation(
        train,
        inner_validation_origins=inner_validation_origins,
        min_fit_origins=min_fit_origins,
    )
    if split is None:
        return None
    fit, validation = split
    _reject_final_holdout(fit)
    _reject_final_holdout(validation)
    if not alpha_grid:
        raise LinearModelError("Alpha grid is empty.")
    probe = fit_ridge(fit, alpha_grid[0])
    if not frame_categories_known(probe, validation):
        return None
    y_val = validation["actual_cents_per_kwh"].to_numpy(dtype=float)
    x_val = design_matrix(validation)
    ranked: list[tuple[float, float, float, float]] = []
    for alpha in alpha_grid:
        pipeline = fit_ridge(fit, alpha)
        predicted = pipeline.predict(x_val)
        mae = float(abs(predicted - y_val).mean())
        ranked.append((round(mae, 6), -float(alpha), float(alpha), mae))
    ranked.sort()
    chosen = ranked[0][2]
    chosen_mae = float(ranked[0][3])
    return AlphaSelection(
        alpha=chosen,
        inner_mae=chosen_mae,
        n_fit_rows=int(len(fit)),
        n_validation_rows=int(len(validation)),
        fit_price_latest_mean=float(fit["price_latest"].mean()),
    )


def training_cases_for_origin(
    cases: pd.DataFrame,
    *,
    forecast_origin: pd.Timestamp,
    holdout_target_start: str = HOLDOUT_TARGET_START,
) -> pd.DataFrame:
    """Earlier cases whose label was available at ``forecast_origin``.

    A row is eligible only when all of the following hold:

    * its forecast origin is strictly earlier;
    * ``label_assumed_available_at <= forecast_origin``;
    * its target month is before the final holdout.
    """
    origin = pd.Timestamp(forecast_origin)
    if cases.empty:
        return cases.copy()
    selected = cases.loc[
        (cases["forecast_origin"] < origin)
        & (cases["label_assumed_available_at"] <= origin)
        & (cases["target_period"] < holdout_target_start)
        & cases["actual_cents_per_kwh"].notna()
    ].copy()
    if (selected["target_period"] >= holdout_target_start).any():
        raise LinearModelError("Holdout target entered the training filter.")
    if (selected["label_assumed_available_at"] > origin).any():
        raise LinearModelError("Training label is not available at the origin.")
    if (selected["forecast_origin"] >= origin).any():
        raise LinearModelError("Training includes the scored origin or a later one.")
    return selected


def _feature_record(
    features: OriginFeatures,
    *,
    actual: float | None,
) -> dict[str, object]:
    return {
        "forecast_origin": features.forecast_origin,
        "state_id": features.state_id,
        "target_period": features.target_period,
        "target_calendar_month": features.target_calendar_month,
        "actual_cents_per_kwh": actual,
        "label_assumed_available_at": assumed_available_at(features.target_period),
        "price_latest": features.price_latest,
        "price_same_month": features.price_same_month,
        "price_yoy_change": features.price_yoy_change,
        "price_trail12_mean": features.price_trail12_mean,
        "sales_latest": features.sales_latest,
        "sales_yoy_change": features.sales_yoy_change,
        "latest_period": features.latest_period,
        "latest_assumed_available_at": features.latest_assumed_available_at,
        "same_month_period": features.same_month_period,
        "same_month_assumed_available_at": features.same_month_assumed_available_at,
        "yoy_period": features.yoy_period,
        "yoy_assumed_available_at": features.yoy_assumed_available_at,
        "trail_max_assumed_available_at": max(features.trail_assumed_available_at),
    }


def _actual_map(frame: pd.DataFrame) -> dict[tuple[str, str], float]:
    return {
        (str(row.state_id).upper(), str(row.period)): row.price_cents_per_kwh
        for row in frame.itertuples(index=False)
    }


def build_feature_cases(
    frame: pd.DataFrame,
    *,
    origins: list[pd.Timestamp],
    states: tuple[str, ...],
) -> tuple[pd.DataFrame, dict[tuple[pd.Timestamp, str], str]]:
    """Featurize every origin/state pair. Gaps are returned separately."""
    actuals = _actual_map(frame)
    records: list[dict[str, object]] = []
    gaps: dict[tuple[pd.Timestamp, str], str] = {}
    for origin in origins:
        for state in states:
            key = (pd.Timestamp(origin).normalize(), state.upper())
            try:
                features = build_origin_features(
                    frame,
                    forecast_origin=origin,
                    state_id=state,
                )
            except FeatureGapError:
                gaps[key] = SKIP_FEATURE_GAP
                continue
            actual = actuals.get((state.upper(), features.target_period))
            actual_value = None if actual is None or pd.isna(actual) else float(actual)
            records.append(_feature_record(features, actual=actual_value))
    cases = pd.DataFrame.from_records(records)
    if not cases.empty:
        cases["forecast_origin"] = pd.to_datetime(cases["forecast_origin"])
        cases["label_assumed_available_at"] = pd.to_datetime(cases["label_assumed_available_at"])
    return cases, gaps


def _prediction_row(
    case: pd.Series,
    *,
    ridge_prediction: float,
    baseline_prediction: float,
    alpha: float,
    n_train: int,
) -> dict[str, object]:
    actual = float(case["actual_cents_per_kwh"])
    return {
        "forecast_origin": pd.Timestamp(case["forecast_origin"]),
        "state_id": str(case["state_id"]),
        "target_period": str(case["target_period"]),
        "actual_cents_per_kwh": actual,
        "ridge_prediction_cents_per_kwh": float(ridge_prediction),
        "baseline_prediction_cents_per_kwh": float(baseline_prediction),
        "ridge_absolute_error": abs(float(ridge_prediction) - actual),
        "baseline_absolute_error": abs(float(baseline_prediction) - actual),
        "alpha": float(alpha),
        "n_train_rows": int(n_train),
        "latest_period": str(case["latest_period"]),
        "latest_assumed_available_at": pd.Timestamp(case["latest_assumed_available_at"]),
        "same_month_period": str(case["same_month_period"]),
        "same_month_assumed_available_at": pd.Timestamp(case["same_month_assumed_available_at"]),
        "yoy_period": str(case["yoy_period"]),
        "yoy_assumed_available_at": pd.Timestamp(case["yoy_assumed_available_at"]),
        "trail_max_assumed_available_at": pd.Timestamp(case["trail_max_assumed_available_at"]),
        "label_assumed_available_at": pd.Timestamp(case["label_assumed_available_at"]),
    }


def run_ridge_backtest(
    frame: pd.DataFrame,
    *,
    origin_start: str = "2002-01",
    origin_end: str = "2024-06",
    history_origin_start: str = HISTORY_ORIGIN_START,
    states: tuple[str, ...] = USER_FACING_STATES,
    window: str = "development",
    holdout_target_start: str = HOLDOUT_TARGET_START,
    alpha_grid: tuple[float, ...] = ALPHA_GRID,
    inner_validation_origins: int = INNER_VALIDATION_ORIGINS,
    min_fit_origins: int = MIN_FIT_ORIGINS,
) -> RidgeBacktestResult:
    """Score Ridge on the development origin grid and pair it with the baseline.

    Origins whose target month falls in the final holdout are not attempted.
    Cases that lack lagged history, a realized actual, or enough earlier
    labels are counted in the skip totals and are not imputed.
    """
    if history_origin_start > origin_start:
        raise LinearModelError("History must start on or before the scored window.")
    if holdout_target_start > HOLDOUT_TARGET_START:
        raise LinearModelError("The final holdout cannot be moved later than 2025-07.")
    history_origins = month_end_origins(history_origin_start, origin_end)
    cases, gaps = build_feature_cases(frame, origins=history_origins, states=states)
    case_index: dict[tuple[pd.Timestamp, str], pd.Series] = {}
    if not cases.empty:
        for _, row in cases.iterrows():
            case_index[(pd.Timestamp(row["forecast_origin"]), str(row["state_id"]))] = row

    records: list[dict[str, object]] = []
    skip_records: list[dict[str, object]] = []
    n_attempted = 0
    n_feature_gap = 0
    n_insufficient_train = 0
    n_missing_actual = 0
    max_training_target = ""

    for origin in month_end_origins(origin_start, origin_end):
        origin = pd.Timestamp(origin)
        target_period = target_period_for_origin(origin)
        if target_period >= holdout_target_start:
            continue
        train = training_cases_for_origin(
            cases,
            forecast_origin=origin,
            holdout_target_start=holdout_target_start,
        )
        if not train.empty:
            origin_max_target = str(train["target_period"].max())
            if origin_max_target >= holdout_target_start:
                raise LinearModelError("Holdout target entered training.")
            if origin_max_target > max_training_target:
                max_training_target = origin_max_target
        selection = select_alpha(
            train,
            alpha_grid=alpha_grid,
            inner_validation_origins=inner_validation_origins,
            min_fit_origins=min_fit_origins,
        )
        model: Pipeline | None = None
        if selection is not None:
            model = fit_ridge(train, selection.alpha)
            scaler_means = numeric_scaler_means(model)
            train_means = {
                name: float(train[name].mean()) for name in NUMERIC_FEATURES
            }
            for name, fitted_mean in scaler_means.items():
                if abs(fitted_mean - train_means[name]) > 1e-8:
                    raise LinearModelError(
                        f"Scaler for {name} was not fit on this origin's training rows."
                    )
            if train["forecast_origin"].max() >= origin:
                raise LinearModelError("Fitted training rows are not strictly before the origin.")
        fitted_origin = None if model is None or selection is None else (
            model,
            selection.alpha,
            int(len(train)),
        )

        for state in states:
            n_attempted += 1
            key = (origin.normalize(), state.upper())
            if key in gaps:
                n_feature_gap += 1
                skip_records.append(
                    {
                        "forecast_origin": origin.normalize(),
                        "state_id": state.upper(),
                        "target_period": target_period,
                        "skip_reason": SKIP_FEATURE_GAP,
                    }
                )
                continue
            case = case_index.get(key)
            if case is None:
                raise LinearModelError(f"Missing feature row for {state} at {origin.date()}.")
            if pd.isna(case["actual_cents_per_kwh"]):
                n_missing_actual += 1
                skip_records.append(
                    {
                        "forecast_origin": origin.normalize(),
                        "state_id": state.upper(),
                        "target_period": target_period,
                        "skip_reason": SKIP_MISSING_ACTUAL,
                    }
                )
                continue
            fitted = fitted_origin
            if fitted is None:
                n_insufficient_train += 1
                skip_records.append(
                    {
                        "forecast_origin": origin.normalize(),
                        "state_id": state.upper(),
                        "target_period": target_period,
                        "skip_reason": SKIP_INSUFFICIENT_TRAIN,
                    }
                )
                continue
            model, alpha, n_train = fitted
            row_frame = pd.DataFrame([case.to_dict()])
            if not frame_categories_known(model, row_frame):
                n_insufficient_train += 1
                skip_records.append(
                    {
                        "forecast_origin": origin.normalize(),
                        "state_id": state.upper(),
                        "target_period": target_period,
                        "skip_reason": SKIP_INSUFFICIENT_TRAIN,
                    }
                )
                continue
            for stamp_column in (
                "latest_assumed_available_at",
                "same_month_assumed_available_at",
                "yoy_assumed_available_at",
                "trail_max_assumed_available_at",
            ):
                if pd.Timestamp(case[stamp_column]) > origin:
                    raise LinearModelError(
                        f"Feature {stamp_column} is after the forecast origin."
                    )
            if str(case["target_period"]) != target_period:
                raise LinearModelError("Scored target is not 12 months after the origin.")
            baseline = availability_adjusted_seasonal_naive(
                frame,
                forecast_origin=origin,
                state_id=state,
            )
            if float(baseline["prediction_cents_per_kwh"]) != float(case["price_same_month"]):
                raise LinearModelError("price_same_month diverges from the seasonal-naive baseline.")
            predicted = float(model.predict(design_matrix(row_frame))[0])
            records.append(
                _prediction_row(
                    case,
                    ridge_prediction=predicted,
                    baseline_prediction=float(baseline["prediction_cents_per_kwh"]),
                    alpha=alpha,
                    n_train=n_train,
                )
            )

    n_scored = len(records)
    if n_attempted != n_scored + n_feature_gap + n_insufficient_train + n_missing_actual:
        raise LinearModelError("Skip accounting invariant failed.")
    if n_attempted == 0:
        raise LinearModelError("Ridge backtest attempted no development cells.")
    if n_scored == 0:
        raise LinearModelError("Ridge backtest produced no scored forecasts.")

    predictions = pd.DataFrame.from_records(records)
    if (predictions["target_period"] >= holdout_target_start).any():
        raise LinearModelError("Holdout target was scored.")
    leaked = (
        (predictions["latest_assumed_available_at"] > predictions["forecast_origin"])
        | (predictions["same_month_assumed_available_at"] > predictions["forecast_origin"])
        | (predictions["yoy_assumed_available_at"] > predictions["forecast_origin"])
        | (predictions["trail_max_assumed_available_at"] > predictions["forecast_origin"])
    )
    if leaked.any():
        raise LinearModelError("A scored feature uses an observation after the origin.")

    skips = pd.DataFrame.from_records(
        skip_records,
        columns=["forecast_origin", "state_id", "target_period", "skip_reason"],
    )
    mae_ridge = float(predictions["ridge_absolute_error"].mean())
    mae_baseline = float(predictions["baseline_absolute_error"].mean())
    if mae_baseline == 0:
        improvement_pct = 0.0
    else:
        improvement_pct = 100.0 * (mae_baseline - mae_ridge) / mae_baseline
    mae_ridge_by_state = {
        state: float(group["ridge_absolute_error"].mean())
        for state, group in predictions.groupby("state_id")
    }
    mae_baseline_by_state = {
        state: float(group["baseline_absolute_error"].mean())
        for state, group in predictions.groupby("state_id")
    }
    last_origin = pd.Timestamp(predictions["forecast_origin"].max())
    last_rows = predictions.loc[predictions["forecast_origin"] == last_origin]
    alpha_counts: dict[float, int] = {}
    for alpha in predictions.drop_duplicates("forecast_origin")["alpha"]:
        key = float(alpha)
        alpha_counts[key] = alpha_counts.get(key, 0) + 1
    return RidgeBacktestResult(
        predictions=predictions,
        skips=skips,
        mae_ridge=mae_ridge,
        mae_baseline_same_cases=mae_baseline,
        mae_improvement=mae_baseline - mae_ridge,
        mae_improvement_pct=improvement_pct,
        mae_ridge_by_state=mae_ridge_by_state,
        mae_baseline_by_state=mae_baseline_by_state,
        n_forecasts=n_scored,
        n_attempted=n_attempted,
        n_skipped_feature_gap=n_feature_gap,
        n_skipped_insufficient_train=n_insufficient_train,
        n_skipped_missing_actual=n_missing_actual,
        window=window,
        alpha_counts=alpha_counts,
        alpha_at_last_origin=float(last_rows["alpha"].iloc[0]),
        last_origin=last_origin,
        n_train_at_last_origin=int(last_rows["n_train_rows"].iloc[0]),
        features=MODEL_FEATURES,
        alpha_grid=tuple(float(value) for value in alpha_grid),
        max_training_target_period=max_training_target,
    )


def _print_result(
    result: RidgeBacktestResult,
    *,
    parquet_path: Path,
    full_baseline_mae: float,
    full_baseline_n: int,
) -> None:
    print(f"window: {result.window}")
    print(f"parquet: {parquet_path}")
    print(f"n_attempted: {result.n_attempted}")
    print(f"n_scored: {result.n_forecasts}")
    print(f"n_skipped_feature_gap: {result.n_skipped_feature_gap}")
    print(f"n_skipped_insufficient_train: {result.n_skipped_insufficient_train}")
    print(f"n_skipped_missing_actual: {result.n_skipped_missing_actual}")
    print(f"full_baseline_n_scored: {full_baseline_n}")
    print(f"full_baseline_mae_cents_per_kwh: {full_baseline_mae:.4f}")
    print(f"paired_baseline_mae_cents_per_kwh: {result.mae_baseline_same_cases:.4f}")
    print(f"ridge_mae_cents_per_kwh: {result.mae_ridge:.4f}")
    print(f"mae_improvement_cents_per_kwh: {result.mae_improvement:.4f}")
    print(f"mae_improvement_pct: {result.mae_improvement_pct:.4f}")
    print("mae_by_state_cents_per_kwh:")
    for state in sorted(result.mae_ridge_by_state):
        ridge = result.mae_ridge_by_state[state]
        baseline = result.mae_baseline_by_state[state]
        delta = baseline - ridge
        print(
            f"  {state}: ridge={ridge:.4f} baseline={baseline:.4f} "
            f"improvement={delta:.4f}"
        )
    print(f"alpha_grid: {list(result.alpha_grid)}")
    print(
        "alpha_selection: per origin, last "
        f"{INNER_VALIDATION_ORIGINS} training origins held out for MAE; "
        f"refit on all pre-origin labels; ties keep the larger alpha"
    )
    print("alpha_counts_by_origin:")
    for alpha, count in sorted(result.alpha_counts.items()):
        print(f"  {alpha:g}: {count}")
    print(f"alpha_at_last_origin: {result.alpha_at_last_origin:g}")
    print(f"last_origin: {result.last_origin.date()}")
    print(f"n_train_at_last_origin: {result.n_train_at_last_origin}")
    print(f"max_training_target_period: {result.max_training_target_period}")
    print(f"features: {', '.join(result.features)}")
    print(f"run_at: {datetime.now().isoformat(timespec='seconds')}")


def main() -> int:
    parquet_path = latest_eia_parquet()
    frame = load_price_panel(parquet_path)
    baseline = run_expanding_backtest(frame)
    result = run_ridge_backtest(frame)
    _print_result(
        result,
        parquet_path=parquet_path,
        full_baseline_mae=baseline.mae_overall,
        full_baseline_n=baseline.n_forecasts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

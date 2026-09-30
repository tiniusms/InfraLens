"""Expanding-origin histogram gradient-boosting candidate.

Uses the same EIA feature rows, origin grid, m+3 rule, and final holdout as
the Ridge backtest. State and month are ordinal-encoded inside each training
fold because ``HistGradientBoostingRegressor`` expects categorical columns as
non-negative integer codes, not one-hot indicators. Numeric columns are left
unscaled: the booster's bin edges are fit on that fold's raw values.

The searched grid is six (max_depth, learning_rate) pairs. It was fixed
before the development run. ``min_samples_leaf``, ``max_iter``, and the
other booster settings are not searched. sklearn's random early-stopping
split is off, because that split is not time-ordered.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import OrdinalEncoder

from infralens.data import USER_FACING_STATES
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
)
from infralens.evaluation.linear import (
    HISTORY_ORIGIN_START,
    INNER_VALIDATION_ORIGINS,
    MIN_FIT_ORIGINS,
    SKIP_FEATURE_GAP,
    SKIP_INSUFFICIENT_TRAIN,
    SKIP_MISSING_ACTUAL,
    LinearModelError,
    build_feature_cases,
    inner_fit_and_validation,
    run_ridge_backtest,
    training_cases_for_origin,
)

# Depth is the nonlinearity knob. Learning rate is the shrinkage knob.
# Ties keep the smaller depth, then the smaller learning rate.
TREE_GRID: tuple[tuple[int, float], ...] = (
    (2, 0.05),
    (2, 0.1),
    (3, 0.05),
    (3, 0.1),
    (6, 0.05),
    (6, 0.1),
)
MAX_ITER: int = 100
MIN_SAMPLES_LEAF: int = 20
MAX_LEAF_NODES: int = 31
L2_REGULARIZATION: float = 0.0
RANDOM_STATE: int = 0

CATEGORICAL_FEATURE_INDEXES: tuple[int, ...] = tuple(
    range(len(NUMERIC_FEATURES), len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES))
)


class TreeModelError(LinearModelError):
    """Raised when the tree backtest would leak or cannot be accounted for."""


@dataclass(frozen=True)
class TreeHyperparameters:
    """The two settings chosen at one origin. Other booster settings are fixed."""

    max_depth: int
    learning_rate: float

    def as_key(self) -> tuple[int, float]:
        return (int(self.max_depth), float(self.learning_rate))


@dataclass(frozen=True)
class FittedTree:
    """Booster and the ordinal encoder fit on the same rows."""

    model: HistGradientBoostingRegressor
    encoder: OrdinalEncoder
    params: TreeHyperparameters


@dataclass(frozen=True)
class TreeSelection:
    """Hyperparameters chosen on one origin's earlier training origins only."""

    params: TreeHyperparameters
    inner_mae: float
    n_fit_rows: int
    n_validation_rows: int
    fit_category_levels: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class TreeBacktestResult:
    """Tree scores paired with the seasonal-naive baseline on the same rows."""

    predictions: pd.DataFrame
    skips: pd.DataFrame
    mae_tree: float
    mae_baseline_same_cases: float
    mae_improvement_vs_baseline: float
    mae_improvement_vs_baseline_pct: float
    mae_tree_by_state: dict[str, float]
    mae_baseline_by_state: dict[str, float]
    n_forecasts: int
    n_attempted: int
    n_skipped_feature_gap: int
    n_skipped_insufficient_train: int
    n_skipped_missing_actual: int
    window: str
    param_counts: dict[tuple[int, float], int]
    params_at_last_origin: TreeHyperparameters
    first_origin: pd.Timestamp
    last_origin: pd.Timestamp
    n_train_at_last_origin: int
    features: tuple[str, ...]
    grid: tuple[tuple[int, float], ...]
    max_training_target_period: str


@dataclass(frozen=True)
class CommonCaseComparison:
    """Ridge and the tree model on the intersection of their scored cases."""

    n_tree: int
    n_ridge: int
    n_common: int
    mae_tree: float
    mae_ridge: float
    mae_baseline: float
    mae_improvement_vs_ridge: float
    mae_improvement_vs_ridge_pct: float
    mae_tree_by_state: dict[str, float]
    mae_ridge_by_state: dict[str, float]
    mae_baseline_by_state: dict[str, float]


def _grid(values: tuple[tuple[int, float], ...]) -> tuple[TreeHyperparameters, ...]:
    if not values:
        raise TreeModelError("Tree hyperparameter grid is empty.")
    return tuple(
        TreeHyperparameters(max_depth=int(depth), learning_rate=float(rate))
        for depth, rate in values
    )


def fit_category_encoder(train: pd.DataFrame) -> OrdinalEncoder:
    """Map state and month to integer codes using ``train`` categories only.

    Unknown levels raise. They are not coded as missing, because this booster
    treats a negative categorical code as a missing value.
    """
    encoder = OrdinalEncoder(handle_unknown="error", dtype=np.int32)
    encoder.fit(train.loc[:, list(CATEGORICAL_FEATURES)].astype(str))
    return encoder


def category_levels(encoder: OrdinalEncoder) -> dict[str, tuple[str, ...]]:
    """Categories learned by ``encoder``, in code order."""
    return {
        name: tuple(str(level) for level in levels)
        for name, levels in zip(CATEGORICAL_FEATURES, encoder.categories_, strict=True)
    }


def model_matrix(frame: pd.DataFrame, encoder: OrdinalEncoder) -> np.ndarray:
    """Numeric features, then integer state and month codes.

    Column positions match ``CATEGORICAL_FEATURE_INDEXES``.
    """
    missing = [column for column in MODEL_FEATURES if column not in frame.columns]
    if missing:
        raise TreeModelError(f"Design matrix is missing columns: {missing}.")
    numeric = frame.loc[:, list(NUMERIC_FEATURES)].to_numpy(dtype=float)
    try:
        categorical = np.asarray(
            encoder.transform(frame.loc[:, list(CATEGORICAL_FEATURES)].astype(str)),
            dtype=np.int32,
        )
    except ValueError as exc:
        if "unknown categor" in str(exc).lower():
            raise TreeModelError(
                "Category was not present in the training fold."
            ) from exc
        raise
    if categorical.size and int(categorical.min()) < 0:
        raise TreeModelError(
            "Negative category codes are missing-value markers and are not used."
        )
    matrix = np.column_stack([numeric, categorical])
    if matrix.shape[1] != len(MODEL_FEATURES):
        raise TreeModelError("Model matrix width does not match the feature list.")
    return matrix


def make_booster(params: TreeHyperparameters) -> HistGradientBoostingRegressor:
    """Histogram booster with categorical state and month columns."""
    return HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=float(params.learning_rate),
        max_iter=MAX_ITER,
        max_leaf_nodes=MAX_LEAF_NODES,
        max_depth=int(params.max_depth),
        min_samples_leaf=MIN_SAMPLES_LEAF,
        l2_regularization=L2_REGULARIZATION,
        early_stopping=False,
        categorical_features=list(CATEGORICAL_FEATURE_INDEXES),
        random_state=RANDOM_STATE,
    )


def fit_tree(train: pd.DataFrame, params: TreeHyperparameters) -> FittedTree:
    """Fit the ordinal encoder and booster on ``train`` only."""
    if train.empty:
        raise TreeModelError("Cannot fit a tree on an empty training frame.")
    if (train["target_period"].astype(str) >= HOLDOUT_TARGET_START).any():
        raise LinearModelError("Holdout target entered training or model selection.")
    encoder = fit_category_encoder(train)
    model = make_booster(params)
    model.fit(
        model_matrix(train, encoder),
        train["actual_cents_per_kwh"].to_numpy(dtype=float),
    )
    return FittedTree(model=model, encoder=encoder, params=params)


def predict_tree(fitted: FittedTree, frame: pd.DataFrame) -> np.ndarray:
    """Score ``frame`` with the encoder that was fit beside ``fitted``."""
    return np.asarray(fitted.model.predict(model_matrix(frame, fitted.encoder)), dtype=float)


def select_tree_params(
    train: pd.DataFrame,
    *,
    grid: tuple[tuple[int, float], ...] = TREE_GRID,
    inner_validation_origins: int = INNER_VALIDATION_ORIGINS,
    min_fit_origins: int = MIN_FIT_ORIGINS,
) -> TreeSelection | None:
    """Pick depth and learning rate on a time-ordered inner split of ``train``.

    The encoder and each booster are fit on the earlier slice only. The later
    slice is used for MAE. Equal MAE (to 0.000001 ¢/kWh) keeps the smaller
    depth, then the smaller learning rate. Returns ``None`` when the origin
    does not yet have enough labeled history, or when the validation slice
    contains a state or month absent from the fit slice.
    """
    split = inner_fit_and_validation(
        train,
        inner_validation_origins=inner_validation_origins,
        min_fit_origins=min_fit_origins,
    )
    if split is None:
        return None
    fit, validation = split
    if (fit["target_period"].astype(str) >= HOLDOUT_TARGET_START).any():
        raise LinearModelError("Holdout target entered training or model selection.")
    if (validation["target_period"].astype(str) >= HOLDOUT_TARGET_START).any():
        raise LinearModelError("Holdout target entered training or model selection.")
    try:
        encoder = fit_category_encoder(fit)
        x_fit = model_matrix(fit, encoder)
        x_val = model_matrix(validation, encoder)
    except TreeModelError:
        return None
    y_fit = fit["actual_cents_per_kwh"].to_numpy(dtype=float)
    y_val = validation["actual_cents_per_kwh"].to_numpy(dtype=float)
    ranked: list[tuple[float, int, float, TreeHyperparameters, float]] = []
    for params in _grid(grid):
        model = make_booster(params)
        model.fit(x_fit, y_fit)
        predicted = np.asarray(model.predict(x_val), dtype=float)
        mae = float(np.abs(predicted - y_val).mean())
        ranked.append(
            (
                round(mae, 6),
                int(params.max_depth),
                float(params.learning_rate),
                params,
                mae,
            )
        )
    ranked.sort()
    chosen = ranked[0][3]
    chosen_mae = float(ranked[0][4])
    return TreeSelection(
        params=chosen,
        inner_mae=chosen_mae,
        n_fit_rows=int(len(fit)),
        n_validation_rows=int(len(validation)),
        fit_category_levels=category_levels(encoder),
    )


def _prediction_row(
    case: pd.Series,
    *,
    tree_prediction: float,
    baseline_prediction: float,
    params: TreeHyperparameters,
    n_train: int,
) -> dict[str, object]:
    actual = float(case["actual_cents_per_kwh"])
    return {
        "forecast_origin": pd.Timestamp(case["forecast_origin"]),
        "state_id": str(case["state_id"]),
        "target_period": str(case["target_period"]),
        "actual_cents_per_kwh": actual,
        "tree_prediction_cents_per_kwh": float(tree_prediction),
        "baseline_prediction_cents_per_kwh": float(baseline_prediction),
        "tree_absolute_error": abs(float(tree_prediction) - actual),
        "baseline_absolute_error": abs(float(baseline_prediction) - actual),
        "max_depth": int(params.max_depth),
        "learning_rate": float(params.learning_rate),
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


def run_tree_backtest(
    frame: pd.DataFrame,
    *,
    origin_start: str = "2002-01",
    origin_end: str = "2024-06",
    history_origin_start: str = HISTORY_ORIGIN_START,
    states: tuple[str, ...] = USER_FACING_STATES,
    window: str = "development",
    holdout_target_start: str = HOLDOUT_TARGET_START,
    grid: tuple[tuple[int, float], ...] = TREE_GRID,
    inner_validation_origins: int = INNER_VALIDATION_ORIGINS,
    min_fit_origins: int = MIN_FIT_ORIGINS,
) -> TreeBacktestResult:
    """Score the tree on the development origin grid and pair it with the baseline.

    Feature rows come from ``build_feature_cases``. Training rows come from
    ``training_cases_for_origin``. Both are the Ridge backtest's functions.
    """
    if history_origin_start > origin_start:
        raise TreeModelError("History must start on or before the scored window.")
    if holdout_target_start > HOLDOUT_TARGET_START:
        raise TreeModelError("The final holdout cannot be moved later than 2025-07.")
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
                raise TreeModelError("Holdout target entered training.")
            if origin_max_target > max_training_target:
                max_training_target = origin_max_target
            if pd.Timestamp(train["forecast_origin"].max()) >= origin:
                raise TreeModelError("Training includes the scored origin or a later one.")
        selection = select_tree_params(
            train,
            grid=grid,
            inner_validation_origins=inner_validation_origins,
            min_fit_origins=min_fit_origins,
        )
        fitted: FittedTree | None = None
        if selection is not None:
            fitted = fit_tree(train, selection.params)
            if pd.Timestamp(train["forecast_origin"].max()) >= origin:
                raise TreeModelError("Fitted training rows are not strictly before the origin.")

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
                raise TreeModelError(f"Missing feature row for {state} at {origin.date()}.")
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
            row_frame = pd.DataFrame([case.to_dict()])
            try:
                predicted_row = predict_tree(fitted, row_frame)
            except TreeModelError:
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
                    raise TreeModelError(
                        f"Feature {stamp_column} is after the forecast origin."
                    )
            if str(case["target_period"]) != target_period:
                raise TreeModelError("Scored target is not 12 months after the origin.")
            baseline = availability_adjusted_seasonal_naive(
                frame,
                forecast_origin=origin,
                state_id=state,
            )
            if float(baseline["prediction_cents_per_kwh"]) != float(case["price_same_month"]):
                raise TreeModelError(
                    "price_same_month diverges from the seasonal-naive baseline."
                )
            records.append(
                _prediction_row(
                    case,
                    tree_prediction=float(predicted_row[0]),
                    baseline_prediction=float(baseline["prediction_cents_per_kwh"]),
                    params=fitted.params,
                    n_train=int(len(train)),
                )
            )

    n_scored = len(records)
    if n_attempted != n_scored + n_feature_gap + n_insufficient_train + n_missing_actual:
        raise TreeModelError("Skip accounting invariant failed.")
    if n_attempted == 0:
        raise TreeModelError("Tree backtest attempted no development cells.")
    if n_scored == 0:
        raise TreeModelError("Tree backtest produced no scored forecasts.")

    predictions = pd.DataFrame.from_records(records)
    if (predictions["target_period"] >= holdout_target_start).any():
        raise TreeModelError("Holdout target was scored.")
    leaked = (
        (predictions["latest_assumed_available_at"] > predictions["forecast_origin"])
        | (predictions["same_month_assumed_available_at"] > predictions["forecast_origin"])
        | (predictions["yoy_assumed_available_at"] > predictions["forecast_origin"])
        | (predictions["trail_max_assumed_available_at"] > predictions["forecast_origin"])
    )
    if leaked.any():
        raise TreeModelError("A scored feature uses an observation after the origin.")

    skips = pd.DataFrame.from_records(
        skip_records,
        columns=["forecast_origin", "state_id", "target_period", "skip_reason"],
    )
    mae_tree = float(predictions["tree_absolute_error"].mean())
    mae_baseline = float(predictions["baseline_absolute_error"].mean())
    if mae_baseline == 0:
        improvement_pct = 0.0
    else:
        improvement_pct = 100.0 * (mae_baseline - mae_tree) / mae_baseline
    param_counts: dict[tuple[int, float], int] = {}
    origin_params = predictions.drop_duplicates("forecast_origin")
    for row in origin_params.itertuples(index=False):
        key = (int(row.max_depth), float(row.learning_rate))
        param_counts[key] = param_counts.get(key, 0) + 1
    first_origin = pd.Timestamp(predictions["forecast_origin"].min())
    last_origin = pd.Timestamp(predictions["forecast_origin"].max())
    last_rows = predictions.loc[predictions["forecast_origin"] == last_origin]
    return TreeBacktestResult(
        predictions=predictions,
        skips=skips,
        mae_tree=mae_tree,
        mae_baseline_same_cases=mae_baseline,
        mae_improvement_vs_baseline=mae_baseline - mae_tree,
        mae_improvement_vs_baseline_pct=improvement_pct,
        mae_tree_by_state={
            state: float(group["tree_absolute_error"].mean())
            for state, group in predictions.groupby("state_id")
        },
        mae_baseline_by_state={
            state: float(group["baseline_absolute_error"].mean())
            for state, group in predictions.groupby("state_id")
        },
        n_forecasts=n_scored,
        n_attempted=n_attempted,
        n_skipped_feature_gap=n_feature_gap,
        n_skipped_insufficient_train=n_insufficient_train,
        n_skipped_missing_actual=n_missing_actual,
        window=window,
        param_counts=param_counts,
        params_at_last_origin=TreeHyperparameters(
            max_depth=int(last_rows["max_depth"].iloc[0]),
            learning_rate=float(last_rows["learning_rate"].iloc[0]),
        ),
        first_origin=first_origin,
        last_origin=last_origin,
        n_train_at_last_origin=int(last_rows["n_train_rows"].iloc[0]),
        features=MODEL_FEATURES,
        grid=tuple((int(depth), float(rate)) for depth, rate in grid),
        max_training_target_period=max_training_target,
    )


def compare_with_ridge(
    tree: TreeBacktestResult,
    ridge_predictions: pd.DataFrame,
) -> CommonCaseComparison:
    """MAE for both models on the intersection of scored cases.

    The baseline column is the tree result's seasonal-naive error. It must
    match the Ridge result's baseline error on those same cases.
    """
    ridge = ridge_predictions.copy()
    merged = tree.predictions.merge(
        ridge,
        on=["state_id", "forecast_origin", "target_period"],
        how="inner",
        suffixes=("_tree", "_ridge"),
    )
    if merged.empty:
        raise TreeModelError("Ridge and the tree model share no scored cases.")
    baseline_tree = merged["baseline_absolute_error_tree"].to_numpy(dtype=float)
    baseline_ridge = merged["baseline_absolute_error_ridge"].to_numpy(dtype=float)
    if not np.allclose(baseline_tree, baseline_ridge):
        raise TreeModelError("Baseline errors diverged on common cases.")
    actual_tree = merged["actual_cents_per_kwh_tree"].to_numpy(dtype=float)
    actual_ridge = merged["actual_cents_per_kwh_ridge"].to_numpy(dtype=float)
    if not np.allclose(actual_tree, actual_ridge):
        raise TreeModelError("Actuals diverged on common cases.")
    mae_tree = float(merged["tree_absolute_error"].mean())
    mae_ridge = float(merged["ridge_absolute_error"].mean())
    mae_baseline = float(merged["baseline_absolute_error_tree"].mean())
    if mae_ridge == 0:
        versus_ridge_pct = 0.0
    else:
        versus_ridge_pct = 100.0 * (mae_ridge - mae_tree) / mae_ridge
    return CommonCaseComparison(
        n_tree=int(tree.n_forecasts),
        n_ridge=int(len(ridge)),
        n_common=int(len(merged)),
        mae_tree=mae_tree,
        mae_ridge=mae_ridge,
        mae_baseline=mae_baseline,
        mae_improvement_vs_ridge=mae_ridge - mae_tree,
        mae_improvement_vs_ridge_pct=versus_ridge_pct,
        mae_tree_by_state={
            state: float(group["tree_absolute_error"].mean())
            for state, group in merged.groupby("state_id")
        },
        mae_ridge_by_state={
            state: float(group["ridge_absolute_error"].mean())
            for state, group in merged.groupby("state_id")
        },
        mae_baseline_by_state={
            state: float(group["baseline_absolute_error_tree"].mean())
            for state, group in merged.groupby("state_id")
        },
    )


def _print_result(
    tree: TreeBacktestResult,
    common: CommonCaseComparison,
    *,
    parquet_path: Path,
    full_baseline_mae: float,
    full_baseline_n: int,
) -> None:
    print(f"window: {tree.window}")
    print(f"parquet: {parquet_path}")
    print(f"n_attempted: {tree.n_attempted}")
    print(f"n_scored_tree: {tree.n_forecasts}")
    print(f"n_skipped_feature_gap: {tree.n_skipped_feature_gap}")
    print(f"n_skipped_insufficient_train: {tree.n_skipped_insufficient_train}")
    print(f"n_skipped_missing_actual: {tree.n_skipped_missing_actual}")
    print(f"full_baseline_n_scored: {full_baseline_n}")
    print(f"full_baseline_mae_cents_per_kwh: {full_baseline_mae:.4f}")
    print(f"paired_baseline_mae_cents_per_kwh: {tree.mae_baseline_same_cases:.4f}")
    print(f"tree_mae_cents_per_kwh: {tree.mae_tree:.4f}")
    print(f"mae_improvement_vs_baseline_cents_per_kwh: {tree.mae_improvement_vs_baseline:.4f}")
    print(f"mae_improvement_vs_baseline_pct: {tree.mae_improvement_vs_baseline_pct:.4f}")
    print(f"n_scored_ridge: {common.n_ridge}")
    print(f"n_common: {common.n_common}")
    print(f"common_baseline_mae_cents_per_kwh: {common.mae_baseline:.4f}")
    print(f"common_ridge_mae_cents_per_kwh: {common.mae_ridge:.4f}")
    print(f"common_tree_mae_cents_per_kwh: {common.mae_tree:.4f}")
    print(f"mae_improvement_vs_ridge_cents_per_kwh: {common.mae_improvement_vs_ridge:.4f}")
    print(f"mae_improvement_vs_ridge_pct: {common.mae_improvement_vs_ridge_pct:.4f}")
    print("mae_by_state_on_common_cases_cents_per_kwh:")
    for state in sorted(common.mae_tree_by_state):
        print(
            f"  {state}: tree={common.mae_tree_by_state[state]:.4f} "
            f"ridge={common.mae_ridge_by_state[state]:.4f} "
            f"baseline={common.mae_baseline_by_state[state]:.4f}"
        )
    print(
        "hyperparameters_fixed: "
        f"loss=squared_error max_iter={MAX_ITER} min_samples_leaf={MIN_SAMPLES_LEAF} "
        f"max_leaf_nodes={MAX_LEAF_NODES} l2_regularization={L2_REGULARIZATION} "
        "early_stopping=False"
    )
    print(f"hyperparameter_grid: {list(tree.grid)}")
    print(
        "hyperparameter_selection: per origin, last "
        f"{INNER_VALIDATION_ORIGINS} training origins held out for MAE; "
        "ordinal encoder and booster fit on the earlier slice only; "
        "refit on all pre-origin labels; ties keep the smaller depth, "
        "then the smaller learning rate"
    )
    print("hyperparameter_counts_by_origin:")
    for key, count in sorted(tree.param_counts.items()):
        depth, rate = key
        print(f"  max_depth={depth} learning_rate={rate:g}: {count}")
    last = tree.params_at_last_origin
    print(
        "params_at_last_origin: "
        f"max_depth={last.max_depth} learning_rate={last.learning_rate:g}"
    )
    print(f"first_origin: {tree.first_origin.date()}")
    print(f"last_origin: {tree.last_origin.date()}")
    print(f"n_train_at_last_origin: {tree.n_train_at_last_origin}")
    print(f"max_training_target_period: {tree.max_training_target_period}")
    print(f"features: {', '.join(tree.features)}")
    print(
        "categorical_encoding: OrdinalEncoder fit on the training fold only; "
        "unknown levels skip the case; numeric features are not scaled"
    )
    print(f"run_at: {datetime.now().isoformat(timespec='seconds')}")


def main() -> int:
    parquet_path = latest_eia_parquet()
    frame = load_price_panel(parquet_path)
    baseline = run_expanding_backtest(frame)
    ridge = run_ridge_backtest(frame)
    tree = run_tree_backtest(frame)
    common = compare_with_ridge(tree, ridge.predictions)
    _print_result(
        tree,
        common,
        parquet_path=parquet_path,
        full_baseline_mae=baseline.mae_overall,
        full_baseline_n=baseline.n_forecasts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

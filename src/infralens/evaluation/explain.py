"""Exact linear explanations for frozen rolling-origin Ridge forecasts.

Ridge is refit at every forecast origin. A coefficient belongs to that origin's
pipeline, not to a single InfraLens model. Contributions use the fitted
identity

``prediction = intercept + sum(transformed_value * coefficient)``.

Numeric coefficients are in cents per kWh per training-fold standard
deviation. State and month coefficients are contrasts against the one-hot
category dropped at that origin. Neither is a causal effect. The dropped
reference is not stored as a zero coefficient.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from infralens.data import USER_FACING_STATES
from infralens.evaluation.backtest import (
    HOLDOUT_TARGET_START,
    latest_eia_parquet,
    load_price_panel,
    month_end_origins,
)
from infralens.evaluation.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from infralens.evaluation.linear import (
    HISTORY_ORIGIN_START,
    build_feature_cases,
    design_matrix,
    fit_ridge,
    frame_categories_known,
    numeric_scaler_means,
    run_ridge_backtest,
    training_cases_for_origin,
)

RECONSTRUCTION_TOLERANCE: float = 1e-8
FROZEN_RIDGE_CASE_COUNT: int = 1145
FROZEN_RIDGE_MAE_ROUNDED: float = 0.7075

_PREDICTION_COLUMNS: tuple[str, ...] = (
    "state_id",
    "forecast_origin",
    "target_period",
    "ridge_prediction_cents_per_kwh",
    "actual_cents_per_kwh",
    "alpha",
    "n_train_rows",
)

TERM_COLUMNS: tuple[str, ...] = (
    "state_id",
    "forecast_origin",
    "target_period",
    "ridge_prediction_cents_per_kwh",
    "intercept",
    "transformed_feature_name",
    "feature_name",
    "feature_group",
    "category",
    "raw_numeric_value",
    "transformed_value",
    "coefficient",
    "contribution",
    "scaler_mean",
    "scaler_scale",
)

_GROUP_FOR_CATEGORY: dict[str, str] = {
    "state_id": "state",
    "target_calendar_month": "month",
}


class ExplainError(ValueError):
    """Raised when an explanation would invent a coefficient or open the holdout."""


@dataclass(frozen=True)
class CoefficientStat:
    """Distribution of one origin-specific coefficient across development fits."""

    feature_group: str
    feature_name: str
    category: str | None
    n_origins: int
    median: float
    minimum: float
    maximum: float
    n_positive: int
    n_negative: int
    n_zero: int
    final_coefficient: float

    @property
    def changes_sign(self) -> bool:
        return self.n_positive > 0 and self.n_negative > 0


@dataclass(frozen=True)
class CoefficientSummary:
    """Descriptive stability of origin-specific coefficients. Not one global model."""

    n_origins: int
    reference_states: tuple[str, ...]
    reference_months: tuple[str, ...]
    numeric: tuple[CoefficientStat, ...]
    state: tuple[CoefficientStat, ...]
    month: tuple[CoefficientStat, ...]

    @property
    def references_constant(self) -> bool:
        return len(self.reference_states) == 1 and len(self.reference_months) == 1


@dataclass(frozen=True)
class RidgeExplanation:
    """Audit tables for one set of frozen Ridge predictions."""

    terms: pd.DataFrame
    cases: pd.DataFrame
    coefficients: pd.DataFrame
    references: pd.DataFrame
    max_reconstruction_error: float


def dropped_references(model: Pipeline) -> dict[str, str]:
    """Return the category removed by ``drop='first'`` for this fit.

    The reference is whatever category the fitted encoder dropped. It is not
    assumed to be Maryland or month ``01``.
    """
    encoder: OneHotEncoder = model.named_steps["preprocess"].named_transformers_["cat"]
    if encoder.drop_idx_ is None:
        raise ExplainError("The fitted encoder did not drop a reference category.")
    references: dict[str, str] = {}
    for feature, categories, drop_index in zip(
        CATEGORICAL_FEATURES,
        encoder.categories_,
        encoder.drop_idx_,
        strict=True,
    ):
        references[str(feature)] = str(categories[int(drop_index)])
    return references


def explain_prediction(
    model: Pipeline,
    case: pd.Series,
    *,
    stored_prediction: float,
) -> tuple[list[dict[str, object]], float]:
    """Explain one scored row with ``model`` and return terms plus the intercept.

    Unknown categories raise. They are not given a zero or borrowed coefficient.
    """
    row = pd.DataFrame([case.to_dict()])
    if not frame_categories_known(model, row):
        raise ExplainError(
            "Unknown category was not assigned a coefficient."
        )
    matrix = design_matrix(row)
    predicted = float(model.predict(matrix)[0])
    if abs(predicted - float(stored_prediction)) > RECONSTRUCTION_TOLERANCE:
        raise ExplainError(
            "Refit Ridge prediction does not match the frozen point forecast."
        )
    transformed = np.asarray(
        model.named_steps["preprocess"].transform(matrix)[0],
        dtype=float,
    )
    names = [
        str(name)
        for name in model.named_steps["preprocess"].get_feature_names_out()
    ]
    coefficients = np.asarray(model.named_steps["model"].coef_, dtype=float).ravel()
    if len(names) != len(coefficients) or len(names) != len(transformed):
        raise ExplainError("Coefficient vector does not match the transformed row.")
    intercept = float(np.asarray(model.named_steps["model"].intercept_).ravel()[0])
    scaler: StandardScaler = model.named_steps["preprocess"].named_transformers_["num"]
    means = {
        name: float(value)
        for name, value in zip(NUMERIC_FEATURES, scaler.mean_, strict=True)
    }
    scales = {
        name: float(value)
        for name, value in zip(NUMERIC_FEATURES, scaler.scale_, strict=True)
    }
    references = dropped_references(model)
    terms: list[dict[str, object]] = []
    for name, transformed_value, coefficient in zip(
        names,
        transformed,
        coefficients,
        strict=True,
    ):
        feature_name, group, category = _parse_transformed_name(name)
        if group == "numeric":
            raw_numeric = float(case[feature_name])
            manual = (raw_numeric - means[feature_name]) / scales[feature_name]
            if abs(manual - float(transformed_value)) > RECONSTRUCTION_TOLERANCE:
                raise ExplainError(
                    f"Standardized {feature_name} does not match the fitted scaler."
                )
        else:
            raw_numeric = np.nan
            active = str(case[feature_name])
            if category == references[feature_name]:
                raise ExplainError(
                    "The dropped reference category was given a coefficient column."
                )
            expected = 1.0 if active == category else 0.0
            if abs(float(transformed_value) - expected) > RECONSTRUCTION_TOLERANCE:
                raise ExplainError(
                    f"One-hot value for {feature_name}={category} does not match the row."
                )
        contribution = float(transformed_value) * float(coefficient)
        terms.append(
            {
                "transformed_feature_name": name,
                "feature_name": feature_name,
                "feature_group": group,
                "category": category,
                "raw_numeric_value": raw_numeric,
                "transformed_value": float(transformed_value),
                "coefficient": float(coefficient),
                "contribution": contribution,
                "scaler_mean": means[feature_name] if group == "numeric" else np.nan,
                "scaler_scale": scales[feature_name] if group == "numeric" else np.nan,
            }
        )
    reconstructed = intercept + float(sum(term["contribution"] for term in terms))
    if abs(reconstructed - predicted) > RECONSTRUCTION_TOLERANCE:
        raise ExplainError("Intercept plus contributions does not rebuild the prediction.")
    return terms, intercept


def explain_ridge_predictions(
    frame: pd.DataFrame,
    predictions: pd.DataFrame,
    *,
    history_origin_start: str = HISTORY_ORIGIN_START,
    states: tuple[str, ...] = USER_FACING_STATES,
    holdout_target_start: str = HOLDOUT_TARGET_START,
) -> RidgeExplanation:
    """Explain frozen Ridge rows by refitting each origin with its recorded penalty.

    ``predictions`` is not modified. The refit uses ``fit_ridge`` on the same
    eligible pre-origin rows as the backtest. A mismatch with the stored point
    forecast raises instead of publishing a different prediction.
    """
    if holdout_target_start > HOLDOUT_TARGET_START:
        raise ExplainError("The final holdout cannot be moved later than 2025-07.")
    _require_prediction_columns(predictions)
    if predictions.empty:
        raise ExplainError("Ridge predictions are empty.")
    if predictions["target_period"].astype(str).ge(holdout_target_start).any():
        raise ExplainError("Holdout target was scored.")
    unexpected_states = set(predictions["state_id"].astype(str)) - set(states)
    if unexpected_states:
        raise ExplainError(f"Unexpected state in Ridge predictions: {sorted(unexpected_states)}.")

    last_origin = pd.Timestamp(predictions["forecast_origin"].max())
    origin_end = f"{last_origin.year:04d}-{last_origin.month:02d}"
    cases, _gaps = build_feature_cases(
        frame,
        origins=month_end_origins(history_origin_start, origin_end),
        states=states,
    )
    if cases.empty:
        raise ExplainError("Feature cases are empty.")
    case_index = {
        (pd.Timestamp(row.forecast_origin), str(row.state_id)): row
        for row in cases.itertuples(index=False)
    }

    models: dict[pd.Timestamp, Pipeline] = {}
    reference_rows: list[dict[str, object]] = []
    coefficient_rows: list[dict[str, object]] = []
    for origin, group in predictions.groupby("forecast_origin", sort=False):
        origin_ts = pd.Timestamp(origin)
        alphas = {float(value) for value in group["alpha"]}
        train_sizes = {int(value) for value in group["n_train_rows"]}
        if len(alphas) != 1 or len(train_sizes) != 1:
            raise ExplainError("One origin produced more than one Ridge fit.")
        alpha = alphas.pop()
        train = training_cases_for_origin(
            cases,
            forecast_origin=origin_ts,
            holdout_target_start=holdout_target_start,
        )
        if len(train) != train_sizes.pop():
            raise ExplainError("Training row count does not match the frozen Ridge fit.")
        if (train["forecast_origin"] >= origin_ts).any():
            raise ExplainError("Explanation training included the scored origin.")
        model = fit_ridge(train, alpha)
        fitted_means = numeric_scaler_means(model)
        for name, fitted_mean in fitted_means.items():
            if abs(fitted_mean - float(train[name].mean())) > 1e-8:
                raise ExplainError(
                    f"Scaler for {name} was not fit on this origin's eligible training rows."
                )
        models[origin_ts] = model
        references = dropped_references(model)
        reference_rows.append(
            {
                "forecast_origin": origin_ts,
                "reference_state": references["state_id"],
                "reference_month": references["target_calendar_month"],
                "alpha": alpha,
                "n_train_rows": int(len(train)),
                "intercept": float(np.asarray(model.named_steps["model"].intercept_).ravel()[0]),
            }
        )
        names = model.named_steps["preprocess"].get_feature_names_out()
        coefficients = np.asarray(model.named_steps["model"].coef_, dtype=float).ravel()
        for name, coefficient in zip(names, coefficients, strict=True):
            feature_name, group_name, category = _parse_transformed_name(str(name))
            coefficient_rows.append(
                {
                    "forecast_origin": origin_ts,
                    "feature_group": group_name,
                    "feature_name": feature_name,
                    "category": category,
                    "coefficient": float(coefficient),
                }
            )

    term_rows: list[dict[str, object]] = []
    case_rows: list[dict[str, object]] = []
    max_error = 0.0
    for prediction in predictions.itertuples(index=False):
        origin_ts = pd.Timestamp(prediction.forecast_origin)
        state_id = str(prediction.state_id)
        case = case_index.get((origin_ts, state_id))
        if case is None:
            raise ExplainError(f"Missing feature row for {state_id} at {origin_ts.date()}.")
        case_series = pd.Series(case._asdict())
        stored = float(prediction.ridge_prediction_cents_per_kwh)
        terms, intercept = explain_prediction(
            models[origin_ts],
            case_series,
            stored_prediction=stored,
        )
        reconstructed = intercept + float(sum(term["contribution"] for term in terms))
        error = abs(reconstructed - stored)
        max_error = max(max_error, error)
        references = dropped_references(models[origin_ts])
        active_state = str(case_series["state_id"])
        active_month = str(case_series["target_calendar_month"])
        case_rows.append(
            {
                "state_id": state_id,
                "forecast_origin": origin_ts,
                "target_period": str(prediction.target_period),
                "ridge_prediction_cents_per_kwh": stored,
                "actual_cents_per_kwh": float(prediction.actual_cents_per_kwh),
                "signed_error": float(prediction.actual_cents_per_kwh) - stored,
                "intercept": intercept,
                "reconstructed_prediction": reconstructed,
                "reconstruction_error": error,
                "reference_state": references["state_id"],
                "reference_month": references["target_calendar_month"],
                "active_state": active_state,
                "state_status": (
                    "reference" if active_state == references["state_id"] else "contrast"
                ),
                "state_contribution": _active_contribution(
                    terms,
                    feature_name="state_id",
                    category=active_state,
                ),
                "active_month": active_month,
                "month_status": (
                    "reference"
                    if active_month == references["target_calendar_month"]
                    else "contrast"
                ),
                "month_contribution": _active_contribution(
                    terms,
                    feature_name="target_calendar_month",
                    category=active_month,
                ),
                "alpha": float(prediction.alpha),
            }
        )
        for term in terms:
            term_rows.append(
                {
                    "state_id": state_id,
                    "forecast_origin": origin_ts,
                    "target_period": str(prediction.target_period),
                    "ridge_prediction_cents_per_kwh": stored,
                    "intercept": intercept,
                    **term,
                }
            )

    terms_frame = pd.DataFrame.from_records(term_rows, columns=list(TERM_COLUMNS))
    cases_frame = pd.DataFrame.from_records(case_rows)
    if cases_frame["target_period"].astype(str).ge(holdout_target_start).any():
        raise ExplainError("Holdout target was scored.")
    if not np.allclose(
        cases_frame["ridge_prediction_cents_per_kwh"].to_numpy(dtype=float),
        predictions["ridge_prediction_cents_per_kwh"].to_numpy(dtype=float),
        atol=RECONSTRUCTION_TOLERANCE,
        rtol=0.0,
    ):
        raise ExplainError("Explanation changed a Ridge point prediction.")
    return RidgeExplanation(
        terms=terms_frame,
        cases=cases_frame,
        coefficients=pd.DataFrame.from_records(coefficient_rows),
        references=pd.DataFrame.from_records(reference_rows),
        max_reconstruction_error=max_error,
    )


def summarize_coefficients(
    explanation: RidgeExplanation,
    *,
    final_origin: pd.Timestamp | None = None,
) -> CoefficientSummary:
    """Summarize coefficients across origins. This does not average the models into one fit."""
    if explanation.coefficients.empty or explanation.references.empty:
        raise ExplainError("Coefficient summary requires at least one origin.")
    final = (
        pd.Timestamp(explanation.references["forecast_origin"].max())
        if final_origin is None
        else pd.Timestamp(final_origin)
    )
    final_rows = explanation.coefficients.loc[
        explanation.coefficients["forecast_origin"] == final
    ]
    if final_rows.empty:
        raise ExplainError("The final origin has no coefficients.")

    def stats(group_name: str) -> tuple[CoefficientStat, ...]:
        subset = explanation.coefficients.loc[
            explanation.coefficients["feature_group"] == group_name
        ]
        built: list[CoefficientStat] = []
        keys = subset.groupby(["feature_name", "category"], dropna=False, sort=True).groups
        for feature_name, category in keys:
            values = subset.loc[
                (subset["feature_name"] == feature_name)
                & _category_equal(subset["category"], category)
            ]
            final_match = final_rows.loc[
                (final_rows["feature_name"] == feature_name)
                & _category_equal(final_rows["category"], category)
            ]
            if len(final_match) != 1:
                raise ExplainError(
                    f"Expected one final-origin coefficient for {feature_name} {category}."
                )
            array = values["coefficient"].to_numpy(dtype=float)
            category_text = None if pd.isna(category) else str(category)
            built.append(
                CoefficientStat(
                    feature_group=group_name,
                    feature_name=str(feature_name),
                    category=category_text,
                    n_origins=int(len(array)),
                    median=float(np.median(array)),
                    minimum=float(array.min()),
                    maximum=float(array.max()),
                    n_positive=int((array > 0).sum()),
                    n_negative=int((array < 0).sum()),
                    n_zero=int((array == 0).sum()),
                    final_coefficient=float(final_match["coefficient"].iloc[0]),
                )
            )
        return tuple(built)

    reference_states = tuple(
        sorted(set(explanation.references["reference_state"].astype(str)))
    )
    reference_months = tuple(
        sorted(set(explanation.references["reference_month"].astype(str)))
    )
    return CoefficientSummary(
        n_origins=int(explanation.references["forecast_origin"].nunique()),
        reference_states=reference_states,
        reference_months=reference_months,
        numeric=stats("numeric"),
        state=stats("state"),
        month=stats("month"),
    )


def _category_equal(series: pd.Series, category: object) -> pd.Series:
    if pd.isna(category):
        return series.isna()
    return series.astype(str) == str(category)


def _active_contribution(
    terms: list[dict[str, object]],
    *,
    feature_name: str,
    category: str,
) -> float:
    """Contribution of the active category, or 0 when that category is the reference."""
    matches = [
        float(term["contribution"])
        for term in terms
        if term["feature_name"] == feature_name and term["category"] == category
    ]
    if not matches:
        return 0.0
    if len(matches) != 1:
        raise ExplainError(f"More than one coefficient for {feature_name}={category}.")
    return matches[0]


def _parse_transformed_name(name: str) -> tuple[str, str, str | None]:
    if name.startswith("num__"):
        feature_name = name.removeprefix("num__")
        if feature_name not in NUMERIC_FEATURES:
            raise ExplainError(f"Unexpected numeric feature in the pipeline: {name}.")
        return feature_name, "numeric", None
    if name.startswith("cat__"):
        body = name.removeprefix("cat__")
        for feature_name in CATEGORICAL_FEATURES:
            prefix = feature_name + "_"
            if body.startswith(prefix):
                return feature_name, _GROUP_FOR_CATEGORY[feature_name], body[len(prefix) :]
        raise ExplainError(f"Unexpected categorical feature in the pipeline: {name}.")
    raise ExplainError(f"Unexpected transformed feature name: {name}.")


def _require_prediction_columns(predictions: pd.DataFrame) -> None:
    missing = [column for column in _PREDICTION_COLUMNS if column not in predictions.columns]
    if missing:
        raise ExplainError(f"Ridge predictions are missing columns: {missing}.")


def _print_stat(stat: CoefficientStat) -> None:
    category = "" if stat.category is None else f"[{stat.category}]"
    print(
        f"  {stat.feature_name}{category}: "
        f"median={stat.median:.6f} min={stat.minimum:.6f} max={stat.maximum:.6f} "
        f"positive={stat.n_positive}/{stat.n_origins} "
        f"negative={stat.n_negative}/{stat.n_origins} "
        f"final={stat.final_coefficient:.6f}"
    )


def _print_summary(summary: CoefficientSummary) -> None:
    print(f"n_coefficient_origins: {summary.n_origins}")
    print(f"references_constant: {str(summary.references_constant).lower()}")
    print(f"reference_states: {', '.join(summary.reference_states)}")
    print(f"reference_months: {', '.join(summary.reference_months)}")
    print("numeric_coefficients:")
    for stat in summary.numeric:
        _print_stat(stat)
    print("state_coefficients_versus_reference:")
    for stat in summary.state:
        _print_stat(stat)
    print("month_coefficients_versus_reference:")
    for stat in summary.month:
        _print_stat(stat)
    print("sign_changes:")
    changes = [
        stat
        for stat in (*summary.numeric, *summary.state, *summary.month)
        if stat.changes_sign
    ]
    if not changes:
        print("  none")
        return
    for stat in changes:
        category = "" if stat.category is None else f"[{stat.category}]"
        print(
            f"  {stat.feature_group} {stat.feature_name}{category}: "
            f"positive={stat.n_positive}/{stat.n_origins} "
            f"negative={stat.n_negative}/{stat.n_origins} "
            f"min={stat.minimum:.6f} max={stat.maximum:.6f}"
        )


def _print_examples(explanation: RidgeExplanation, origin: pd.Timestamp) -> None:
    selected = explanation.cases.loc[
        explanation.cases["forecast_origin"] == origin
    ].sort_values("state_id")
    if selected.empty:
        raise ExplainError(f"No explanations at {origin.date()}.")
    print(f"examples_origin: {origin.date()}")
    for case in selected.itertuples(index=False):
        terms = explanation.terms.loc[
            (explanation.terms["forecast_origin"] == origin)
            & (explanation.terms["state_id"] == case.state_id)
        ]
        numeric = terms.loc[terms["feature_group"] == "numeric"]
        print(f"state: {case.state_id}")
        print(f"  target_period: {case.target_period}")
        print(f"  prediction: {case.ridge_prediction_cents_per_kwh:.4f}")
        print(f"  actual: {case.actual_cents_per_kwh:.4f}")
        print(f"  signed_error: {case.signed_error:.4f}")
        print(f"  intercept: {case.intercept:.6f}")
        print(
            f"  state_term: {case.state_status} active={case.active_state} "
            f"reference={case.reference_state} contribution={case.state_contribution:.6f}"
        )
        print(
            f"  month_term: {case.month_status} active={case.active_month} "
            f"reference={case.reference_month} contribution={case.month_contribution:.6f}"
        )
        print("  numeric_contributions:")
        for term in numeric.itertuples(index=False):
            print(
                f"    {term.feature_name}: raw={term.raw_numeric_value:.6f} "
                f"standardized={term.transformed_value:.6f} "
                f"coefficient={term.coefficient:.6f} "
                f"contribution={term.contribution:.6f}"
            )
        print(f"  reconstructed: {case.reconstructed_prediction:.6f}")
        print(f"  reconstruction_abs_error: {case.reconstruction_error:.3e}")


def main() -> int:
    """Explain the frozen development Ridge forecasts. Stop if the point MAE changed."""
    parquet_path = latest_eia_parquet()
    frame = load_price_panel(parquet_path)
    ridge = run_ridge_backtest(frame)
    rounded_mae = round(ridge.mae_ridge, 4)
    if (
        ridge.n_forecasts != FROZEN_RIDGE_CASE_COUNT
        or rounded_mae != FROZEN_RIDGE_MAE_ROUNDED
    ):
        print(
            "STOP: Ridge point predictions differ from the frozen development result. "
            f"n={ridge.n_forecasts} mae={ridge.mae_ridge:.10f}"
        )
        return 2
    before = ridge.predictions.copy()
    explanation = explain_ridge_predictions(frame, ridge.predictions)
    if not ridge.predictions.equals(before):
        print("STOP: building explanations mutated the Ridge prediction table.")
        return 2
    if explanation.cases["target_period"].astype(str).max() >= HOLDOUT_TARGET_START:
        print("STOP: a holdout target month was scored.")
        return 2
    summary = summarize_coefficients(explanation)
    final_origin = pd.Timestamp("2024-06-30")
    print(f"window: development")
    print(f"parquet: {parquet_path}")
    print(f"ridge_mae_cents_per_kwh: {ridge.mae_ridge:.4f}")
    print(f"n_point_forecasts: {ridge.n_forecasts}")
    print(f"n_explained: {len(explanation.cases)}")
    print(f"max_reconstruction_abs_error: {explanation.max_reconstruction_error:.3e}")
    print(f"max_target_period: {explanation.cases['target_period'].max()}")
    _print_summary(summary)
    _print_examples(explanation, final_origin)
    print(f"run_at: {datetime.now().isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

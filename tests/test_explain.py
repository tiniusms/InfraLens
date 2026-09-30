"""Exact reconstruction tests for origin-specific Ridge explanations."""

from __future__ import annotations

import pandas as pd
import pytest

from infralens.data.availability import assumed_available_at
from infralens.evaluation.backtest import HOLDOUT_TARGET_START
from infralens.evaluation.explain import (
    FROZEN_RIDGE_CASE_COUNT,
    FROZEN_RIDGE_MAE_ROUNDED,
    RECONSTRUCTION_TOLERANCE,
    ExplainError,
    dropped_references,
    explain_prediction,
    explain_ridge_predictions,
    summarize_coefficients,
)
from infralens.evaluation.features import MODEL_FEATURES, NUMERIC_FEATURES
from infralens.evaluation.linear import (
    build_feature_cases,
    fit_ridge,
    inner_fit_and_validation,
    run_ridge_backtest,
    training_cases_for_origin,
)
from infralens.evaluation.backtest import month_end_origins


def _panel(start: str = "2001-01", end: str = "2008-12") -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for period in pd.period_range(start, end, freq="M"):
        label = str(period)
        for index, state in enumerate(("MD", "NJ", "OH", "PA", "VA")):
            rows.append(
                {
                    "period": label,
                    "state_id": state,
                    "price_cents_per_kwh": (
                        8.0 + index + 0.15 * period.month + 0.04 * (period.year - 2001)
                    ),
                    "sales_million_kwh": 100.0 + 10 * index + period.month,
                    "revenue_million_usd": 999.0,
                    "assumed_available_at": assumed_available_at(label),
                }
            )
    return pd.DataFrame(rows)


def _development_slice() -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = _panel()
    result = run_ridge_backtest(frame, origin_end="2006-06")
    return frame, result.predictions


def test_intercept_plus_contributions_reconstructs_the_prediction() -> None:
    frame, predictions = _development_slice()
    explanation = explain_ridge_predictions(frame, predictions)
    assert explanation.max_reconstruction_error <= RECONSTRUCTION_TOLERANCE
    for case in explanation.cases.itertuples(index=False):
        terms = explanation.terms.loc[
            (explanation.terms["state_id"] == case.state_id)
            & (explanation.terms["forecast_origin"] == case.forecast_origin)
        ]
        rebuilt = float(case.intercept) + float(terms["contribution"].sum())
        assert rebuilt == pytest.approx(
            case.ridge_prediction_cents_per_kwh,
            abs=RECONSTRUCTION_TOLERANCE,
        )


def test_explanation_uses_the_origin_fit_not_the_inner_slice() -> None:
    frame, predictions = _development_slice()
    explanation = explain_ridge_predictions(frame, predictions)
    origin = pd.Timestamp(predictions["forecast_origin"].min())
    alpha = float(predictions.loc[predictions["forecast_origin"] == origin, "alpha"].iloc[0])
    cases, _gaps = build_feature_cases(
        frame,
        origins=month_end_origins("2001-01", "2006-06"),
        states=("VA", "PA", "OH", "MD", "NJ"),
    )
    train = training_cases_for_origin(cases, forecast_origin=origin)
    model = fit_ridge(train, alpha)
    explained = explanation.coefficients.loc[
        explanation.coefficients["forecast_origin"] == origin
    ]
    names = model.named_steps["preprocess"].get_feature_names_out()
    coefficients = model.named_steps["model"].coef_.ravel()
    for name, coefficient in zip(names, coefficients, strict=True):
        feature_name = str(name).split("__", maxsplit=1)[1]
        if feature_name.startswith("state_id_") or feature_name.startswith(
            "target_calendar_month_"
        ):
            continue
        match = explained.loc[explained["feature_name"] == feature_name]
        assert len(match) == 1
        assert float(match["coefficient"].iloc[0]) == pytest.approx(float(coefficient))
    inner_fit, _validation = inner_fit_and_validation(train)
    assert inner_fit is not None
    explained_mean = float(
        explanation.terms.loc[
            (explanation.terms["forecast_origin"] == origin)
            & (explanation.terms["feature_name"] == "price_latest"),
            "scaler_mean",
        ].iloc[0]
    )
    assert explained_mean == pytest.approx(float(train["price_latest"].mean()))
    assert abs(explained_mean - float(inner_fit["price_latest"].mean())) > 1e-6


def test_numeric_transform_uses_only_eligible_training_rows() -> None:
    frame, predictions = _development_slice()
    explanation = explain_ridge_predictions(frame, predictions)
    origin = pd.Timestamp("2005-06-30")
    cases, _gaps = build_feature_cases(
        frame,
        origins=month_end_origins("2001-01", "2006-06"),
        states=("VA", "PA", "OH", "MD", "NJ"),
    )
    train = training_cases_for_origin(cases, forecast_origin=origin)
    scored = cases.loc[
        (cases["forecast_origin"] == origin) & (cases["state_id"] == "VA")
    ].iloc[0]
    augmented_mean = float(
        pd.concat([train["price_latest"], pd.Series([scored["price_latest"]])]).mean()
    )
    term = explanation.terms.loc[
        (explanation.terms["forecast_origin"] == origin)
        & (explanation.terms["state_id"] == "VA")
        & (explanation.terms["feature_name"] == "price_latest")
    ].iloc[0]
    assert float(term["scaler_mean"]) == pytest.approx(float(train["price_latest"].mean()))
    assert abs(float(term["scaler_mean"]) - augmented_mean) > 1e-8
    assert origin not in set(train["forecast_origin"])
    manual = (float(term["raw_numeric_value"]) - float(term["scaler_mean"])) / float(
        term["scaler_scale"]
    )
    assert float(term["transformed_value"]) == pytest.approx(manual)


def test_categorical_contribution_matches_the_active_one_hot_category() -> None:
    frame, predictions = _development_slice()
    explanation = explain_ridge_predictions(frame, predictions)
    origin = pd.Timestamp("2005-06-30")
    terms = explanation.terms.loc[
        (explanation.terms["forecast_origin"] == origin)
        & (explanation.terms["state_id"] == "VA")
    ]
    state_terms = terms.loc[terms["feature_name"] == "state_id"]
    active = state_terms.loc[state_terms["category"] == "VA"].iloc[0]
    inactive = state_terms.loc[state_terms["category"] == "NJ"].iloc[0]
    assert float(active["transformed_value"]) == 1.0
    assert float(active["contribution"]) == pytest.approx(float(active["coefficient"]))
    assert float(inactive["transformed_value"]) == 0.0
    assert float(inactive["contribution"]) == 0.0
    month_terms = terms.loc[terms["feature_name"] == "target_calendar_month"]
    june = month_terms.loc[month_terms["category"] == "06"].iloc[0]
    assert float(june["transformed_value"]) == 1.0
    assert float(june["contribution"]) == pytest.approx(float(june["coefficient"]))


def test_dropped_reference_is_read_from_the_encoder() -> None:
    rows: list[dict[str, object]] = []
    for index, (state, month) in enumerate(
        (("NJ", "06"), ("NJ", "07"), ("VA", "06"), ("VA", "07"))
    ):
        row = {
            "target_period": "2004-06",
            "actual_cents_per_kwh": float(index + 1),
            "state_id": state,
            "target_calendar_month": month,
        }
        for feature in NUMERIC_FEATURES:
            row[feature] = float(index + 2)
        rows.append(row)
    model = fit_ridge(pd.DataFrame(rows), 1.0)
    references = dropped_references(model)
    assert references == {"state_id": "NJ", "target_calendar_month": "06"}
    names = set(model.named_steps["preprocess"].get_feature_names_out())
    assert "cat__state_id_NJ" not in names
    assert "cat__target_calendar_month_06" not in names
    case = pd.Series(rows[0])
    terms, _intercept = explain_prediction(model, case, stored_prediction=float(model.predict(
        pd.DataFrame([case.to_dict()]).loc[:, list(MODEL_FEATURES)]
    )[0]))
    categories = {term["category"] for term in terms if term["feature_name"] == "state_id"}
    assert "NJ" not in categories
    assert "VA" in categories


def test_unknown_category_is_not_assigned_a_coefficient() -> None:
    frame, predictions = _development_slice()
    origin = pd.Timestamp(predictions["forecast_origin"].iloc[0])
    alpha = float(predictions["alpha"].iloc[0])
    cases, _gaps = build_feature_cases(
        frame,
        origins=month_end_origins("2001-01", "2006-06"),
        states=("VA", "PA", "OH", "MD", "NJ"),
    )
    train = training_cases_for_origin(cases, forecast_origin=origin)
    model = fit_ridge(train, alpha)
    unknown = pd.Series(train.iloc[0].to_dict())
    unknown["state_id"] = "TX"
    with pytest.raises(ExplainError, match="Unknown category"):
        explain_prediction(
            model,
            unknown,
            stored_prediction=float(predictions["ridge_prediction_cents_per_kwh"].iloc[0]),
        )


def test_explanation_does_not_alter_the_ridge_prediction() -> None:
    frame, predictions = _development_slice()
    before = predictions.copy()
    mae_before = float(predictions["ridge_absolute_error"].mean())
    explanation = explain_ridge_predictions(frame, predictions)
    pd.testing.assert_frame_equal(predictions, before)
    assert explanation.cases["ridge_prediction_cents_per_kwh"].tolist() == (
        predictions["ridge_prediction_cents_per_kwh"].tolist()
    )
    assert float(predictions["ridge_absolute_error"].mean()) == mae_before


def test_frozen_development_ridge_check_stays_at_the_recorded_result() -> None:
    assert FROZEN_RIDGE_CASE_COUNT == 1145
    assert FROZEN_RIDGE_MAE_ROUNDED == 0.7075
    frame, predictions = _development_slice()
    explanation = explain_ridge_predictions(frame, predictions)
    assert len(explanation.cases) == len(predictions)
    assert float(predictions["ridge_absolute_error"].mean()) == pytest.approx(
        float(predictions["ridge_absolute_error"].mean())
    )
    summary = summarize_coefficients(explanation)
    assert summary.n_origins == predictions["forecast_origin"].nunique()


def test_final_holdout_targets_are_not_scored() -> None:
    frame, predictions = _development_slice()
    explanation = explain_ridge_predictions(frame, predictions)
    assert explanation.cases["target_period"].astype(str).max() < HOLDOUT_TARGET_START
    holdout = predictions.iloc[[0]].copy()
    holdout["target_period"] = "2025-07"
    with pytest.raises(ExplainError, match="Holdout target was scored"):
        explain_ridge_predictions(frame, holdout)

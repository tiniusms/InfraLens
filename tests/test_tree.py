"""Leakage and alignment tests for the histogram gradient-boosting candidate."""

from __future__ import annotations

import pandas as pd
import pytest

from infralens.data.availability import assumed_available_at
from infralens.evaluation.backtest import HOLDOUT_TARGET_START
from infralens.evaluation.baseline import target_period_for_origin
from infralens.evaluation.features import MODEL_FEATURES, build_origin_features
from infralens.evaluation.linear import (
    LinearModelError,
    build_feature_cases,
    inner_fit_and_validation,
    run_ridge_backtest,
    training_cases_for_origin,
)
from infralens.evaluation.tree import (
    MIN_SAMPLES_LEAF,
    TREE_GRID,
    TreeModelError,
    category_levels,
    compare_with_ridge,
    fit_category_encoder,
    model_matrix,
    run_tree_backtest,
    select_tree_params,
)


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


def _constant_training_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for origin in pd.date_range("2002-04-30", "2004-03-31", freq="ME"):
        target_period = target_period_for_origin(origin)
        rows.append(
            {
                "forecast_origin": pd.Timestamp(origin),
                "state_id": "VA",
                "target_period": target_period,
                "target_calendar_month": target_period[5:7],
                "actual_cents_per_kwh": 5.0,
                "label_assumed_available_at": assumed_available_at(target_period),
                "price_latest": 5.0,
                "price_same_month": 5.0,
                "price_yoy_change": 0.0,
                "price_trail12_mean": 5.0,
                "sales_latest": 100.0,
                "sales_yoy_change": 0.0,
            }
        )
    return pd.DataFrame(rows)


def test_tree_uses_the_ridge_feature_list_without_revenue() -> None:
    assert "revenue_million_usd" not in MODEL_FEATURES
    assert MODEL_FEATURES == (
        "price_latest",
        "price_same_month",
        "price_yoy_change",
        "price_trail12_mean",
        "sales_latest",
        "sales_yoy_change",
        "state_id",
        "target_calendar_month",
    )


def test_ordinal_encoder_learns_only_the_fit_slice_and_rejects_unknown_levels() -> None:
    train = _constant_training_frame()
    split = inner_fit_and_validation(train, inner_validation_origins=12, min_fit_origins=12)
    assert split is not None
    fit, validation = split
    assert fit["forecast_origin"].max() < validation["forecast_origin"].min()
    encoder = fit_category_encoder(fit)
    levels = category_levels(encoder)
    assert set(levels["target_calendar_month"]) == set(fit["target_calendar_month"].astype(str))
    assert "state_id" in levels
    matrix = model_matrix(fit, encoder)
    assert matrix.shape == (len(fit), len(MODEL_FEATURES))
    assert int(matrix[:, -2:].min()) >= 0

    withheld = fit.copy()
    withheld["target_calendar_month"] = "01"
    narrow = fit_category_encoder(withheld)
    assert category_levels(narrow)["target_calendar_month"] == ("01",)
    unseen = validation.copy()
    unseen["target_calendar_month"] = "07"
    with pytest.raises(TreeModelError, match="not present in the training fold"):
        model_matrix(unseen, narrow)

    blocked = train.copy()
    early = blocked["forecast_origin"] < validation["forecast_origin"].min()
    blocked.loc[early, "target_calendar_month"] = "01"
    assert select_tree_params(blocked, inner_validation_origins=12, min_fit_origins=12) is None


def test_hyperparameter_selection_uses_the_earlier_slice_and_breaks_ties_simply() -> None:
    train = _constant_training_frame()
    selection = select_tree_params(train, inner_validation_origins=12, min_fit_origins=12)
    assert selection is not None
    assert selection.params.as_key() in TREE_GRID
    assert selection.params.as_key() == (2, 0.05)
    assert selection.n_fit_rows == 12
    assert selection.n_validation_rows == 12
    fit, _validation = inner_fit_and_validation(
        train, inner_validation_origins=12, min_fit_origins=12
    )
    assert fit is not None
    assert selection.fit_category_levels["target_calendar_month"] == tuple(
        sorted(fit["target_calendar_month"].astype(str).unique())
    )
    assert MIN_SAMPLES_LEAF == 20


def test_select_tree_params_rejects_final_holdout_targets() -> None:
    train = _constant_training_frame()
    train.loc[train.index[-1], "target_period"] = "2025-07"
    with pytest.raises(LinearModelError, match="Holdout target"):
        select_tree_params(train, inner_validation_origins=12, min_fit_origins=12)
    with pytest.raises(TreeModelError, match="later than 2025-07"):
        run_tree_backtest(_panel(), holdout_target_start="2025-08")


def test_tree_cases_match_ridge_and_exclude_the_scored_origin() -> None:
    frame = _panel()
    kwargs = {
        "origin_start": "2002-01",
        "origin_end": "2005-06",
        "states": ("MD", "NJ", "OH", "PA", "VA"),
        "window": "unit-test",
    }
    tree = run_tree_backtest(frame, **kwargs)
    ridge = run_ridge_backtest(frame, **kwargs)
    assert tree.n_attempted == ridge.n_attempted == 210
    assert tree.n_forecasts == ridge.n_forecasts == 5
    assert tree.n_skipped_feature_gap == ridge.n_skipped_feature_gap == 15
    assert tree.n_skipped_insufficient_train == ridge.n_skipped_insufficient_train == 190
    assert tree.n_skipped_missing_actual == ridge.n_skipped_missing_actual == 0
    assert tree.n_attempted == (
        tree.n_forecasts
        + tree.n_skipped_feature_gap
        + tree.n_skipped_insufficient_train
        + tree.n_skipped_missing_actual
    )
    assert (tree.predictions["target_period"] >= HOLDOUT_TARGET_START).sum() == 0
    assert tree.max_training_target_period < HOLDOUT_TARGET_START
    assert tree.predictions["target_period"].eq("2006-06").all()
    assert (
        tree.predictions["target_period"]
        == tree.predictions["forecast_origin"].map(target_period_for_origin)
    ).all()
    assert (
        tree.predictions["label_assumed_available_at"] > tree.predictions["forecast_origin"]
    ).all()
    for column in (
        "latest_assumed_available_at",
        "same_month_assumed_available_at",
        "yoy_assumed_available_at",
        "trail_max_assumed_available_at",
    ):
        assert (tree.predictions[column] <= tree.predictions["forecast_origin"]).all()

    common = compare_with_ridge(tree, ridge.predictions)
    assert common.n_common == common.n_tree == common.n_ridge == 5
    assert common.mae_baseline == pytest.approx(tree.mae_baseline_same_cases)

    origin = pd.Timestamp(tree.predictions["forecast_origin"].iloc[0])
    cases, _gaps = build_feature_cases(
        frame,
        origins=pd.date_range("2001-01-31", "2005-06-30", freq="ME").tolist(),
        states=("MD", "NJ", "OH", "PA", "VA"),
    )
    train = training_cases_for_origin(cases, forecast_origin=origin)
    assert origin not in set(pd.to_datetime(train["forecast_origin"]))
    assert int(tree.predictions["n_train_rows"].iloc[0]) == len(train)
    assert str(train["target_period"].max()) < str(tree.predictions["target_period"].iloc[0])
    features = build_origin_features(frame, forecast_origin=origin, state_id="VA")
    assert all(stamp <= origin for stamp in features.source_availability())
    assert features.target_period == "2006-06"


def test_future_rows_and_scored_target_do_not_change_the_tree_prediction() -> None:
    frame = _panel(end="2007-06")
    kwargs = {
        "origin_start": "2005-06",
        "origin_end": "2005-06",
        "states": ("MD", "NJ", "OH", "PA", "VA"),
        "window": "unit-test",
    }
    original = run_tree_backtest(frame, **kwargs)
    future = _panel(end="2008-12")
    future.loc[future["period"] == "2008-06", "price_cents_per_kwh"] = 999.0
    with_future = run_tree_backtest(future, **kwargs)
    pd.testing.assert_series_equal(
        original.predictions["tree_prediction_cents_per_kwh"].reset_index(drop=True),
        with_future.predictions["tree_prediction_cents_per_kwh"].reset_index(drop=True),
    )

    leaked_target = frame.copy()
    leaked_target.loc[
        (leaked_target["period"] == "2006-06") & (leaked_target["state_id"] == "VA"),
        "price_cents_per_kwh",
    ] = 999.0
    poisoned = run_tree_backtest(leaked_target, **kwargs)
    original_va = original.predictions.loc[original.predictions["state_id"] == "VA"].iloc[0]
    poisoned_va = poisoned.predictions.loc[poisoned.predictions["state_id"] == "VA"].iloc[0]
    assert poisoned_va["actual_cents_per_kwh"] == 999.0
    assert poisoned_va["tree_prediction_cents_per_kwh"] == pytest.approx(
        original_va["tree_prediction_cents_per_kwh"]
    )
    assert poisoned_va["target_period"] == "2006-06"


def test_missing_history_is_counted_rather_than_filled() -> None:
    frame = _panel()
    frame = frame.loc[~((frame["period"] == "2005-01") & (frame["state_id"] == "VA"))].copy()
    frame.loc[frame["period"] == "2005-04", "price_cents_per_kwh"] = 12345.0
    gapped = run_tree_backtest(
        frame,
        origin_start="2002-01",
        origin_end="2005-06",
        states=("MD", "NJ", "OH", "PA", "VA"),
        window="unit-test-gap",
    )
    assert gapped.n_skipped_feature_gap == 17
    assert gapped.n_skipped_missing_actual == 1
    assert gapped.n_skipped_insufficient_train == 188
    assert gapped.n_forecasts == 4
    assert set(gapped.predictions["state_id"]) == {"MD", "NJ", "OH", "PA"}
    assert (gapped.predictions["tree_prediction_cents_per_kwh"] == 12345.0).sum() == 0


def test_extending_past_an_earlier_holdout_cutoff_does_not_change_tree_scores() -> None:
    frame = _panel(end="2008-12")
    kwargs = {
        "origin_start": "2005-06",
        "states": ("MD", "NJ", "OH", "PA", "VA"),
        "holdout_target_start": "2006-07",
        "window": "unit-test-holdout",
    }
    short = run_tree_backtest(frame, origin_end="2005-06", **kwargs)
    extended = run_tree_backtest(frame, origin_end="2008-06", **kwargs)
    assert short.n_forecasts == extended.n_forecasts == 5
    assert (extended.predictions["target_period"] >= "2006-07").sum() == 0
    assert extended.max_training_target_period < "2006-07"
    left = short.predictions.sort_values("state_id").reset_index(drop=True)
    right = extended.predictions.sort_values("state_id").reset_index(drop=True)
    pd.testing.assert_series_equal(
        left["tree_prediction_cents_per_kwh"],
        right["tree_prediction_cents_per_kwh"],
    )

"""Leakage and alignment tests for the Ridge EIA baseline."""

from __future__ import annotations

import pandas as pd
import pytest

from infralens.data.availability import assumed_available_at
from infralens.evaluation.backtest import HOLDOUT_TARGET_START, run_expanding_backtest
from infralens.evaluation.baseline import (
    availability_adjusted_seasonal_naive,
    target_period_for_origin,
)
from infralens.evaluation.features import (
    MODEL_FEATURES,
    FeatureGapError,
    build_origin_features,
    trailing_periods,
)
from infralens.evaluation.linear import (
    ALPHA_GRID,
    LinearModelError,
    fit_ridge,
    inner_fit_and_validation,
    numeric_scaler_means,
    run_ridge_backtest,
    select_alpha,
    training_cases_for_origin,
)


def _panel(start: str = "2001-01", end: str = "2008-12") -> pd.DataFrame:
    """Complete monthly commercial panel with an m+3 availability stamp."""
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
    """24 consecutive origins, one state, constant actuals. All calendar months appear."""
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


def test_model_features_exclude_revenue_and_use_the_baseline_analog() -> None:
    assert "revenue_million_usd" not in MODEL_FEATURES
    assert "price_same_month" in MODEL_FEATURES
    assert MODEL_FEATURES.index("state_id") >= 0
    assert "target_calendar_month" in MODEL_FEATURES


def test_trailing_window_is_twelve_consecutive_months() -> None:
    assert trailing_periods("2004-03") == (
        "2003-04",
        "2003-05",
        "2003-06",
        "2003-07",
        "2003-08",
        "2003-09",
        "2003-10",
        "2003-11",
        "2003-12",
        "2004-01",
        "2004-02",
        "2004-03",
    )


def test_features_reject_observations_unavailable_at_origin() -> None:
    frame = _panel(start="2001-01", end="2025-06")
    origin = pd.Timestamp("2024-06-30")
    frame.loc[frame["period"] == "2024-06", "price_cents_per_kwh"] = 99.0
    frame.loc[frame["period"] == "2024-04", "price_cents_per_kwh"] = 88.0
    features = build_origin_features(frame, forecast_origin=origin, state_id="VA")
    assert features.target_period == "2025-06"
    assert features.latest_period == "2024-03"
    assert features.same_month_period == "2023-06"
    assert features.yoy_period == "2023-03"
    assert "2024-06" not in features.source_periods()
    assert "2024-04" not in features.source_periods()
    assert features.price_same_month != 99.0
    assert features.price_latest != 88.0
    assert all(stamp <= origin for stamp in features.source_availability())
    analog = availability_adjusted_seasonal_naive(
        frame, forecast_origin=origin, state_id="VA"
    )
    assert features.price_same_month == analog["prediction_cents_per_kwh"]
    assert features.same_month_period == analog["source_period"]


def test_missing_history_is_not_filled_from_a_later_month() -> None:
    frame = _panel(start="2001-01", end="2006-06")
    origin = pd.Timestamp("2004-06-30")
    # Hole inside the 12 months that end at the latest available month (2004-03).
    frame = frame.loc[
        ~((frame["period"] == "2003-06") & (frame["state_id"] == "VA"))
    ].copy()
    frame.loc[frame["period"] == "2004-06", "price_cents_per_kwh"] = 77.0
    with pytest.raises(FeatureGapError, match="2003-06"):
        build_origin_features(frame, forecast_origin=origin, state_id="VA")

    null_latest = _panel(start="2001-01", end="2006-06")
    null_latest.loc[
        (null_latest["period"] == "2004-03") & (null_latest["state_id"] == "VA"),
        "price_cents_per_kwh",
    ] = pd.NA
    with pytest.raises(FeatureGapError, match="2004-03"):
        build_origin_features(null_latest, forecast_origin=origin, state_id="VA")


def test_holdout_targets_never_enter_training_rows() -> None:
    cases = pd.DataFrame(
        [
            {
                "forecast_origin": pd.Timestamp("2024-06-30"),
                "state_id": "VA",
                "target_period": "2025-06",
                "label_assumed_available_at": pd.Timestamp("2025-09-01"),
                "actual_cents_per_kwh": 10.0,
            },
            {
                "forecast_origin": pd.Timestamp("2024-07-31"),
                "state_id": "VA",
                "target_period": "2025-07",
                "label_assumed_available_at": pd.Timestamp("2025-10-01"),
                "actual_cents_per_kwh": 99.0,
            },
            {
                "forecast_origin": pd.Timestamp("2023-01-31"),
                "state_id": "VA",
                "target_period": "2025-07",
                "label_assumed_available_at": pd.Timestamp("2025-10-01"),
                "actual_cents_per_kwh": 99.0,
            },
        ]
    )
    selected = training_cases_for_origin(
        cases,
        forecast_origin=pd.Timestamp("2026-06-30"),
    )
    assert set(selected["target_period"]) == {"2025-06"}
    assert (selected["target_period"] >= HOLDOUT_TARGET_START).sum() == 0
    assert (selected["label_assumed_available_at"] <= pd.Timestamp("2026-06-30")).all()

    too_early = training_cases_for_origin(
        cases,
        forecast_origin=pd.Timestamp("2025-08-31"),
    )
    assert too_early.empty

    with pytest.raises(LinearModelError, match="later than 2025-07"):
        run_ridge_backtest(_panel(), holdout_target_start="2025-08")


def test_scaler_and_alpha_selection_use_only_the_training_slice() -> None:
    train = _constant_training_frame()
    train["price_latest"] = 1.0
    train.loc[train["forecast_origin"] >= pd.Timestamp("2003-04-30"), "price_latest"] = 1000.0
    split = inner_fit_and_validation(train, inner_validation_origins=12, min_fit_origins=12)
    assert split is not None
    fit, validation = split
    assert fit["forecast_origin"].max() < validation["forecast_origin"].min()
    pipeline = fit_ridge(fit, alpha=1.0)
    fitted_mean = numeric_scaler_means(pipeline)["price_latest"]
    assert fitted_mean == pytest.approx(float(fit["price_latest"].mean()))
    assert fitted_mean == pytest.approx(1.0)
    leaky = fit_ridge(pd.concat([fit, validation], ignore_index=True), alpha=1.0)
    assert numeric_scaler_means(leaky)["price_latest"] == pytest.approx(
        float(pd.concat([fit, validation])["price_latest"].mean())
    )
    assert numeric_scaler_means(leaky)["price_latest"] != pytest.approx(fitted_mean)

    selection = select_alpha(train, inner_validation_origins=12, min_fit_origins=12)
    assert selection is not None
    assert selection.fit_price_latest_mean == pytest.approx(1.0)
    assert selection.alpha in ALPHA_GRID

    tied = _constant_training_frame()
    tied_selection = select_alpha(tied, inner_validation_origins=12, min_fit_origins=12)
    assert tied_selection is not None
    assert tied_selection.alpha == max(ALPHA_GRID)


def test_select_alpha_rejects_final_holdout_targets() -> None:
    train = _constant_training_frame()
    train.loc[train.index[-1], "target_period"] = "2025-07"
    with pytest.raises(LinearModelError, match="Holdout target"):
        select_alpha(train, inner_validation_origins=12, min_fit_origins=12)


def test_ridge_backtest_matches_baseline_cases_and_twelve_month_target() -> None:
    frame = _panel()
    ridge = run_ridge_backtest(
        frame,
        origin_start="2002-01",
        origin_end="2005-06",
        states=("MD", "NJ", "OH", "PA", "VA"),
        window="unit-test",
    )
    baseline = run_expanding_backtest(
        frame,
        origin_start="2002-01",
        origin_end="2005-06",
        states=("MD", "NJ", "OH", "PA", "VA"),
        window="unit-test",
    )
    assert ridge.n_attempted == baseline.n_attempted == 210
    assert ridge.n_forecasts == 5
    assert ridge.n_skipped_feature_gap == 15
    assert ridge.n_skipped_insufficient_train == 190
    assert ridge.n_skipped_missing_actual == 0
    assert ridge.n_attempted == (
        ridge.n_forecasts
        + ridge.n_skipped_feature_gap
        + ridge.n_skipped_insufficient_train
        + ridge.n_skipped_missing_actual
    )
    assert (ridge.predictions["target_period"] >= HOLDOUT_TARGET_START).sum() == 0
    assert ridge.max_training_target_period < HOLDOUT_TARGET_START
    assert ridge.predictions["target_period"].eq("2006-06").all()
    assert (
        ridge.predictions["target_period"]
        == ridge.predictions["forecast_origin"].map(target_period_for_origin)
    ).all()
    assert (
        ridge.predictions["label_assumed_available_at"] > ridge.predictions["forecast_origin"]
    ).all()
    for column in (
        "latest_assumed_available_at",
        "same_month_assumed_available_at",
        "yoy_assumed_available_at",
        "trail_max_assumed_available_at",
    ):
        assert (ridge.predictions[column] <= ridge.predictions["forecast_origin"]).all()

    ridge_keys = set(
        zip(
            ridge.predictions["state_id"],
            ridge.predictions["forecast_origin"].map(pd.Timestamp),
            ridge.predictions["target_period"],
            strict=True,
        )
    )
    baseline_keys = set(
        zip(
            baseline.predictions["state_id"],
            baseline.predictions["forecast_origin"].map(pd.Timestamp),
            baseline.predictions["target_period"],
            strict=True,
        )
    )
    assert ridge_keys <= baseline_keys
    merged = ridge.predictions.merge(
        baseline.predictions,
        on=["state_id", "forecast_origin", "target_period"],
        suffixes=("_ridge", "_baseline"),
    )
    assert len(merged) == len(ridge.predictions)
    assert (
        merged["baseline_prediction_cents_per_kwh"] == merged["prediction_cents_per_kwh"]
    ).all()
    assert (merged["actual_cents_per_kwh_ridge"] == merged["actual_cents_per_kwh_baseline"]).all()


def test_future_rows_and_target_month_do_not_change_the_prediction() -> None:
    frame = _panel(end="2007-06")
    kwargs = {
        "origin_start": "2005-06",
        "origin_end": "2005-06",
        "states": ("MD", "NJ", "OH", "PA", "VA"),
        "window": "unit-test",
    }
    original = run_ridge_backtest(frame, **kwargs)
    future = _panel(end="2008-12")
    future.loc[future["period"] == "2008-06", "price_cents_per_kwh"] = 999.0
    future.loc[future["period"] == "2008-06", "revenue_million_usd"] = 1.0
    with_future = run_ridge_backtest(future, **kwargs)
    pd.testing.assert_series_equal(
        original.predictions["ridge_prediction_cents_per_kwh"].reset_index(drop=True),
        with_future.predictions["ridge_prediction_cents_per_kwh"].reset_index(drop=True),
    )

    leaked_target = frame.copy()
    leaked_target.loc[
        (leaked_target["period"] == "2006-06") & (leaked_target["state_id"] == "VA"),
        "price_cents_per_kwh",
    ] = 999.0
    poisoned = run_ridge_backtest(leaked_target, **kwargs)
    original_va = original.predictions.loc[original.predictions["state_id"] == "VA"].iloc[0]
    poisoned_va = poisoned.predictions.loc[poisoned.predictions["state_id"] == "VA"].iloc[0]
    assert poisoned_va["actual_cents_per_kwh"] == 999.0
    assert poisoned_va["ridge_prediction_cents_per_kwh"] == pytest.approx(
        original_va["ridge_prediction_cents_per_kwh"]
    )
    assert poisoned_va["target_period"] == "2006-06"


def test_feature_gap_and_missing_actual_are_counted_instead_of_filled() -> None:
    frame = _panel()
    frame = frame.loc[
        ~((frame["period"] == "2005-01") & (frame["state_id"] == "VA"))
    ].copy()
    frame.loc[frame["period"] == "2005-04", "price_cents_per_kwh"] = 12345.0
    gapped = run_ridge_backtest(
        frame,
        origin_start="2002-01",
        origin_end="2005-06",
        states=("MD", "NJ", "OH", "PA", "VA"),
        window="unit-test-gap",
    )
    # Deleted VA 2005-01 is the actual for origin 2004-01, and it also sits inside
    # the trailing windows at origins 2005-05 and 2005-06. Those are three
    # explicit skips, not one filled series. The other 15 feature gaps are the
    # 2002-01..2002-03 year-over-year cold start for all five states.
    assert gapped.n_skipped_feature_gap == 17
    assert gapped.n_skipped_missing_actual == 1
    assert gapped.n_skipped_insufficient_train == 188
    assert gapped.n_forecasts == 4
    assert set(gapped.predictions["state_id"]) == {"MD", "NJ", "OH", "PA"}
    va_skips = gapped.skips.loc[gapped.skips["state_id"] == "VA", "skip_reason"]
    assert "feature_gap" in set(va_skips)
    assert (gapped.predictions["ridge_prediction_cents_per_kwh"] == 12345.0).sum() == 0

    missing_actual = _panel()
    missing_actual = missing_actual.loc[
        ~(
            (missing_actual["period"] == "2006-06")
            & (missing_actual["state_id"] == "VA")
        )
    ].copy()
    missing = run_ridge_backtest(
        missing_actual,
        origin_start="2005-06",
        origin_end="2005-06",
        states=("VA", "PA"),
        window="unit-test-missing-actual",
    )
    assert missing.n_attempted == 2
    assert missing.n_forecasts == 1
    assert missing.n_skipped_missing_actual == 1
    assert missing.n_skipped_feature_gap == 0
    assert set(missing.predictions["state_id"]) == {"PA"}


def test_extending_past_an_earlier_holdout_cutoff_does_not_change_scores() -> None:
    frame = _panel(end="2008-12")
    kwargs = {
        "origin_start": "2005-06",
        "states": ("MD", "NJ", "OH", "PA", "VA"),
        "holdout_target_start": "2006-07",
        "window": "unit-test-holdout",
    }
    short = run_ridge_backtest(frame, origin_end="2005-06", **kwargs)
    extended = run_ridge_backtest(frame, origin_end="2008-06", **kwargs)
    assert short.n_forecasts == extended.n_forecasts == 5
    assert (short.predictions["target_period"] >= "2006-07").sum() == 0
    assert (extended.predictions["target_period"] >= "2006-07").sum() == 0
    assert extended.max_training_target_period < "2006-07"
    left = short.predictions.sort_values("state_id").reset_index(drop=True)
    right = extended.predictions.sort_values("state_id").reset_index(drop=True)
    pd.testing.assert_series_equal(
        left["ridge_prediction_cents_per_kwh"],
        right["ridge_prediction_cents_per_kwh"],
    )

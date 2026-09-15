"""Leakage tests for availability dates and the seasonal-naive baseline."""

from __future__ import annotations

import pandas as pd
import pytest

from infralens.data.availability import assumed_available_at
from infralens.evaluation.backtest import HOLDOUT_TARGET_START, run_expanding_backtest
from infralens.evaluation.baseline import (
    BaselineError,
    availability_adjusted_seasonal_naive,
    available_rows,
    target_period_for_origin,
)


def test_assumed_available_at_is_first_day_of_m_plus_3() -> None:
    assert assumed_available_at("2024-03") == pd.Timestamp("2024-06-01")
    assert assumed_available_at("2024-11") == pd.Timestamp("2025-02-01")


def test_target_period_is_twelve_months_after_origin_month() -> None:
    assert target_period_for_origin(pd.Timestamp("2024-06-30")) == "2025-06"


def _panel() -> pd.DataFrame:
    """June prices including an unavailable 2024-06 row that must never be used."""
    rows = [
        ("2022-06", "VA", 8.0, "2022-09-01"),
        ("2023-06", "VA", 10.0, "2023-09-01"),
        ("2024-06", "VA", 99.0, "2024-09-01"),
        ("2025-06", "VA", 12.0, "2025-09-01"),
        ("2023-06", "PA", 11.0, "2023-09-01"),
        ("2024-06", "PA", 88.0, "2024-09-01"),
        ("2025-06", "PA", 13.0, "2025-09-01"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "period",
            "state_id",
            "price_cents_per_kwh",
            "assumed_available_at",
        ],
    )


def test_unavailable_row_cannot_enter_available_set() -> None:
    origin = pd.Timestamp("2024-06-30")
    usable = available_rows(_panel(), origin)
    assert (usable["assumed_available_at"] > origin).sum() == 0
    assert "2024-06" not in set(usable["period"])


def test_seasonal_naive_uses_june_2023_not_unavailable_june_2024() -> None:
    origin = pd.Timestamp("2024-06-30")
    result = availability_adjusted_seasonal_naive(
        _panel(),
        forecast_origin=origin,
        state_id="VA",
    )
    assert result["target_period"] == "2025-06"
    assert result["source_period"] == "2023-06"
    assert result["prediction_cents_per_kwh"] == 10.0
    assert pd.Timestamp(result["source_assumed_available_at"]) <= origin
    assert result["source_period"] != "2024-06"


def test_seasonal_naive_raises_if_only_unavailable_same_month_exists() -> None:
    frame = pd.DataFrame(
        [
            {
                "period": "2024-06",
                "state_id": "VA",
                "price_cents_per_kwh": 99.0,
                "assumed_available_at": pd.Timestamp("2024-09-01"),
            }
        ]
    )
    with pytest.raises(BaselineError, match="No available same-month analog"):
        availability_adjusted_seasonal_naive(
            frame,
            forecast_origin=pd.Timestamp("2024-06-30"),
            state_id="VA",
        )


def test_backtest_never_uses_rows_after_origin() -> None:
    frame = _panel()
    result = run_expanding_backtest(
        frame,
        origin_start="2024-06",
        origin_end="2024-06",
        states=("VA", "PA"),
        window="unit-test",
    )
    assert result.n_forecasts == 2
    assert result.n_attempted == 2
    assert result.n_skipped_no_analog == 0
    assert result.n_skipped_missing_actual == 0
    assert result.n_attempted == (
        result.n_forecasts
        + result.n_skipped_no_analog
        + result.n_skipped_missing_actual
    )
    assert (
        result.predictions["source_assumed_available_at"]
        > result.predictions["forecast_origin"]
    ).sum() == 0
    assert set(result.predictions["source_period"]) == {"2023-06"}
    assert "2024-06" not in set(result.predictions["source_period"])
    assert result.predictions["target_period"].eq("2025-06").all()
    assert result.predictions["target_period"].lt(HOLDOUT_TARGET_START).all()


def _boundary_panel() -> pd.DataFrame:
    """June (development) and July/August (holdout) actuals with t-24 analogs."""
    rows = [
        ("2023-06", "VA", 10.0, "2023-09-01"),
        ("2025-06", "VA", 12.0, "2025-09-01"),
        ("2023-07", "VA", 20.0, "2023-10-01"),
        ("2025-07", "VA", 22.0, "2025-10-01"),
        ("2023-08", "VA", 30.0, "2023-11-01"),
        ("2025-08", "VA", 32.0, "2025-11-01"),
    ]
    return pd.DataFrame(
        rows,
        columns=["period", "state_id", "price_cents_per_kwh", "assumed_available_at"],
    )


def test_backtest_excludes_holdout_targets_when_origin_end_extends() -> None:
    frame = _boundary_panel()
    development = run_expanding_backtest(
        frame,
        origin_start="2024-06",
        origin_end="2024-06",
        states=("VA",),
        window="unit-test-dev",
    )
    extended = run_expanding_backtest(
        frame,
        origin_start="2024-06",
        origin_end="2025-08",
        states=("VA",),
        window="unit-test-extended",
    )
    assert (development.predictions["target_period"] >= HOLDOUT_TARGET_START).sum() == 0
    assert (extended.predictions["target_period"] >= HOLDOUT_TARGET_START).sum() == 0
    assert set(development.predictions["target_period"]) == {"2025-06"}
    assert set(extended.predictions["target_period"]) == {"2025-06"}
    assert development.n_forecasts == extended.n_forecasts == 1
    assert development.n_attempted == extended.n_attempted
    scored_dev = development.predictions.sort_values(["state_id", "target_period"])
    scored_ext = extended.predictions.sort_values(["state_id", "target_period"])
    pd.testing.assert_frame_equal(
        scored_dev.reset_index(drop=True),
        scored_ext.reset_index(drop=True),
    )


def test_backtest_reports_skip_reasons() -> None:
    rows = [
        ("2023-06", "VA", 10.0, "2023-09-01"),
        ("2025-06", "VA", 12.0, "2025-09-01"),
        ("2024-06", "PA", 88.0, "2024-09-01"),
        ("2025-06", "PA", 13.0, "2025-09-01"),
        ("2023-06", "OH", 9.0, "2023-09-01"),
    ]
    frame = pd.DataFrame(
        rows,
        columns=["period", "state_id", "price_cents_per_kwh", "assumed_available_at"],
    )
    result = run_expanding_backtest(
        frame,
        origin_start="2024-06",
        origin_end="2024-06",
        states=("VA", "PA", "OH"),
        window="unit-test-skips",
    )
    assert result.n_attempted == 3
    assert result.n_forecasts == 1
    assert result.n_skipped_no_analog == 1
    assert result.n_skipped_missing_actual == 1
    assert result.n_attempted == (
        result.n_forecasts
        + result.n_skipped_no_analog
        + result.n_skipped_missing_actual
    )
    assert set(result.predictions["state_id"]) == {"VA"}


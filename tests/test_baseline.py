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
    assert (
        result.predictions["source_assumed_available_at"]
        > result.predictions["forecast_origin"]
    ).sum() == 0
    assert set(result.predictions["source_period"]) == {"2023-06"}
    assert "2024-06" not in set(result.predictions["source_period"])
    assert result.predictions["target_period"].eq("2025-06").all()
    assert result.predictions["target_period"].lt(HOLDOUT_TARGET_START).all()

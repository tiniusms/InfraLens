"""Leakage and arithmetic tests for Ridge absolute-residual intervals."""

from __future__ import annotations

import pandas as pd
import pytest

from infralens.evaluation.backtest import HOLDOUT_TARGET_START
from infralens.evaluation.intervals import (
    MIN_CALIBRATION_RESIDUALS,
    STATUS_INSUFFICIENT_RESIDUAL_HISTORY,
    STATUS_INTERVAL,
    IntervalError,
    absolute_residuals,
    build_ridge_intervals,
    eligible_calibration_mask,
    order_statistic_index,
)
from infralens.evaluation.linear import ALPHA_GRID
from infralens.evaluation.selection import FEATURE_SET_ID, FROZEN_FEATURES, SELECTED_MODEL
from infralens.evaluation.tree import TREE_GRID


def _row(
    *,
    origin: str,
    state: str,
    target: str,
    prediction: float,
    actual: float,
    available: str,
) -> dict[str, object]:
    return {
        "state_id": state,
        "forecast_origin": pd.Timestamp(origin),
        "target_period": target,
        "ridge_prediction_cents_per_kwh": prediction,
        "actual_cents_per_kwh": actual,
        "label_assumed_available_at": pd.Timestamp(available),
    }


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _monthly_history(
    *,
    n: int,
    state: str = "VA",
    start: str = "2006-01-31",
    prediction: float = 10.0,
    residuals: list[float] | None = None,
) -> list[dict[str, object]]:
    """Earlier rolling-origin rows whose labels are available well before a 2010 origin."""
    origins = pd.date_range(start, periods=n, freq="ME")
    values = residuals if residuals is not None else [float(index) for index in range(1, n + 1)]
    if len(values) != n:
        raise AssertionError("Residual list length must match history length.")
    rows: list[dict[str, object]] = []
    for origin, residual in zip(origins, values, strict=True):
        target = (origin + pd.DateOffset(months=12)).strftime("%Y-%m")
        rows.append(
            _row(
                origin=str(origin.date()),
                state=state,
                target=target,
                prediction=prediction,
                actual=prediction + residual,
                available="2008-01-01",
            )
        )
    return rows


def test_calibration_uses_only_earlier_rolling_origin_predictions(monkeypatch) -> None:
    def fail_if_refit(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Interval construction refit Ridge.")

    monkeypatch.setattr("infralens.evaluation.linear.fit_ridge", fail_if_refit)
    monkeypatch.setattr("infralens.evaluation.linear.run_ridge_backtest", fail_if_refit)
    history = _monthly_history(n=24, residuals=[float(index) for index in range(1, 25)])
    scored = _row(
        origin="2010-01-31",
        state="VA",
        target="2011-01",
        prediction=10.0,
        actual=110.0,
        available="2011-04-01",
    )
    frame = _frame([*history, scored])
    # A fitted in-sample column must not be read even if a caller attaches one.
    frame["in_sample_fitted"] = 0.0
    intervals = build_ridge_intervals(frame)
    scored_row = intervals.loc[intervals["forecast_origin"] == pd.Timestamp("2010-01-31")].iloc[0]
    mask = eligible_calibration_mask(
        frame,
        state_id="VA",
        forecast_origin=pd.Timestamp("2010-01-31"),
    )
    pool = frame.loc[mask]
    assert pool["forecast_origin"].max() < pd.Timestamp("2010-01-31")
    assert set(absolute_residuals(pool)) == set(range(1, 25))
    assert int(scored_row["n_calibration_residuals"]) == 24
    assert scored_row["half_width_cents_per_kwh"] == 20.0


def test_unavailable_target_cannot_enter_calibration() -> None:
    history = _monthly_history(n=24, residuals=[float(index) for index in range(1, 25)])
    unavailable = _row(
        origin="2008-01-31",
        state="VA",
        target="2009-01",
        prediction=10.0,
        actual=1010.0,
        available="2010-02-01",
    )
    scored = _row(
        origin="2010-01-31",
        state="VA",
        target="2011-01",
        prediction=10.0,
        actual=10.0,
        available="2011-04-01",
    )
    frame = _frame([*history, unavailable, scored])
    mask = eligible_calibration_mask(
        frame,
        state_id="VA",
        forecast_origin=pd.Timestamp("2010-01-31"),
    )
    assert pd.Timestamp("2008-01-31") not in set(frame.loc[mask, "forecast_origin"])
    intervals = build_ridge_intervals(frame)
    scored_row = intervals.loc[intervals["forecast_origin"] == pd.Timestamp("2010-01-31")].iloc[0]
    assert int(scored_row["n_calibration_residuals"]) == 24
    assert scored_row["half_width_cents_per_kwh"] == 20.0


def test_holdout_target_months_do_not_enter_calibration() -> None:
    history = _monthly_history(n=24, residuals=[float(index) for index in range(1, 25)])
    holdout = _row(
        origin="2008-06-30",
        state="VA",
        target="2025-07",
        prediction=10.0,
        actual=1010.0,
        available="2008-01-01",
    )
    frame = _frame([*history, holdout])
    mask = eligible_calibration_mask(
        frame,
        state_id="VA",
        forecast_origin=pd.Timestamp("2010-01-31"),
    )
    assert "2025-07" not in set(frame.loc[mask, "target_period"])
    assert int(mask.sum()) == 24


def test_scored_case_cannot_calibrate_itself() -> None:
    history = _monthly_history(n=24, residuals=[float(index) for index in range(1, 25)])
    scored = _row(
        origin="2010-01-31",
        state="VA",
        target="2011-01",
        prediction=10.0,
        actual=110.0,
        available="2009-01-01",
    )
    frame = _frame([*history, scored])
    origin = pd.Timestamp("2010-01-31")
    mask = eligible_calibration_mask(frame, state_id="VA", forecast_origin=origin)
    assert origin not in set(frame.loc[mask, "forecast_origin"])
    intervals = build_ridge_intervals(frame)
    scored_row = intervals.loc[intervals["forecast_origin"] == origin].iloc[0]
    # Including the scored residual of 100 would move e(k) from 20 to 21.
    assert scored_row["half_width_cents_per_kwh"] == 20.0
    assert int(scored_row["k"]) == 20


def test_residual_pools_are_state_specific() -> None:
    virginia = _monthly_history(
        n=24,
        state="VA",
        residuals=[float(index) for index in range(1, 25)],
    )
    maryland = _monthly_history(n=24, state="MD", residuals=[50.0] * 24)
    scored = [
        _row(
            origin="2010-01-31",
            state="VA",
            target="2011-01",
            prediction=10.0,
            actual=10.0,
            available="2011-04-01",
        ),
        _row(
            origin="2010-01-31",
            state="MD",
            target="2011-01",
            prediction=10.0,
            actual=10.0,
            available="2011-04-01",
        ),
    ]
    frame = _frame([*virginia, *maryland, *scored])
    intervals = build_ridge_intervals(frame)
    origin = pd.Timestamp("2010-01-31")
    virginia_row = intervals.loc[
        (intervals["state_id"] == "VA") & (intervals["forecast_origin"] == origin)
    ].iloc[0]
    maryland_row = intervals.loc[
        (intervals["state_id"] == "MD") & (intervals["forecast_origin"] == origin)
    ].iloc[0]
    assert virginia_row["half_width_cents_per_kwh"] == 20.0
    assert maryland_row["half_width_cents_per_kwh"] == 50.0


def test_fewer_than_24_residuals_keeps_the_point_without_an_interval() -> None:
    history = _monthly_history(n=MIN_CALIBRATION_RESIDUALS - 1, residuals=[5.0] * 23)
    scored = _row(
        origin="2010-01-31",
        state="VA",
        target="2011-01",
        prediction=12.5,
        actual=12.5,
        available="2011-04-01",
    )
    intervals = build_ridge_intervals(_frame([*history, scored]))
    row = intervals.loc[intervals["forecast_origin"] == pd.Timestamp("2010-01-31")].iloc[0]
    assert int(row["n_calibration_residuals"]) == 23
    assert int(row["k"]) == order_statistic_index(23)
    assert int(row["k"]) <= 23
    assert row["interval_status"] == STATUS_INSUFFICIENT_RESIDUAL_HISTORY
    assert row["ridge_prediction_cents_per_kwh"] == 12.5
    assert pd.isna(row["half_width_cents_per_kwh"])
    assert pd.isna(row["lower_cents_per_kwh"])
    assert pd.isna(row["upper_cents_per_kwh"])
    assert pd.isna(row["covered"])


def test_order_statistic_uses_exact_ceil_of_four_fifths() -> None:
    assert order_statistic_index(0) == 1
    assert order_statistic_index(3) == 4
    assert order_statistic_index(4) == 4
    assert order_statistic_index(23) == 20
    assert order_statistic_index(24) == 20
    assert order_statistic_index(25) == 21
    assert order_statistic_index(29) == 24
    # n=3 has k > n, so the guard is not only the minimum of 24.
    short = _monthly_history(n=3, residuals=[1.0, 2.0, 3.0])
    scored = _row(
        origin="2010-01-31",
        state="VA",
        target="2011-01",
        prediction=4.0,
        actual=4.0,
        available="2011-04-01",
    )
    row = build_ridge_intervals(_frame([*short, scored])).iloc[-1]
    assert int(row["k"]) == 4
    assert int(row["k"]) > int(row["n_calibration_residuals"])
    assert row["interval_status"] == STATUS_INSUFFICIENT_RESIDUAL_HISTORY


def test_half_width_is_the_order_statistic_without_interpolation() -> None:
    residuals = [1.0] * 19 + [3.0, 100.0, 100.0, 100.0, 100.0]
    history = _monthly_history(n=24, residuals=residuals)
    scored = _row(
        origin="2010-01-31",
        state="VA",
        target="2011-01",
        prediction=8.0,
        actual=8.0,
        available="2011-04-01",
    )
    row = build_ridge_intervals(_frame([*history, scored])).iloc[-1]
    assert int(row["k"]) == 20
    assert row["half_width_cents_per_kwh"] == 3.0
    assert row["half_width_cents_per_kwh"] != pytest.approx(51.5)


def test_bounds_equal_point_prediction_plus_or_minus_selected_residual() -> None:
    history = _monthly_history(n=24, residuals=[1.0] * 19 + [3.0, 100.0, 100.0, 100.0, 100.0])
    inside = _row(
        origin="2010-01-31",
        state="VA",
        target="2011-01",
        prediction=8.0,
        actual=9.0,
        available="2011-04-01",
    )
    outside = _row(
        origin="2010-02-28",
        state="VA",
        target="2011-02",
        prediction=8.0,
        actual=12.0,
        available="2011-05-01",
    )
    intervals = build_ridge_intervals(_frame([*history, inside, outside]))
    inside_row = intervals.loc[intervals["forecast_origin"] == pd.Timestamp("2010-01-31")].iloc[0]
    outside_row = intervals.loc[intervals["forecast_origin"] == pd.Timestamp("2010-02-28")].iloc[0]
    assert inside_row["interval_status"] == STATUS_INTERVAL
    assert inside_row["lower_cents_per_kwh"] == 5.0
    assert inside_row["upper_cents_per_kwh"] == 11.0
    assert bool(inside_row["covered"]) is True
    assert outside_row["lower_cents_per_kwh"] == 5.0
    assert outside_row["upper_cents_per_kwh"] == 11.0
    assert bool(outside_row["covered"]) is False


def test_interval_construction_does_not_alter_the_ridge_point_prediction() -> None:
    history = _monthly_history(n=24, residuals=[2.0] * 24)
    scored = _row(
        origin="2010-01-31",
        state="VA",
        target="2011-01",
        prediction=7.25,
        actual=8.0,
        available="2011-04-01",
    )
    frame = _frame([*history, scored])
    frame["alpha"] = 100.0
    before = frame.copy()
    intervals = build_ridge_intervals(frame)
    pd.testing.assert_frame_equal(frame, before)
    assert intervals["ridge_prediction_cents_per_kwh"].tolist() == (
        frame["ridge_prediction_cents_per_kwh"].tolist()
    )
    assert intervals.iloc[-1]["ridge_prediction_cents_per_kwh"] == 7.25


def test_frozen_ridge_and_tree_specification_is_unchanged() -> None:
    assert SELECTED_MODEL == "ridge"
    assert FEATURE_SET_ID == "eia_commercial_price_v1"
    assert FROZEN_FEATURES == (
        "price_latest",
        "price_same_month",
        "price_yoy_change",
        "price_trail12_mean",
        "sales_latest",
        "sales_yoy_change",
        "state_id",
        "target_calendar_month",
    )
    assert ALPHA_GRID == (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
    assert len(TREE_GRID) == 6
    assert HOLDOUT_TARGET_START == "2025-07"
    assert MIN_CALIBRATION_RESIDUALS == 24


def test_final_holdout_targets_are_not_scored() -> None:
    history = _monthly_history(n=24, residuals=[1.0] * 24)
    holdout = _row(
        origin="2024-07-31",
        state="VA",
        target="2025-07",
        prediction=10.0,
        actual=11.0,
        available="2025-10-01",
    )
    with pytest.raises(IntervalError, match="Holdout target was scored"):
        build_ridge_intervals(_frame([*history, holdout]))
    development = build_ridge_intervals(
        _frame(
            [
                *history,
                _row(
                    origin="2010-01-31",
                    state="VA",
                    target="2011-01",
                    prediction=10.0,
                    actual=10.0,
                    available="2011-04-01",
                ),
            ]
        )
    )
    assert development["target_period"].astype(str).max() < HOLDOUT_TARGET_START

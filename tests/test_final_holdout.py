"""Tests for the locked final-holdout runner. None of these read the EIA extract."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from infralens.data.availability import assumed_available_at
from infralens.evaluation.backtest import HOLDOUT_TARGET_START
from infralens.evaluation.final_holdout import (
    CASE_COLUMNS,
    FINAL_STATES,
    LOCKED_ALPHA_GRID,
    LOCKED_ORIGIN_TARGETS,
    PRIMARY_RELATIVE_IMPROVEMENT,
    FinalHoldoutError,
    _score_locked_grid,
    locked_cells,
    main,
    primary_criterion_passes,
    relative_improvement,
    run_final_holdout,
)
from infralens.evaluation.intervals import build_ridge_intervals
from infralens.evaluation.linear import (
    ALPHA_GRID,
    INNER_VALIDATION_ORIGINS,
    MIN_FIT_ORIGINS,
    select_alpha,
    training_cases_for_origin,
)


def _panel(start: str = "2001-01", end: str = "2026-06") -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for period in pd.period_range(start, end, freq="M"):
        label = str(period)
        for index, state in enumerate(FINAL_STATES):
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


def _history(n: int = 30) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    origins = pd.date_range("2010-01-31", periods=n, freq="ME")
    for origin in origins:
        target = (origin + pd.DateOffset(months=12)).strftime("%Y-%m")
        for state in FINAL_STATES:
            rows.append(
                {
                    "state_id": state,
                    "forecast_origin": pd.Timestamp(origin),
                    "target_period": target,
                    "ridge_prediction_cents_per_kwh": 10.0,
                    "actual_cents_per_kwh": 11.0,
                    "label_assumed_available_at": pd.Timestamp("2012-01-01"),
                }
            )
    return pd.DataFrame(rows)


def test_locked_grid_attempts_sixty_cells_with_the_twelve_month_map() -> None:
    cells = locked_cells()
    assert len(cells) == 60
    assert cells == locked_cells()
    origins = [origin.date().isoformat() for origin, _state, _target in cells[::5]]
    targets = [target for _origin, _state, target in cells[::5]]
    assert list(zip(origins, targets, strict=True)) == list(LOCKED_ORIGIN_TARGETS)
    assert {state for _origin, state, _target in cells} == set(FINAL_STATES)
    assert cells[0] == (pd.Timestamp("2024-07-31"), "MD", "2025-07")
    assert cells[-1] == (pd.Timestamp("2025-06-30"), "VA", "2026-06")


def test_exact_ten_percent_passes_and_less_does_not() -> None:
    assert relative_improvement(5.0, 4.5) == pytest.approx(0.10)
    assert primary_criterion_passes(relative_improvement(5.0, 4.5)) is True
    assert primary_criterion_passes(PRIMARY_RELATIVE_IMPROVEMENT) is True
    assert relative_improvement(5.0, 4.75) == pytest.approx(0.05)
    assert primary_criterion_passes(relative_improvement(5.0, 4.75)) is False


def test_runner_accepts_no_cli_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_loaded(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("CLI rejection loaded the EIA extract.")

    monkeypatch.setattr(
        "infralens.evaluation.final_holdout.latest_eia_parquet",
        fail_if_loaded,
    )
    monkeypatch.setattr(
        "infralens.evaluation.final_holdout.load_price_panel",
        fail_if_loaded,
    )
    for arguments in (
        ["--threshold", "0"],
        ["--alpha", "1"],
        ["--states", "VA"],
        ["--origin-end", "2026-06"],
        ["--coverage", "0.5"],
        ["--min-residuals", "1"],
    ):
        with pytest.raises(FinalHoldoutError, match="no options"):
            main(arguments)


def test_development_interval_api_still_rejects_holdout_rows() -> None:
    history = _history(24)
    holdout = history.iloc[[0]].copy()
    holdout["target_period"] = "2025-07"
    holdout["forecast_origin"] = pd.Timestamp("2024-07-31")
    with pytest.raises(Exception, match="Holdout target was scored"):
        build_ridge_intervals(pd.concat([history, holdout], ignore_index=True))


def test_holdout_calibration_excludes_holdout_targets_and_the_scored_case() -> None:
    history = _history(30)
    leaked = history.iloc[[0]].copy()
    leaked["target_period"] = "2025-07"
    leaked["forecast_origin"] = pd.Timestamp("2020-01-31")
    leaked["actual_cents_per_kwh"] = 1000.0
    leaked["label_assumed_available_at"] = pd.Timestamp("2012-01-01")
    same_origin = history.iloc[[0]].copy()
    same_origin["forecast_origin"] = pd.Timestamp("2024-07-31")
    same_origin["target_period"] = "2024-06"
    same_origin["actual_cents_per_kwh"] = 1000.0
    contaminated = pd.concat([history, leaked, same_origin], ignore_index=True)
    with pytest.raises(FinalHoldoutError, match="calibration history"):
        from infralens.evaluation.final_holdout import holdout_interval

        holdout_interval(
            contaminated,
            state_id="MD",
            forecast_origin=pd.Timestamp("2024-07-31"),
            point_prediction=10.0,
            actual=10.0,
        )
    from infralens.evaluation.final_holdout import holdout_interval

    interval = holdout_interval(
        history,
        state_id="MD",
        forecast_origin=pd.Timestamp("2024-07-31"),
        point_prediction=10.0,
        actual=11.0,
    )
    assert interval["interval_status"] == "interval"
    assert int(interval["n_calibration_residuals"]) == 30
    with_self = pd.concat([history, same_origin], ignore_index=True)
    excluding_self = holdout_interval(
        with_self,
        state_id="MD",
        forecast_origin=pd.Timestamp("2024-07-31"),
        point_prediction=10.0,
        actual=11.0,
    )
    assert int(excluding_self["n_calibration_residuals"]) == 30
    assert interval["lower_cents_per_kwh"] == pytest.approx(9.0)
    assert interval["upper_cents_per_kwh"] == pytest.approx(11.0)


def test_runner_source_does_not_use_development_mae_as_the_holdout_baseline() -> None:
    source = Path("src/infralens/evaluation/final_holdout.py").read_text(encoding="utf-8")
    assert "0.7793" not in source
    assert "0.7997" not in source
    assert "0.7075" not in source


def test_synthetic_grid_keeps_training_labels_before_the_holdout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    frame = _panel()
    frame.loc[
        (frame["state_id"] == "VA") & (frame["period"] == "2025-07"),
        "price_cents_per_kwh",
    ] = float("nan")
    recorded: list[tuple[pd.Timestamp, pd.DataFrame, str]] = []

    def spy_train(cases: pd.DataFrame, *, forecast_origin: pd.Timestamp, holdout_target_start: str) -> pd.DataFrame:
        train = training_cases_for_origin(
            cases,
            forecast_origin=forecast_origin,
            holdout_target_start=holdout_target_start,
        )
        recorded.append((pd.Timestamp(forecast_origin), train, holdout_target_start))
        return train

    def spy_alpha(train: pd.DataFrame, **kwargs: object) -> object:
        assert kwargs["alpha_grid"] == ALPHA_GRID == LOCKED_ALPHA_GRID
        assert kwargs["inner_validation_origins"] == INNER_VALIDATION_ORIGINS == 12
        assert kwargs["min_fit_origins"] == MIN_FIT_ORIGINS == 12
        return select_alpha(train, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "infralens.evaluation.final_holdout.training_cases_for_origin",
        spy_train,
    )
    monkeypatch.setattr("infralens.evaluation.final_holdout.select_alpha", spy_alpha)
    result = _score_locked_grid(frame, _history(), extract_id="synthetic")
    assert result.summary["attempted"] == 60
    assert result.summary["scored_paired"] == 59
    assert result.summary["skip_counts"]["missing_actual"] == 1
    assert sum(result.summary["skip_counts"].values()) + result.summary["scored_paired"] == 60
    assert len(recorded) == 12
    for origin, train, cutoff in recorded:
        assert cutoff == HOLDOUT_TARGET_START == "2025-07"
        assert train.empty or (train["target_period"].astype(str) < "2025-07").all()
        assert train.empty or (pd.to_datetime(train["forecast_origin"]) < origin).all()
        assert train.empty or (pd.to_datetime(train["label_assumed_available_at"]) <= origin).all()
    scored = result.cases.loc[result.cases["skip_reason"].isna()]
    skipped = result.cases.loc[result.cases["skip_reason"].notna()]
    assert skipped["seasonal_naive_prediction"].isna().all()
    assert skipped["ridge_prediction"].isna().all()
    assert scored["seasonal_naive_prediction"].notna().all()
    assert scored["ridge_prediction"].notna().all()
    assert (scored["max_training_target_period"].astype(str) < "2025-07").all()
    assert set(scored["selected_alpha"]).issubset(set(LOCKED_ALPHA_GRID))
    assert result.cases["forecast_origin"].is_monotonic_increasing
    assert list(result.cases.columns) == list(CASE_COLUMNS)
    repeated = _score_locked_grid(frame, _history(), extract_id="synthetic")
    pd.testing.assert_frame_equal(result.cases, repeated.cases)
    assert result.summary["primary_criterion"] in {"PASS", "FAIL"}
    assert result.summary["primary_threshold_percent"] == 10
    # Interval coverage is present and is not the field that carries the gate.
    assert "interval_coverage" in result.summary
    assert result.summary["primary_criterion"] == (
        "PASS" if result.summary["mae_improvement_ratio"] >= 0.10 else "FAIL"
    )
    from infralens.evaluation.final_holdout import write_holdout_result

    cases_path, summary_path = write_holdout_result(result, tmp_path)
    assert cases_path.exists() and summary_path.exists()
    assert "eia_retail_sales" not in summary_path.read_text(encoding="utf-8")


def test_run_final_holdout_rejects_development_predictions_that_scored_the_holdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_backtest(_frame: pd.DataFrame) -> object:
        class Result:
            window = "development"
            predictions = _history().assign(target_period="2025-07")

        return Result()

    monkeypatch.setattr("infralens.evaluation.final_holdout.run_ridge_backtest", fake_backtest)
    with pytest.raises(FinalHoldoutError, match="holdout target"):
        run_final_holdout(_panel(start="2024-01", end="2024-03"), extract_id="synthetic")


def test_state_mae_and_interval_coverage_do_not_decide_the_primary_gate() -> None:
    from infralens.evaluation.final_holdout import _summary

    rows: list[dict[str, object]] = []
    for state, ridge_error in (
        ("MD", 2.0),
        ("NJ", 0.5),
        ("OH", 0.5),
        ("PA", 0.5),
        ("VA", 0.5),
    ):
        for _ in range(4):
            rows.append(
                {
                    "state_id": state,
                    "skip_reason": None,
                    "ridge_absolute_error": ridge_error,
                    "baseline_absolute_error": 1.0,
                    "interval_status": "interval",
                    "interval_covered": False,
                    "interval_width": 9.0,
                }
            )
    summary = _summary(pd.DataFrame(rows), extract_id="synthetic")
    assert summary["primary_criterion"] == "PASS"
    assert summary["mae_by_state"]["MD"]["ridge_mae"] > summary["mae_by_state"]["MD"]["paired_baseline_mae"]
    assert summary["interval_coverage"] == 0.0

    fail_rows = []
    for state in FINAL_STATES:
        fail_rows.append(
            {
                "state_id": state,
                "skip_reason": None,
                "ridge_absolute_error": 1.0,
                "baseline_absolute_error": 1.0,
                "interval_status": "interval",
                "interval_covered": True,
                "interval_width": 1.0,
            }
        )
    failed = _summary(pd.DataFrame(fail_rows), extract_id="synthetic")
    assert failed["interval_coverage"] == 1.0
    assert failed["primary_criterion"] == "FAIL"

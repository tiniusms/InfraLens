"""Charts for observed EIA prices and the closed holdout. They do not score it."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from infralens.demo.eia_views import (
    ACTUAL_SERIES_LABEL,
    CLOSED_PREDICTION_ROLE,
    DEMO_STATES,
    HISTORY_LIMITATIONS,
    HOLDOUT_SECTION_LABEL,
    HOLDOUT_TARGET_MONTHS,
    HYPOTHETICAL_ROLE,
    MISSING_HOLDOUT_CHART,
    MISSING_PRICE_HISTORY,
    NAIVE_SERIES_LABEL,
    OBSERVED_PRICE_LABEL,
    OBSERVED_ROLE,
    RIDGE_SERIES_LABEL,
    chart_series_catalog,
    holdout_line_frame,
    holdout_plot_frame,
    holdout_provenance,
    load_holdout_comparison,
    load_price_history,
    price_plot_frame,
)
from infralens.demo.foundation import (
    FROZEN_EXTRACT_ID,
    DemoDataError,
    default_artifact_paths,
    load_holdout_banner,
)
from infralens.finance.annual_cost import EIA_MODEL_PRICE_WARNING


def test_price_history_schema_covers_five_states_in_order(tmp_path: Path) -> None:
    path = tmp_path / "prices.parquet"
    _write_prices(path)
    history = load_price_history(path)
    assert history.states == DEMO_STATES
    assert history.latest_period == "2026-06"
    assert history.earliest_period == "2026-05"
    assert history.row_count == 10
    assert history.limitations == HISTORY_LIMITATIONS
    frame = price_plot_frame(history, "VA")
    assert list(frame["period"]) == ["2026-05", "2026-06"]
    assert frame["role"].eq(OBSERVED_ROLE).all()
    assert frame["series"].eq(OBSERVED_PRICE_LABEL).all()
    assert "forecast_origin" not in frame.columns
    assert frame.loc[frame["period"].eq("2026-06"), "observed_commercial_average_price_cents_per_kwh"].iloc[0] == 15.0


def test_local_price_history_matches_the_frozen_extract() -> None:
    path = default_artifact_paths().price_history
    if not path.is_file():
        pytest.skip("local EIA parquet is not on this machine")
    history = load_price_history(path, extract_id=FROZEN_EXTRACT_ID)
    assert history.extract_id == FROZEN_EXTRACT_ID
    assert history.earliest_period == "2001-01"
    assert history.latest_period == "2026-06"
    assert history.row_count == 1530
    assert history.states == ("VA", "PA", "OH", "MD", "NJ")
    assert history.retrieved_at == "2026-09-11T19:05:24.708930+00:00"
    virginia = price_plot_frame(history, "VA")
    assert len(virginia) == 306
    assert virginia["period"].iloc[0] == "2001-01"
    assert virginia["period"].iloc[-1] == "2026-06"
    assert "forecast_origin" not in virginia.columns


def test_price_history_rejects_missing_malformed_and_wrong_extract(tmp_path: Path) -> None:
    with pytest.raises(DemoDataError, match="not on this machine"):
        load_price_history(tmp_path / "absent.parquet")
    wrong_name = tmp_path / "other.parquet"
    _write_prices(wrong_name)
    with pytest.raises(DemoDataError, match="not the frozen extract"):
        load_price_history(wrong_name, extract_id=FROZEN_EXTRACT_ID)
    dropped = _price_rows()
    dropped = dropped.drop(columns=["price_cents_per_kwh"])
    dropped_path = tmp_path / "dropped.parquet"
    dropped.to_parquet(dropped_path, index=False)
    with pytest.raises(DemoDataError, match="missing columns"):
        load_price_history(dropped_path)
    duplicate = pd.concat([_price_rows(), _price_rows()], ignore_index=True)
    duplicate_path = tmp_path / "duplicate.parquet"
    duplicate.to_parquet(duplicate_path, index=False)
    with pytest.raises(DemoDataError, match="Duplicate"):
        load_price_history(duplicate_path)
    gapped = _price_rows()
    gapped.loc[gapped["period"].eq("2026-05"), "period"] = "2026-04"
    gapped_path = tmp_path / "gapped.parquet"
    gapped.to_parquet(gapped_path, index=False)
    with pytest.raises(DemoDataError, match="gap"):
        load_price_history(gapped_path)


def test_holdout_grid_is_sixty_cases_sorted_by_target_month(tmp_path: Path) -> None:
    path = tmp_path / "cases.parquet"
    _write_holdout(path, shuffle=True)
    comparison = load_holdout_comparison(path)
    assert comparison.row_count == 60
    assert comparison.origin_start == "2024-07-31"
    assert comparison.origin_end == "2025-06-30"
    assert comparison.target_start == "2025-07"
    assert comparison.target_end == "2026-06"
    counts = {state: 0 for state in DEMO_STATES}
    for point in comparison.points:
        counts[point.state_id] += 1
        assert point.forecast_origin != point.target_month
    assert counts == {state: 12 for state in DEMO_STATES}
    july = comparison.point_for("VA", "2025-07")
    assert july.forecast_origin == "2024-07-31"
    assert july.actual_cents_per_kwh == Decimal("10.21")
    assert july.ridge_prediction_cents_per_kwh == Decimal("8.633044")
    assert july.seasonal_naive_prediction_cents_per_kwh == Decimal("8.84")
    plot = holdout_plot_frame(comparison, "VA")
    assert list(plot["target_month"]) == list(HOLDOUT_TARGET_MONTHS)
    assert "forecast_origin" not in plot.columns
    assert plot.loc[0, "actual_observed_cents_per_kwh"] == pytest.approx(10.21)
    assert plot.loc[0, "ridge_closed_prediction_cents_per_kwh"] == pytest.approx(8.633044)
    assert plot.loc[0, "seasonal_naive_closed_prediction_cents_per_kwh"] == pytest.approx(8.84)
    assert plot.loc[1, "target_month"] == "2025-08"
    assert plot.loc[1, "actual_observed_cents_per_kwh"] == pytest.approx(9.46)
    lines = holdout_line_frame(plot)
    assert set(lines["series"]) == {ACTUAL_SERIES_LABEL, RIDGE_SERIES_LABEL, NAIVE_SERIES_LABEL}
    assert set(lines["role"]) == {OBSERVED_ROLE, CLOSED_PREDICTION_ROLE}
    assert HYPOTHETICAL_ROLE not in set(lines["role"])
    assert "forecast_origin" not in lines.columns
    july_actual = lines.loc[
        lines["target_month"].eq("2025-07") & lines["series"].eq(ACTUAL_SERIES_LABEL),
        "cents_per_kwh",
    ].iloc[0]
    assert july_actual == pytest.approx(10.21)


def test_stored_intervals_keep_zero_coverage_and_are_not_synthesized(tmp_path: Path) -> None:
    path = tmp_path / "cases.parquet"
    _write_holdout(path, with_intervals=True)
    comparison = load_holdout_comparison(path)
    assert comparison.has_intervals is True
    assert comparison.empirical_interval_coverage == 0
    assert comparison.interval_warning is not None
    assert "0%" in comparison.interval_warning
    assert "nominal 80%" in comparison.interval_warning
    assert "Not a forward-looking forecast interval." in comparison.interval_warning
    july = comparison.point_for("VA", "2025-07")
    assert july.interval_covered is False
    assert july.interval_lower_cents_per_kwh == Decimal("7.759795")
    assert july.interval_upper_cents_per_kwh == Decimal("9.506292")
    assert july.actual_cents_per_kwh > july.interval_upper_cents_per_kwh
    plot = holdout_plot_frame(comparison, "VA")
    assert plot.loc[0, "interval_lower_cents_per_kwh"] == pytest.approx(7.759795)
    assert plot.loc[0, "interval_upper_cents_per_kwh"] == pytest.approx(9.506292)
    bare = tmp_path / "bare.parquet"
    _write_holdout(bare, with_intervals=False)
    without = load_holdout_comparison(bare)
    assert without.has_intervals is False
    assert without.interval_warning is None
    assert "interval_lower_cents_per_kwh" not in holdout_plot_frame(without, "PA").columns
    partial = _holdout_frame(with_intervals=True).drop(columns=["interval_upper"])
    partial_path = tmp_path / "partial.parquet"
    partial.to_parquet(partial_path, index=False)
    with pytest.raises(DemoDataError, match="will not be synthesized"):
        load_holdout_comparison(partial_path)


def test_local_holdout_file_matches_the_closed_window() -> None:
    path = default_artifact_paths().holdout_cases
    if not path.is_file():
        pytest.skip("local holdout cases are not on this machine")
    comparison = load_holdout_comparison(path)
    assert comparison.row_count == 60
    assert comparison.empirical_interval_coverage == 0
    banner = load_holdout_banner(default_artifact_paths().committed_summary)
    provenance = holdout_provenance(comparison, banner)
    assert provenance.axis == "target_month"
    assert provenance.origin_start == "2024-07-31"
    assert provenance.origin_end == "2025-06-30"
    assert provenance.target_start == "2025-07"
    assert provenance.target_end == "2026-06"
    assert provenance.extract_id == FROZEN_EXTRACT_ID
    assert provenance.summary_source == "docs/final_eia_holdout_oneshot.json"
    assert provenance.feature_set_id == "eia_commercial_price_v1"
    assert banner.primary_criterion == "FAIL"
    assert banner.interval_coverage == Decimal("0.0")


def test_holdout_rejects_a_swapped_origin_and_a_short_file(tmp_path: Path) -> None:
    swapped = _holdout_frame(with_intervals=False)
    mask = swapped["target_month"].eq("2025-07")
    swapped.loc[mask, "forecast_origin"] = pd.Timestamp("2025-07-31")
    swapped_path = tmp_path / "swapped.parquet"
    swapped.to_parquet(swapped_path, index=False)
    with pytest.raises(DemoDataError, match="will not plot an origin date as a target month"):
        load_holdout_comparison(swapped_path)
    short = _holdout_frame(with_intervals=False).iloc[:-1]
    short_path = tmp_path / "short.parquet"
    short.to_parquet(short_path, index=False)
    with pytest.raises(DemoDataError, match="60 cases"):
        load_holdout_comparison(short_path)
    with pytest.raises(DemoDataError, match="not on this machine"):
        load_holdout_comparison(tmp_path / "absent.parquet")


def test_catalog_has_no_forward_production_forecast() -> None:
    catalog = chart_series_catalog()
    roles = {series.role for series in catalog}
    assert roles == {OBSERVED_ROLE, CLOSED_PREDICTION_ROLE, HYPOTHETICAL_ROLE}
    names = [series.name for series in catalog]
    assert OBSERVED_PRICE_LABEL in names
    assert "production forecast" not in " ".join(names).lower()
    assert HOLDOUT_SECTION_LABEL.endswith("not a forward forecast")
    assert "forward forecast" not in OBSERVED_PRICE_LABEL.lower()
    hypothetical = next(series for series in catalog if series.role == HYPOTHETICAL_ROLE)
    assert hypothetical.time_axis == "scenario"
    assert "model forecast" in hypothetical.name.lower()
    assert "FAIL" in EIA_MODEL_PRICE_WARNING


def test_banner_stays_above_tabs_and_charts_do_not_train() -> None:
    demo = Path(__file__).resolve().parents[1] / "src" / "infralens" / "demo"
    app = (demo / "app.py").read_text(encoding="utf-8")
    views = (demo / "eia_views.py").read_text(encoding="utf-8")
    assert app.index("_render_banner(banner)") < app.index("st.tabs")
    assert "_render_cost_form" in app
    assert "EIA_MODEL_PRICE_WARNING" in app
    assert "@st.cache_data" in app
    assert "mtime_ns" in app
    combined = app + views
    assert "infralens.evaluation" not in combined
    assert "run_final_holdout" not in combined
    assert "httpx" not in combined
    assert "urllib" not in combined


def _write_prices(path: Path) -> None:
    frame = _price_rows().sample(frac=1, random_state=3)
    frame.to_parquet(path, index=False)


def _price_rows() -> pd.DataFrame:
    rows = []
    for index, state_id in enumerate(("MD", "NJ", "OH", "PA", "VA")):
        for period, price in (("2026-05", 10 + index), ("2026-06", 11 + index)):
            rows.append(
                {
                    "period": period,
                    "state_id": state_id,
                    "sector_id": "COM",
                    "price_cents_per_kwh": float(price),
                }
            )
    return pd.DataFrame(rows)


def _write_holdout(path: Path, *, shuffle: bool = False, with_intervals: bool = True) -> None:
    frame = _holdout_frame(with_intervals=with_intervals)
    if shuffle:
        frame = frame.sample(frac=1, random_state=7)
    frame.to_parquet(path, index=False)


def _holdout_frame(*, with_intervals: bool) -> pd.DataFrame:
    origins = {
        "2025-07": "2024-07-31",
        "2025-08": "2024-08-31",
        "2025-09": "2024-09-30",
        "2025-10": "2024-10-31",
        "2025-11": "2024-11-30",
        "2025-12": "2024-12-31",
        "2026-01": "2025-01-31",
        "2026-02": "2025-02-28",
        "2026-03": "2025-03-31",
        "2026-04": "2025-04-30",
        "2026-05": "2025-05-31",
        "2026-06": "2025-06-30",
    }
    rows = []
    for state_id in ("MD", "NJ", "OH", "PA", "VA"):
        for target_month, origin in origins.items():
            if state_id == "VA" and target_month == "2025-07":
                actual, ridge, naive = 10.21, 8.633044, 8.84
                lower, upper = 7.759795, 9.506292
            elif state_id == "VA" and target_month == "2025-08":
                actual, ridge, naive = 9.46, 8.140090, 8.65
                lower, upper = 7.266842, 9.013338
            else:
                actual, ridge, naive = 12.0, 10.0, 11.0
                lower, upper = 9.0, 11.0
            row = {
                "evaluation_stage": "final_holdout",
                "state_id": state_id,
                "forecast_origin": pd.Timestamp(origin),
                "target_month": target_month,
                "actual": actual,
                "ridge_prediction": ridge,
                "seasonal_naive_prediction": naive,
                "skip_reason": None,
            }
            if with_intervals:
                row.update(
                    {
                        "interval_lower": lower,
                        "interval_upper": upper,
                        "interval_status": "interval",
                        "interval_covered": False,
                    }
                )
            rows.append(row)
    return pd.DataFrame(rows)

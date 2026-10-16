"""Foundation tests for the historical demo page. They do not score the holdout."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from infralens.demo.foundation import (
    HOLDOUT_PRICE_LABEL,
    PORTABLE_MODE,
    PROTOTYPE_CAPTION,
    DemoDataError,
    LocalArtifactPaths,
    PriceSource,
    assess_artifacts,
    cost_scenarios,
    default_artifact_paths,
    is_model_derived_price,
    load_holdout_banner,
    load_holdout_quotes,
)
from infralens.finance.annual_cost import EIA_MODEL_PRICE_WARNING, FinanceInputError


def test_committed_summary_is_the_failed_holdout() -> None:
    banner = load_holdout_banner(default_artifact_paths().committed_summary)
    assert banner.primary_criterion == "FAIL"
    assert banner.ridge_mae_cents_per_kwh == Decimal("2.6384726503825626")
    assert banner.paired_baseline_mae_cents_per_kwh == Decimal("2.6136666666666666")
    assert banner.interval_coverage == Decimal("0.0")
    assert banner.feature_set_id == "eia_commercial_price_v1"
    assert banner.evaluation_stage == "final_holdout"
    assert "ee5bcf6" in banner.runner_commit
    assert "forward" not in PROTOTYPE_CAPTION.lower() or "Not a live" in PROTOTYPE_CAPTION


def test_missing_summary_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(DemoDataError, match="missing"):
        load_holdout_banner(tmp_path / "absent.json")


def test_portable_mode_when_cached_files_are_absent(tmp_path: Path) -> None:
    paths = LocalArtifactPaths(
        price_history=tmp_path / "price.parquet",
        holdout_cases=tmp_path / "cases.parquet",
        pjm_2025_tables=tmp_path / "2025.xlsx",
        pjm_2026_tables=tmp_path / "2026.xlsx",
        committed_summary=tmp_path / "summary.json",
    )
    assessment = assess_artifacts(paths)
    assert assessment.mode == PORTABLE_MODE
    assert "Do not rerun the final EIA holdout" in assessment.obtain_sources
    for path in (
        paths.price_history,
        paths.holdout_cases,
        paths.pjm_2025_tables,
        paths.pjm_2026_tables,
    ):
        path.write_bytes(b"")
    assert assess_artifacts(paths).mode == "local_full_data"


def test_typed_prices_match_the_checked_example_without_a_model_warning() -> None:
    rows = cost_scenarios(
        it_capacity_mw=50,
        pue=Decimal("1.30"),
        utilization=Decimal("0.80"),
        operating_hours_per_year=8760,
        baseline_name="baseline",
        scenarios=(
            ("baseline", PriceSource.TYPED_HYPOTHETICAL, 12),
            ("comparison", PriceSource.TYPED_HYPOTHETICAL, 10),
        ),
    )
    by_name = {row.scenario_name: row for row in rows}
    assert by_name["baseline"].annual_consumption_kwh == Decimal("455520000")
    assert by_name["baseline"].annual_electricity_cost_usd == Decimal("54662400")
    assert by_name["comparison"].cost_difference_vs_baseline_usd == Decimal("-9110400")
    assert all(row.model_price_warning is None for row in rows)
    assert is_model_derived_price(PriceSource.TYPED_HYPOTHETICAL) is False


def test_holdout_price_uses_the_frozen_case_and_sets_the_warning(tmp_path: Path) -> None:
    path = tmp_path / "cases.parquet"
    _write_cases(path)
    quotes = load_holdout_quotes(path)
    rows = cost_scenarios(
        it_capacity_mw=50,
        pue=Decimal("1.30"),
        utilization=Decimal("0.80"),
        operating_hours_per_year=8760,
        baseline_name="typed",
        holdout_quotes=quotes,
        scenarios=(
            ("typed", PriceSource.TYPED_HYPOTHETICAL, 12),
            ("ridge", PriceSource.HOLDOUT_RIDGE, ("VA", "2024-07-31", "2025-07")),
        ),
    )
    ridge = rows[1]
    assert ridge.price_cents_per_kwh == Decimal("11.5")
    assert ridge.model_derived_eia_price is True
    assert ridge.model_price_warning == EIA_MODEL_PRICE_WARNING
    assert "FAIL" in EIA_MODEL_PRICE_WARNING
    assert "not a validated investment forecast" in EIA_MODEL_PRICE_WARNING.lower()
    assert is_model_derived_price(PriceSource.HOLDOUT_RIDGE) is True
    assert "Not a forward-looking forecast" in HOLDOUT_PRICE_LABEL


def test_missing_or_unknown_holdout_case_does_not_invent_a_price(tmp_path: Path) -> None:
    with pytest.raises(DemoDataError, match="not on this machine"):
        load_holdout_quotes(tmp_path / "missing.parquet")
    quotes = load_holdout_quotes(_write_cases(tmp_path / "cases.parquet"))
    with pytest.raises(DemoDataError, match="will not invent"):
        cost_scenarios(
            it_capacity_mw=50,
            pue=1,
            utilization=1,
            operating_hours_per_year=8760,
            baseline_name="ridge",
            holdout_quotes=quotes,
            scenarios=(("ridge", PriceSource.HOLDOUT_RIDGE, ("MD", "2024-07-31", "2025-07")),),
        )


def test_invalid_facility_inputs_fail_closed() -> None:
    with pytest.raises(FinanceInputError, match="pue"):
        cost_scenarios(
            it_capacity_mw=50,
            pue=Decimal("0.99"),
            utilization=1,
            operating_hours_per_year=8760,
            baseline_name="baseline",
            scenarios=(("baseline", PriceSource.TYPED_HYPOTHETICAL, 12),),
        )
    with pytest.raises(FinanceInputError, match="it_capacity_mw"):
        cost_scenarios(
            it_capacity_mw=-1,
            pue=1,
            utilization=0,
            operating_hours_per_year=8760,
            baseline_name="baseline",
            scenarios=(("baseline", PriceSource.TYPED_HYPOTHETICAL, 12),),
        )


def test_duplicate_holdout_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "dup.parquet"
    frame = _case_frame()
    pd.concat([frame, frame], ignore_index=True).to_parquet(path, index=False)
    with pytest.raises(DemoDataError, match="Duplicate"):
        load_holdout_quotes(path)


def test_demo_package_does_not_import_evaluation_or_run_the_holdout() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "infralens" / "demo"
    sources = {path.name: path.read_text(encoding="utf-8") for path in root.glob("*.py")}
    combined = "\n".join(sources.values())
    assert "infralens.evaluation" not in combined
    assert "final_holdout" not in sources["app.py"]


def _write_cases(path: Path) -> Path:
    _case_frame().to_parquet(path, index=False)
    return path


def _case_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "evaluation_stage": "final_holdout",
                "state_id": "VA",
                "forecast_origin": pd.Timestamp("2024-07-31"),
                "target_month": "2025-07",
                "actual": 13.25,
                "ridge_prediction": 11.5,
                "seasonal_naive_prediction": 12.0,
                "skip_reason": None,
            }
        ]
    )

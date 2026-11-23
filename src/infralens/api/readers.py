"""Call existing InfraLens functions and map their failures onto API errors.

This module does not reimplement vintage selection, price-history validation,
or the electricity-cost identity.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from infralens.api.errors import ApiError, ArtifactId, safe_detail
from infralens.api.schemas import (
    ArtifactReport,
    EvaluationSummaryResponse,
    FinanceRequest,
    FinanceResponse,
    FinanceScenarioResult,
    HistoryPointOut,
    HistoryResponse,
    HoldoutCaseOut,
    HoldoutCasesResponse,
    HoldoutInterval,
    HoldoutPointOut,
    HoldoutPointProvenance,
    HoldoutResponse,
    HoldoutWindow,
    PjmCatalogResponse,
    PjmScreenResponse,
    SeriesValue,
    StatusResponse,
    StoredSummary,
)
from infralens.data.manifest import default_manifest_path
from infralens.demo.eia_views import (
    DEMO_STATES,
    HISTORY_LIMITATIONS,
    HOLDOUT_SECTION_LABEL,
    MISSING_HOLDOUT_CHART,
    MISSING_PRICE_HISTORY,
    OBSERVED_PRICE_LABEL,
    SUMMARY_SOURCE_LABEL,
    load_holdout_comparison,
    load_price_history,
)
from infralens.demo.foundation import (
    FROZEN_EXTRACT_ID,
    HOLDOUT_PRICE_LABEL,
    LOCAL_FULL_DATA_MODE,
    PORTABLE_MODE,
    PROTOTYPE_CAPTION,
    TYPED_PRICE_LABEL,
    DemoDataError,
    PriceSource,
    assess_artifacts,
    cost_scenarios,
    default_artifact_paths,
    load_holdout_banner,
    load_holdout_quotes,
)
from infralens.demo.pjm_screen import (
    CAGR_PERCENT_LABEL,
    FORECAST_YEARS,
    GEOGRAPHIC_WARNING,
    LARGE_LOAD_WARNING,
    MISSING_WORKBOOKS,
    load_screening_tables,
    manifest_identity,
    present_screening,
    screen_cached_zone,
    workbook_identity,
)
from infralens.finance.annual_cost import EIA_MODEL_PRICE_WARNING, FinanceInputError
from infralens.screening.pjm_adjustments import PjmAdjustmentError
from infralens.screening.pjm_b1 import PjmB1Error
from infralens.screening.pjm_sources import EXPECTED_B1_ZONE_CODES
from infralens.screening.pjm_view import PjmViewError

CLOSED_EVALUATION_LIMITATION = (
    "Closed historical evaluation. Not a validated production forecast "
    "and not an investment recommendation."
)

_FINANCE_FIELDS = (
    "operating_hours_per_year",
    "it_capacity_mw",
    "price_cents_per_kwh",
    "utilization",
    "baseline_name",
    "pue",
)


@dataclass
class Runtime:
    """Process-local PJM parse cache. Validation state starts unvalidated."""

    root: Path
    lock: threading.Lock = field(default_factory=threading.Lock)
    pjm_tables: dict[tuple[object, ...], tuple[object, object, object]] = field(default_factory=dict)
    pjm_file_state: dict[tuple[object, ...], str] = field(default_factory=dict)


def _paths(runtime: Runtime):
    return default_artifact_paths(runtime.root)


def _file_key(artifact_id: str, path: Path) -> tuple[object, ...]:
    return (artifact_id, workbook_identity(path))


def _mark_pjm(runtime: Runtime, artifact_id: str, path: Path, state: str) -> None:
    if not path.is_file():
        return
    runtime.pjm_file_state[_file_key(artifact_id, path)] = state


def status_response(runtime: Runtime) -> StatusResponse:
    paths = _paths(runtime)
    assessment = assess_artifacts(paths)
    mode = assessment.mode
    if mode not in {PORTABLE_MODE, LOCAL_FULL_DATA_MODE}:
        mode = PORTABLE_MODE
    return StatusResponse(
        prototype_caption=PROTOTYPE_CAPTION,
        presence_mode=mode,  # type: ignore[arg-type]
        artifacts=[
            _summary_report(paths.committed_summary),
            _history_report(paths.price_history),
            _cases_report(paths.holdout_cases),
            _pjm_report(runtime, paths.pjm_2025_tables, "pjm_2025_tables"),
            _pjm_report(runtime, paths.pjm_2026_tables, "pjm_2026_tables"),
        ],
    )


def _checked_report(artifact_id: ArtifactId, path: Path, loader) -> ArtifactReport:
    if not path.is_file():
        return ArtifactReport(
            artifact_id=artifact_id,
            status="missing",
            validation="not_applicable",
        )
    try:
        loader()
    except ApiError as exc:
        return ArtifactReport(
            artifact_id=artifact_id,
            status="invalid",
            validation="failed",
            detail=safe_detail(exc),
        )
    except DemoDataError as exc:
        return ArtifactReport(
            artifact_id=artifact_id,
            status="invalid",
            validation="failed",
            detail=safe_detail(exc),
        )
    except Exception:
        return ArtifactReport(
            artifact_id=artifact_id,
            status="invalid",
            validation="failed",
            detail=None,
        )
    return ArtifactReport(
        artifact_id=artifact_id,
        status="valid",
        validation="validated",
    )


def _summary_report(path: Path) -> ArtifactReport:
    def load() -> None:
        read_evaluation(path)

    return _checked_report("committed_summary", path, load)


def _history_report(path: Path) -> ArtifactReport:
    def load() -> None:
        load_price_history(path, extract_id=FROZEN_EXTRACT_ID)

    return _checked_report("price_history", path, load)


def _cases_report(path: Path) -> ArtifactReport:
    def load() -> None:
        load_holdout_comparison(path)

    return _checked_report("holdout_cases", path, load)


def _pjm_report(runtime: Runtime, path: Path, artifact_id: str) -> ArtifactReport:
    if not path.is_file():
        return ArtifactReport(
            artifact_id=artifact_id,  # type: ignore[arg-type]
            status="missing",
            validation="not_applicable",
        )
    state = runtime.pjm_file_state.get(_file_key(artifact_id, path))
    if state == "valid":
        return ArtifactReport(
            artifact_id=artifact_id,  # type: ignore[arg-type]
            status="valid",
            validation="validated",
        )
    if state == "invalid":
        return ArtifactReport(
            artifact_id=artifact_id,  # type: ignore[arg-type]
            status="invalid",
            validation="failed",
            detail="The PJM workbook failed validation.",
        )
    return ArtifactReport(
        artifact_id=artifact_id,  # type: ignore[arg-type]
        status="present_unvalidated",
        validation="deferred",
        detail="Workbook validation runs when a zone-year screen is requested.",
    )


def read_evaluation(path: Path) -> EvaluationSummaryResponse:
    """Read the committed JSON. Improvement and threshold stay the stored values."""

    if not path.is_file():
        raise ApiError(
            404,
            "artifact_missing",
            "The committed holdout summary is not available.",
            artifact_id="committed_summary",
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        load_holdout_banner(path)
        summary = document["summary"]
        return EvaluationSummaryResponse(
            source_label=SUMMARY_SOURCE_LABEL,
            limitations=CLOSED_EVALUATION_LIMITATION,
            executed_on=str(document["executed_on"]),
            runner_commit=str(document["runner_commit"]),
            label=str(document["label"]),
            note=str(document["note"]),
            python=str(document["python"]),
            architecture=str(document["architecture"]),
            environment=str(document["environment"]),
            source_cases=str(document["source_cases"]),
            source_summary=str(document["source_summary"]),
            selected_alpha_by_origin=document["selected_alpha_by_origin"],
            selected_alpha_origin_counts={
                str(key): int(value)
                for key, value in document["selected_alpha_origin_counts"].items()
            },
            summary=StoredSummary.model_validate(summary),
        )
    except ApiError:
        raise
    except (DemoDataError, json.JSONDecodeError, KeyError, TypeError, ValidationError, ValueError) as exc:
        raise ApiError(
            500,
            "artifact_invalid",
            safe_detail(exc) or "Committed holdout summary is incomplete.",
            artifact_id="committed_summary",
        ) from exc


def read_history(runtime: Runtime, state_id: str | None) -> HistoryResponse:
    path = _paths(runtime).price_history
    if not path.is_file():
        raise ApiError(
            404,
            "artifact_missing",
            MISSING_PRICE_HISTORY,
            artifact_id="price_history",
        )
    try:
        history = load_price_history(path, extract_id=FROZEN_EXTRACT_ID)
    except DemoDataError as exc:
        raise ApiError(
            500,
            "artifact_invalid",
            safe_detail(exc) or "Price history failed validation.",
            artifact_id="price_history",
        ) from exc
    except Exception as exc:
        raise ApiError(
            500,
            "artifact_invalid",
            "Price history failed validation.",
            artifact_id="price_history",
        ) from exc
    if state_id is not None and state_id not in DEMO_STATES:
        raise ApiError(
            422,
            "validation_error",
            f"Unknown state {state_id}.",
            field="state_id",
        )
    selected = [
        point
        for point in history.points
        if state_id is None or point.state_id == state_id
    ]
    periods = [point.period for point in selected]
    return HistoryResponse(
        state_id=state_id,
        extract_id=history.extract_id,
        retrieved_at=history.retrieved_at,
        source_name=history.source_name,
        recorded_price_units=history.price_units,
        earliest_period=periods[0] if periods else history.earliest_period,
        latest_period=periods[-1] if periods else history.latest_period,
        extract_row_count=history.row_count,
        returned_row_count=len(selected),
        limitations=history.limitations or HISTORY_LIMITATIONS,
        series_name=OBSERVED_PRICE_LABEL,
        points=[
            HistoryPointOut(
                state_id=point.state_id,
                period=point.period,
                observed_price_cents_per_kwh=point.observed_price_cents_per_kwh,
            )
            for point in selected
        ],
    )


def read_holdout(runtime: Runtime, state_id: str | None) -> HoldoutResponse:
    paths = _paths(runtime)
    if not paths.holdout_cases.is_file():
        raise ApiError(
            404,
            "artifact_missing",
            MISSING_HOLDOUT_CHART,
            artifact_id="holdout_cases",
        )
    try:
        comparison = load_holdout_comparison(paths.holdout_cases)
    except DemoDataError as exc:
        raise ApiError(
            500,
            "artifact_invalid",
            safe_detail(exc) or "The holdout case file failed validation.",
            artifact_id="holdout_cases",
        ) from exc
    except Exception as exc:
        raise ApiError(
            500,
            "artifact_invalid",
            "The holdout case file failed validation.",
            artifact_id="holdout_cases",
        ) from exc
    if state_id is not None and state_id not in DEMO_STATES:
        raise ApiError(
            422,
            "validation_error",
            f"Unknown state {state_id}.",
            field="state_id",
        )
    banner = _banner_or_none(paths.committed_summary)
    selected = [
        point
        for point in comparison.points
        if state_id is None or point.state_id == state_id
    ]
    return HoldoutResponse(
        state_id=state_id,
        limitations=HOLDOUT_SECTION_LABEL,
        returned_row_count=len(selected),
        window=HoldoutWindow(
            origin_start=comparison.origin_start,
            origin_end=comparison.origin_end,
            target_start=comparison.target_start,
            target_end=comparison.target_end,
            extract_id=None if banner is None else banner.extract_id,
            feature_set_id=None if banner is None else banner.feature_set_id,
            evaluation_stage=None if banner is None else banner.evaluation_stage,
            summary_source=None if banner is None else SUMMARY_SOURCE_LABEL,
            interval_warning=comparison.interval_warning,
            empirical_interval_coverage=comparison.empirical_interval_coverage,
        ),
        points=[
            HoldoutPointOut(
                state_id=point.state_id,
                target_month=point.target_month,
                actual=SeriesValue(
                    cents_per_kwh=point.actual_cents_per_kwh,
                    role="observed",
                ),
                ridge=SeriesValue(
                    cents_per_kwh=point.ridge_prediction_cents_per_kwh,
                    role="closed_prediction",
                ),
                seasonal_naive=SeriesValue(
                    cents_per_kwh=point.seasonal_naive_prediction_cents_per_kwh,
                    role="closed_prediction",
                ),
                interval=HoldoutInterval(
                    lower_cents_per_kwh=point.interval_lower_cents_per_kwh,
                    upper_cents_per_kwh=point.interval_upper_cents_per_kwh,
                    covered=point.interval_covered,
                ),
                provenance=HoldoutPointProvenance(forecast_origin=point.forecast_origin),
            )
            for point in selected
        ],
    )


def read_cases(runtime: Runtime) -> HoldoutCasesResponse:
    path = _paths(runtime).holdout_cases
    if not path.is_file():
        raise ApiError(
            404,
            "artifact_missing",
            "Frozen holdout cases are not available. A Ridge price cannot be supplied in their place.",
            artifact_id="holdout_cases",
        )
    try:
        quotes = load_holdout_quotes(path)
    except DemoDataError as exc:
        message = safe_detail(exc) or "The holdout case file failed validation."
        code_status = 404 if "not on this machine" in str(exc) else 500
        raise ApiError(
            code_status,
            "artifact_missing" if code_status == 404 else "artifact_invalid",
            message,
            artifact_id="holdout_cases",
        ) from exc
    except Exception as exc:
        raise ApiError(
            500,
            "artifact_invalid",
            "The holdout case file failed validation.",
            artifact_id="holdout_cases",
        ) from exc
    return HoldoutCasesResponse(
        limitations=CLOSED_EVALUATION_LIMITATION,
        row_count=len(quotes),
        cases=[
            HoldoutCaseOut(
                state_id=quote.state_id,
                forecast_origin=quote.forecast_origin,
                target_month=quote.target_month,
                ridge_prediction_cents_per_kwh=quote.ridge_prediction_cents_per_kwh,
                actual_cents_per_kwh=quote.actual_cents_per_kwh,
                seasonal_naive_prediction_cents_per_kwh=quote.seasonal_naive_prediction_cents_per_kwh,
            )
            for quote in quotes
        ],
    )


def _banner_or_none(path: Path):
    if not path.is_file():
        return None
    try:
        return load_holdout_banner(path)
    except DemoDataError:
        return None


def price_scenarios(runtime: Runtime, request: FinanceRequest) -> FinanceResponse:
    scenarios: list[tuple[str, str, object]] = []
    needs_cases = False
    for scenario in request.scenarios:
        if scenario.source == PriceSource.TYPED_HYPOTHETICAL:
            if scenario.case_key is not None:
                raise ApiError(
                    422,
                    "validation_error",
                    "A typed price does not take a holdout case key.",
                    field="case_key",
                )
            if scenario.price_cents_per_kwh is None:
                raise ApiError(
                    422,
                    "validation_error",
                    "A typed scenario needs price_cents_per_kwh.",
                    field="price_cents_per_kwh",
                )
            scenarios.append((scenario.name, scenario.source, scenario.price_cents_per_kwh))
            continue
        if scenario.price_cents_per_kwh is not None:
            raise ApiError(
                422,
                "validation_error",
                "A holdout Ridge scenario cannot include a client-supplied price.",
                field="price_cents_per_kwh",
            )
        if scenario.case_key is None:
            raise ApiError(
                422,
                "validation_error",
                "A holdout Ridge scenario needs a frozen case key.",
                field="case_key",
            )
        key = scenario.case_key
        scenarios.append(
            (
                scenario.name,
                scenario.source,
                (key.state_id, key.forecast_origin, key.target_month),
            )
        )
        needs_cases = True

    quotes: tuple = ()
    if needs_cases:
        path = _paths(runtime).holdout_cases
        if not path.is_file():
            raise ApiError(
                404,
                "artifact_missing",
                "Frozen holdout cases are not available. A Ridge price cannot be supplied in their place.",
                artifact_id="holdout_cases",
            )
        try:
            quotes = load_holdout_quotes(path)
        except DemoDataError as exc:
            raise ApiError(
                500,
                "artifact_invalid",
                safe_detail(exc) or "The holdout case file failed validation.",
                artifact_id="holdout_cases",
            ) from exc

    try:
        rows = cost_scenarios(
            it_capacity_mw=request.it_capacity_mw,
            pue=request.pue,
            utilization=request.utilization,
            operating_hours_per_year=request.operating_hours_per_year,
            scenarios=tuple(scenarios),
            baseline_name=request.baseline_name,
            holdout_quotes=quotes,
        )
    except FinanceInputError as exc:
        message = safe_detail(exc) or "A finance input is not valid."
        raise ApiError(
            422,
            "validation_error",
            message,
            field=_finance_field(message),
        ) from exc
    except DemoDataError as exc:
        message = safe_detail(exc) or "That holdout case is not in the frozen file."
        raise ApiError(422, "validation_error", message, field="case_key") from exc

    sources = [scenario.source for scenario in request.scenarios]
    results = [
        FinanceScenarioResult(
            scenario_name=row.scenario_name,
            price_source=source,  # type: ignore[arg-type]
            price_label=HOLDOUT_PRICE_LABEL if row.model_derived_eia_price else TYPED_PRICE_LABEL,
            it_capacity_mw=row.it_capacity_mw,
            pue=row.pue,
            utilization=row.utilization,
            operating_hours_per_year=row.operating_hours_per_year,
            facility_average_demand_mw=row.facility_average_demand_mw,
            facility_average_demand_unit=row.facility_average_demand_unit,
            annual_consumption_kwh=row.annual_consumption_kwh,
            annual_consumption_unit=row.annual_consumption_unit,
            price_cents_per_kwh=row.price_cents_per_kwh,
            price_unit=row.price_unit,
            annual_electricity_cost_usd=row.annual_electricity_cost_usd,
            annual_electricity_cost_unit=row.annual_electricity_cost_unit,
            baseline_scenario_name=row.baseline_scenario_name or request.baseline_name,
            cost_difference_vs_baseline_usd=(
                Decimal("0")
                if row.cost_difference_vs_baseline_usd is None
                else row.cost_difference_vs_baseline_usd
            ),
            cost_difference_unit=row.cost_difference_unit,
            model_derived_eia_price=row.model_derived_eia_price,
            model_price_warning=row.model_price_warning,
        )
        for row, source in zip(rows, sources, strict=True)
    ]
    derived = any(row.model_derived_eia_price for row in results)
    return FinanceResponse(
        closed_holdout_claim_boundary="closed_historical_evaluation" if derived else None,
        closed_holdout_limitation=EIA_MODEL_PRICE_WARNING if derived else None,
        scenarios=results,
    )


def _finance_field(message: str) -> str | None:
    if "scenario name" in message:
        return "scenario_name"
    for name in _FINANCE_FIELDS:
        if name in message:
            return name
    if "Baseline" in message or "baseline" in message:
        return "baseline_name"
    if "scenario" in message:
        return "scenarios"
    return None


def pjm_catalog() -> PjmCatalogResponse:
    years = list(FORECAST_YEARS)
    return PjmCatalogResponse(
        zones=list(EXPECTED_B1_ZONE_CODES),
        forecast_year_min=years[0],
        forecast_year_max=years[-1],
        forecast_years=years,
        geographic_warning=GEOGRAPHIC_WARNING,
        large_load_warning=LARGE_LOAD_WARNING,
    )


def pjm_screen(
    runtime: Runtime,
    pjm_zone: str,
    forecast_year: int,
    as_of: date,
) -> PjmScreenResponse:
    if pjm_zone not in EXPECTED_B1_ZONE_CODES:
        raise ApiError(
            422,
            "validation_error",
            f"Unknown PJM zone {pjm_zone}.",
            field="pjm_zone",
        )
    if forecast_year not in FORECAST_YEARS:
        raise ApiError(
            422,
            "validation_error",
            "forecast_year is outside the screening range.",
            field="forecast_year",
        )
    paths = _paths(runtime)
    b1_rows, adjustment_rows, retrieval = _load_pjm(runtime, paths)
    try:
        result = screen_cached_zone(
            b1_rows,
            adjustment_rows,
            pjm_zone,
            forecast_year,
            as_of,
        )
    except PjmViewError as exc:
        raise ApiError(
            409,
            "malformed_vintage",
            safe_detail(exc)
            or "This published vintage is incomplete or contradictory. An older vintage is not substituted.",
            field="as_of",
        ) from exc
    except DemoDataError as exc:
        raise ApiError(
            422,
            "validation_error",
            safe_detail(exc) or "The zone-year request is not valid.",
            field="pjm_zone",
        ) from exc
    shown = present_screening(result, retrieval.note)
    return PjmScreenResponse(
        available=shown.available,
        pjm_zone=shown.pjm_zone,
        forecast_year=shown.forecast_year,
        as_of_date=shown.as_of_date.isoformat(),
        ltlf_vintage_year=shown.ltlf_vintage_year,
        summer_peak_mw=shown.summer_peak_mw,
        summer_peak_10yr_cagr=shown.summer_peak_10yr_cagr,
        cagr_percent_per_year=shown.cagr_percent_per_year,
        cagr_percent_label=CAGR_PERCENT_LABEL,
        above_embedded_mw=shown.above_embedded_mw,
        total_associated_mw=shown.total_associated_mw,
        original_release_date=_iso_date(shown.original_release_date),
        revision_date=_iso_date(shown.revision_date),
        vintage_available_at=_iso_date(shown.vintage_available_at),
        source_tables=list(shown.source_tables),
        source_files=list(shown.source_files),
        source_urls=list(shown.source_urls),
        retrieved_at=list(shown.retrieved_at),
        retrieval_note=shown.retrieval_note,
        unavailable_reason=shown.unavailable_reason,
        geographic_warning=shown.geographic_warning,
        large_load_warning=shown.large_load_warning,
    )


def _iso_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _load_pjm(runtime: Runtime, paths):
    missing = _missing_workbook(paths)
    if missing is not None:
        raise ApiError(
            404,
            "artifact_missing",
            MISSING_WORKBOOKS,
            artifact_id=missing,
        )
    manifest_path = default_manifest_path(runtime.root)
    identity = (
        _file_key("pjm_2025_tables", paths.pjm_2025_tables),
        _file_key("pjm_2026_tables", paths.pjm_2026_tables),
        ("manifest", manifest_identity(manifest_path)),
    )
    with runtime.lock:
        cached = runtime.pjm_tables.get(identity)
    if cached is not None:
        return cached
    try:
        loaded = load_screening_tables(paths.pjm_2025_tables.parent, manifest_path=manifest_path)
    except DemoDataError as exc:
        _remember_pjm_failure(runtime, paths)
        if "not on this machine" in str(exc):
            raise ApiError(
                404,
                "artifact_missing",
                MISSING_WORKBOOKS,
                artifact_id=_missing_workbook(paths) or "pjm_2025_tables",
            ) from exc
        raise ApiError(
            500,
            "artifact_invalid",
            safe_detail(exc) or "The PJM workbook failed validation.",
            artifact_id="pjm_2025_tables",
        ) from exc
    except (PjmB1Error, PjmAdjustmentError) as exc:
        _remember_pjm_failure(runtime, paths)
        raise ApiError(
            500,
            "artifact_invalid",
            "The PJM workbook failed validation.",
            artifact_id="pjm_2025_tables",
        ) from exc
    with runtime.lock:
        runtime.pjm_tables[identity] = loaded  # type: ignore[assignment]
        _mark_pjm(runtime, "pjm_2025_tables", paths.pjm_2025_tables, "valid")
        _mark_pjm(runtime, "pjm_2026_tables", paths.pjm_2026_tables, "valid")
    return loaded


def _remember_pjm_failure(runtime: Runtime, paths) -> None:
    with runtime.lock:
        _mark_pjm(runtime, "pjm_2025_tables", paths.pjm_2025_tables, "invalid")
        _mark_pjm(runtime, "pjm_2026_tables", paths.pjm_2026_tables, "invalid")


def _missing_workbook(paths) -> str | None:
    if not paths.pjm_2025_tables.is_file():
        return "pjm_2025_tables"
    if not paths.pjm_2026_tables.is_file():
        return "pjm_2026_tables"
    return None

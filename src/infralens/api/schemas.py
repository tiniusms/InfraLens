"""Response and request contracts for the read-only API.

Decimal amounts are JSON strings so a client does not parse them as binary floats.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

ClaimBoundary = Literal[
    "observed_history",
    "closed_historical_evaluation",
    "hypothetical_energy_cost",
    "pjm_zonal_planning",
]


def stored_decimal_text(value: Decimal) -> str:
    """Keep the scale produced by an exact Decimal, including trailing zeros."""

    return format(value, "f")


def shortest_decimal_text(value: Decimal) -> str:
    """Serialize a calculated Decimal without trailing zeros."""

    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-", "-0"}:
        return "0"
    return text


StoredDecimal = Annotated[
    Decimal,
    PlainSerializer(stored_decimal_text, return_type=str, when_used="json"),
]
ShortDecimal = Annotated[
    Decimal,
    PlainSerializer(shortest_decimal_text, return_type=str, when_used="json"),
]


class ErrorResponse(BaseModel):
    """One failure. ``artifact_id`` is a role name, never a filesystem path."""

    code: Literal[
        "artifact_missing",
        "validation_error",
        "malformed_vintage",
        "artifact_invalid",
    ]
    message: str
    artifact_id: Literal[
        "committed_summary",
        "price_history",
        "holdout_cases",
        "pjm_2025_tables",
        "pjm_2026_tables",
    ] | None = None
    field: str | None = None


class ArtifactReport(BaseModel):
    """Presence and validation are separate. A file on disk may still be unvalidated."""

    artifact_id: Literal[
        "committed_summary",
        "price_history",
        "holdout_cases",
        "pjm_2025_tables",
        "pjm_2026_tables",
    ]
    status: Literal["missing", "present_unvalidated", "valid", "invalid"]
    validation: Literal["not_applicable", "deferred", "validated", "failed"]
    detail: str | None = None


class StatusResponse(BaseModel):
    """Operational metadata. It is not an evaluation claim."""

    claim_boundary: None = None
    prototype_caption: str
    presence_mode: Literal["portable_summary", "local_full_data"]
    presence_mode_meaning: Literal["file_existence_only"] = "file_existence_only"
    artifacts: list[ArtifactReport]


class EvaluationUnits(BaseModel):
    mae: Literal["cents/kWh"] = "cents/kWh"
    mae_difference: Literal["cents/kWh"] = "cents/kWh"
    improvement: Literal["percent"] = "percent"
    threshold: Literal["percent"] = "percent"
    interval_coverage: Literal["share"] = "share"
    interval_width: Literal["cents/kWh"] = "cents/kWh"


class StateMae(BaseModel):
    n_scored: int
    paired_baseline_mae: StoredDecimal
    ridge_mae: StoredDecimal


class StateInterval(BaseModel):
    coverage: StoredDecimal
    mean_width: StoredDecimal
    n_intervals: int


class SkipCounts(BaseModel):
    feature_gap: int
    insufficient_train: int
    missing_actual: int
    no_analog: int


class MaeByState(BaseModel):
    MD: StateMae
    NJ: StateMae
    OH: StateMae
    PA: StateMae
    VA: StateMae


class IntervalByState(BaseModel):
    MD: StateInterval
    NJ: StateInterval
    OH: StateInterval
    PA: StateInterval
    VA: StateInterval


class StoredSummary(BaseModel):
    """Fields copied from the committed summary object. Nothing here is recomputed."""

    attempted: int
    evaluation_stage: str
    extract_id: str
    feature_set_id: str
    git_commit: str
    interval_by_state: IntervalByState
    interval_coverage: StoredDecimal
    mae_by_state: MaeByState
    mae_difference: StoredDecimal
    mae_improvement_percent: StoredDecimal
    mae_improvement_ratio: StoredDecimal
    mean_interval_width: StoredDecimal
    min_calibration_residuals: int
    n_insufficient_residual_history: int
    n_intervals: int
    nominal_interval_coverage: StoredDecimal
    paired_baseline_mae: StoredDecimal
    primary_criterion: str
    primary_threshold_percent: int
    primary_threshold_ratio: StoredDecimal
    ridge_mae: StoredDecimal
    scored_paired: int
    skip_counts: SkipCounts


class EvaluationSummaryResponse(BaseModel):
    claim_boundary: Literal["closed_historical_evaluation"] = "closed_historical_evaluation"
    source_label: str
    limitations: str
    units: EvaluationUnits = Field(default_factory=EvaluationUnits)
    executed_on: str
    runner_commit: str
    label: str
    note: str
    python: str
    architecture: str
    environment: str
    source_cases: str
    source_summary: str
    selected_alpha_by_origin: dict[str, StoredDecimal]
    selected_alpha_origin_counts: dict[str, int]
    summary: StoredSummary


class HistoryPointOut(BaseModel):
    state_id: str
    period: str
    observed_price_cents_per_kwh: StoredDecimal
    unit: Literal["cents/kWh"] = "cents/kWh"
    role: Literal["observed"] = "observed"


class HistoryResponse(BaseModel):
    claim_boundary: Literal["observed_history"] = "observed_history"
    state_id: str | None
    extract_id: str
    retrieved_at: str | None
    source_name: str | None
    recorded_price_units: str | None
    unit: Literal["cents/kWh"] = "cents/kWh"
    earliest_period: str
    latest_period: str
    extract_row_count: int
    returned_row_count: int
    limitations: str
    series_name: str
    points: list[HistoryPointOut]


class SeriesValue(BaseModel):
    cents_per_kwh: StoredDecimal
    unit: Literal["cents/kWh"] = "cents/kWh"
    role: Literal["observed", "closed_prediction"]


class HoldoutInterval(BaseModel):
    lower_cents_per_kwh: StoredDecimal | None
    upper_cents_per_kwh: StoredDecimal | None
    covered: bool | None
    unit: Literal["cents/kWh"] = "cents/kWh"


class HoldoutPointProvenance(BaseModel):
    forecast_origin: str


class HoldoutPointOut(BaseModel):
    state_id: str
    target_month: str
    actual: SeriesValue
    ridge: SeriesValue
    seasonal_naive: SeriesValue
    interval: HoldoutInterval
    provenance: HoldoutPointProvenance


class HoldoutWindow(BaseModel):
    axis: Literal["target_month"] = "target_month"
    origin_start: str
    origin_end: str
    target_start: str
    target_end: str
    extract_id: str | None
    feature_set_id: str | None
    evaluation_stage: str | None
    summary_source: str | None
    interval_warning: str | None
    empirical_interval_coverage: StoredDecimal | None
    empirical_interval_coverage_unit: Literal["share"] = "share"


class HoldoutResponse(BaseModel):
    claim_boundary: Literal["closed_historical_evaluation"] = "closed_historical_evaluation"
    state_id: str | None
    limitations: str
    window: HoldoutWindow
    returned_row_count: int
    points: list[HoldoutPointOut]


class HoldoutCaseOut(BaseModel):
    state_id: str
    forecast_origin: str
    target_month: str
    ridge_prediction_cents_per_kwh: StoredDecimal
    actual_cents_per_kwh: StoredDecimal
    seasonal_naive_prediction_cents_per_kwh: StoredDecimal
    unit: Literal["cents/kWh"] = "cents/kWh"
    ridge_role: Literal["closed_prediction"] = "closed_prediction"
    actual_role: Literal["observed"] = "observed"


class HoldoutCasesResponse(BaseModel):
    claim_boundary: Literal["closed_historical_evaluation"] = "closed_historical_evaluation"
    limitations: str
    unit: Literal["cents/kWh"] = "cents/kWh"
    row_count: int
    cases: list[HoldoutCaseOut]


class HoldoutCaseKey(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    state_id: str
    forecast_origin: str
    target_month: str


class FinanceScenarioInput(BaseModel):
    """A typed price is hypothetical. A Ridge scenario sends a case key and no price."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    source: Literal["typed_hypothetical", "holdout_ridge"]
    price_cents_per_kwh: str | None = None
    case_key: HoldoutCaseKey | None = None


class FinanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    it_capacity_mw: str
    pue: str
    utilization: str
    operating_hours_per_year: str = "8760"
    baseline_name: str
    scenarios: list[FinanceScenarioInput] = Field(min_length=1)


class FinanceScenarioResult(BaseModel):
    scenario_name: str
    price_source: Literal["typed_hypothetical", "holdout_ridge"]
    price_label: str
    claim_boundary: Literal["hypothetical_energy_cost"] = "hypothetical_energy_cost"
    it_capacity_mw: ShortDecimal
    pue: ShortDecimal
    utilization: ShortDecimal
    operating_hours_per_year: ShortDecimal
    facility_average_demand_mw: ShortDecimal
    facility_average_demand_unit: str
    annual_consumption_kwh: ShortDecimal
    annual_consumption_unit: str
    price_cents_per_kwh: ShortDecimal
    price_unit: str
    annual_electricity_cost_usd: ShortDecimal
    annual_electricity_cost_unit: str
    baseline_scenario_name: str
    cost_difference_vs_baseline_usd: ShortDecimal
    cost_difference_unit: str
    model_derived_eia_price: bool
    model_price_warning: str | None


class FinanceResponse(BaseModel):
    claim_boundary: Literal["hypothetical_energy_cost"] = "hypothetical_energy_cost"
    closed_holdout_claim_boundary: Literal["closed_historical_evaluation"] | None
    closed_holdout_limitation: str | None
    scenarios: list[FinanceScenarioResult]


class PjmCatalogResponse(BaseModel):
    claim_boundary: Literal["pjm_zonal_planning"] = "pjm_zonal_planning"
    zones: list[str]
    forecast_year_min: int
    forecast_year_max: int
    forecast_years: list[int]
    geographic_warning: str
    large_load_warning: str
    measure_unit: Literal["MW"] = "MW"
    cagr_unit: Literal["decimal_per_year"] = "decimal_per_year"


class PjmScreenResponse(BaseModel):
    claim_boundary: Literal["pjm_zonal_planning"] = "pjm_zonal_planning"
    available: bool
    pjm_zone: str
    forecast_year: int
    as_of_date: str
    ltlf_vintage_year: int | None
    summer_peak_mw: float | None
    summer_peak_10yr_cagr: float | None
    cagr_percent_per_year: float | None
    cagr_percent_label: str
    above_embedded_mw: float | None
    total_associated_mw: float | None
    original_release_date: str | None
    revision_date: str | None
    vintage_available_at: str | None
    source_tables: list[str]
    source_files: list[str]
    source_urls: list[str]
    retrieved_at: list[str]
    retrieval_note: str
    unavailable_reason: str | None
    geographic_warning: str
    large_load_warning: str
    measure_unit: Literal["MW"] = "MW"
    cagr_unit: Literal["decimal_per_year"] = "decimal_per_year"

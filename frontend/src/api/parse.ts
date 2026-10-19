import type {
  ArtifactId,
  ArtifactReport,
  ArtifactStatus,
  ArtifactValidation,
  ErrorCode,
  ErrorResponse,
  EvaluationSummary,
  FinanceResponse,
  FinanceScenarioResult,
  HistoryPoint,
  HistoryResponse,
  HoldoutCase,
  HoldoutCasesResponse,
  HoldoutPoint,
  HoldoutResponse,
  SeriesValue,
  StateMae,
  StatusResponse,
} from "./types";
import { isDecimalString } from "../lib/format";

const ARTIFACT_IDS: readonly ArtifactId[] = [
  "committed_summary",
  "price_history",
  "holdout_cases",
  "pjm_2025_tables",
  "pjm_2026_tables",
];

const STATUSES: readonly ArtifactStatus[] = [
  "missing",
  "present_unvalidated",
  "valid",
  "invalid",
];

const VALIDATIONS: readonly ArtifactValidation[] = [
  "not_applicable",
  "deferred",
  "validated",
  "failed",
];

const ERROR_CODES: readonly ErrorCode[] = [
  "artifact_missing",
  "validation_error",
  "malformed_vintage",
  "artifact_invalid",
];

export class ContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContractError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new ContractError(`Missing string field ${key}.`);
  }
  return value;
}

function decimalField(record: Record<string, unknown>, key: string): string {
  const value = requiredString(record, key);
  if (!isDecimalString(value)) {
    throw new ContractError(`Field ${key} is not a decimal string.`);
  }
  return value;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], label: string): T {
  if (typeof value === "string" && allowed.includes(value as T)) {
    return value as T;
  }
  throw new ContractError(`Unexpected ${label}.`);
}

export function parseErrorResponse(value: unknown): ErrorResponse | null {
  if (!isRecord(value) || typeof value.code !== "string" || typeof value.message !== "string") {
    return null;
  }
  if (!ERROR_CODES.includes(value.code as ErrorCode)) {
    return null;
  }
  const artifact = value.artifact_id;
  const artifactId =
    artifact === null || artifact === undefined
      ? null
      : oneOf(artifact, ARTIFACT_IDS, "artifact_id");
  const field = value.field;
  if (field !== null && field !== undefined && typeof field !== "string") {
    return null;
  }
  return {
    code: value.code as ErrorCode,
    message: value.message,
    artifact_id: artifactId,
    field: typeof field === "string" ? field : null,
  };
}

function parseArtifact(value: unknown): ArtifactReport {
  if (!isRecord(value)) {
    throw new ContractError("Artifact report is not an object.");
  }
  const detail = value.detail;
  if (detail !== null && detail !== undefined && typeof detail !== "string") {
    throw new ContractError("Artifact detail is not text.");
  }
  return {
    artifact_id: oneOf(value.artifact_id, ARTIFACT_IDS, "artifact_id"),
    status: oneOf(value.status, STATUSES, "status"),
    validation: oneOf(value.validation, VALIDATIONS, "validation"),
    detail: typeof detail === "string" ? detail : null,
  };
}

export function parseStatus(value: unknown): StatusResponse {
  if (!isRecord(value)) {
    throw new ContractError("Status response is not an object.");
  }
  if (value.claim_boundary !== null) {
    throw new ContractError("Status claim_boundary must be null.");
  }
  if (value.presence_mode_meaning !== "file_existence_only") {
    throw new ContractError("Status presence meaning is not file existence.");
  }
  if (!Array.isArray(value.artifacts)) {
    throw new ContractError("Status artifacts are missing.");
  }
  const mode = value.presence_mode;
  if (mode !== "portable_summary" && mode !== "local_full_data") {
    throw new ContractError("Unexpected presence mode.");
  }
  return {
    claim_boundary: null,
    prototype_caption: requiredString(value, "prototype_caption"),
    presence_mode: mode,
    presence_mode_meaning: "file_existence_only",
    artifacts: value.artifacts.map(parseArtifact),
  };
}

function parseStateMae(value: unknown): StateMae {
  if (!isRecord(value)) {
    throw new ContractError("State MAE is not an object.");
  }
  if (typeof value.n_scored !== "number" || !Number.isInteger(value.n_scored)) {
    throw new ContractError("State n_scored is not an integer.");
  }
  return {
    n_scored: value.n_scored,
    paired_baseline_mae: decimalField(value, "paired_baseline_mae"),
    ridge_mae: decimalField(value, "ridge_mae"),
  };
}

export function parseEvaluationSummary(value: unknown): EvaluationSummary {
  if (!isRecord(value) || !isRecord(value.summary) || !isRecord(value.units)) {
    throw new ContractError("Evaluation summary is incomplete.");
  }
  if (value.claim_boundary !== "closed_historical_evaluation") {
    throw new ContractError("Unexpected evaluation claim boundary.");
  }
  const units = value.units;
  if (
    units.mae !== "cents/kWh" ||
    units.improvement !== "percent" ||
    units.threshold !== "percent" ||
    units.interval_coverage !== "share"
  ) {
    throw new ContractError("Unexpected evaluation units.");
  }
  const summary = value.summary;
  if (!isRecord(summary.mae_by_state)) {
    throw new ContractError("State MAE table is missing.");
  }
  if (
    typeof summary.primary_threshold_percent !== "number" ||
    !Number.isInteger(summary.primary_threshold_percent)
  ) {
    throw new ContractError("Primary threshold is not an integer.");
  }
  const maeByState = {
    MD: parseStateMae(summary.mae_by_state.MD),
    NJ: parseStateMae(summary.mae_by_state.NJ),
    OH: parseStateMae(summary.mae_by_state.OH),
    PA: parseStateMae(summary.mae_by_state.PA),
    VA: parseStateMae(summary.mae_by_state.VA),
  };
  return {
    claim_boundary: "closed_historical_evaluation",
    source_label: requiredString(value, "source_label"),
    limitations: requiredString(value, "limitations"),
    units: {
      mae: "cents/kWh",
      improvement: "percent",
      threshold: "percent",
      interval_coverage: "share",
    },
    executed_on: requiredString(value, "executed_on"),
    runner_commit: requiredString(value, "runner_commit"),
    summary: {
      primary_criterion: requiredString(summary, "primary_criterion"),
      ridge_mae: decimalField(summary, "ridge_mae"),
      paired_baseline_mae: decimalField(summary, "paired_baseline_mae"),
      mae_improvement_percent: decimalField(summary, "mae_improvement_percent"),
      primary_threshold_percent: summary.primary_threshold_percent,
      primary_threshold_ratio: decimalField(summary, "primary_threshold_ratio"),
      interval_coverage: decimalField(summary, "interval_coverage"),
      nominal_interval_coverage: decimalField(summary, "nominal_interval_coverage"),
      mae_by_state: maeByState,
    },
  };
}

const MONTH = /^\d{4}-\d{2}$/;

function integerField(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new ContractError(`Field ${key} is not a count.`);
  }
  return value;
}

function optionalString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== "string" || value.length === 0) {
    throw new ContractError(`Field ${key} is not text.`);
  }
  return value;
}

function optionalDecimal(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== "string" || !isDecimalString(value)) {
    throw new ContractError(`Field ${key} is not a decimal string.`);
  }
  return value;
}

function monthField(record: Record<string, unknown>, key: string): string {
  const value = requiredString(record, key);
  if (!MONTH.test(value)) {
    throw new ContractError(`Field ${key} is not a month.`);
  }
  return value;
}

function parseHistoryPoint(value: unknown, expectedState: string | null): HistoryPoint {
  if (!isRecord(value)) {
    throw new ContractError("History point is not an object.");
  }
  if (value.unit !== "cents/kWh" || value.role !== "observed") {
    throw new ContractError("History point role or unit is unexpected.");
  }
  const stateId = requiredString(value, "state_id");
  if (expectedState !== null && stateId !== expectedState) {
    throw new ContractError("History point state does not match the request.");
  }
  return {
    state_id: stateId,
    period: monthField(value, "period"),
    observed_price_cents_per_kwh: decimalField(value, "observed_price_cents_per_kwh"),
    unit: "cents/kWh",
    role: "observed",
  };
}

export function parseHistory(value: unknown): HistoryResponse {
  if (!isRecord(value)) {
    throw new ContractError("History response is not an object.");
  }
  if (value.claim_boundary !== "observed_history" || value.unit !== "cents/kWh") {
    throw new ContractError("History claim or unit is unexpected.");
  }
  const stateId = optionalString(value, "state_id");
  if (!Array.isArray(value.points)) {
    throw new ContractError("History points are missing.");
  }
  const points = value.points.map((point) => parseHistoryPoint(point, stateId));
  const returned = integerField(value, "returned_row_count");
  if (returned !== points.length) {
    throw new ContractError("History row count does not match the points.");
  }
  return {
    claim_boundary: "observed_history",
    state_id: stateId,
    extract_id: requiredString(value, "extract_id"),
    retrieved_at: optionalString(value, "retrieved_at"),
    source_name: optionalString(value, "source_name"),
    recorded_price_units: optionalString(value, "recorded_price_units"),
    unit: "cents/kWh",
    earliest_period: monthField(value, "earliest_period"),
    latest_period: monthField(value, "latest_period"),
    extract_row_count: integerField(value, "extract_row_count"),
    returned_row_count: returned,
    limitations: requiredString(value, "limitations"),
    series_name: requiredString(value, "series_name"),
    points,
  };
}

function parseSeriesValue<Role extends SeriesValue["role"]>(
  value: unknown,
  role: Role,
): SeriesValue & { role: Role } {
  if (!isRecord(value) || value.unit !== "cents/kWh" || value.role !== role) {
    throw new ContractError("Series value role or unit is unexpected.");
  }
  return {
    cents_per_kwh: decimalField(value, "cents_per_kwh"),
    unit: "cents/kWh",
    role,
  };
}

function parseHoldoutPoint(value: unknown, expectedState: string | null): HoldoutPoint {
  if (!isRecord(value) || !isRecord(value.interval) || !isRecord(value.provenance)) {
    throw new ContractError("Holdout point is incomplete.");
  }
  if (value.interval.unit !== "cents/kWh") {
    throw new ContractError("Holdout interval unit is unexpected.");
  }
  const covered = value.interval.covered;
  if (covered !== null && covered !== undefined && typeof covered !== "boolean") {
    throw new ContractError("Holdout interval coverage flag is not boolean.");
  }
  const stateId = requiredString(value, "state_id");
  if (expectedState !== null && stateId !== expectedState) {
    throw new ContractError("Holdout point state does not match the request.");
  }
  return {
    state_id: stateId,
    target_month: monthField(value, "target_month"),
    actual: parseSeriesValue(value.actual, "observed"),
    ridge: parseSeriesValue(value.ridge, "closed_prediction"),
    seasonal_naive: parseSeriesValue(value.seasonal_naive, "closed_prediction"),
    interval: {
      lower_cents_per_kwh: optionalDecimal(value.interval, "lower_cents_per_kwh"),
      upper_cents_per_kwh: optionalDecimal(value.interval, "upper_cents_per_kwh"),
      covered: typeof covered === "boolean" ? covered : null,
      unit: "cents/kWh",
    },
    provenance: {
      forecast_origin: requiredString(value.provenance, "forecast_origin"),
    },
  };
}

export function parseHoldout(value: unknown): HoldoutResponse {
  if (!isRecord(value) || !isRecord(value.window)) {
    throw new ContractError("Holdout response is incomplete.");
  }
  if (value.claim_boundary !== "closed_historical_evaluation") {
    throw new ContractError("Holdout claim boundary is unexpected.");
  }
  const window = value.window;
  if (window.axis !== "target_month" || window.empirical_interval_coverage_unit !== "share") {
    throw new ContractError("Holdout axis or coverage unit is unexpected.");
  }
  const stateId = optionalString(value, "state_id");
  if (!Array.isArray(value.points)) {
    throw new ContractError("Holdout points are missing.");
  }
  const points = value.points.map((point) => parseHoldoutPoint(point, stateId));
  const returned = integerField(value, "returned_row_count");
  if (returned !== points.length) {
    throw new ContractError("Holdout row count does not match the points.");
  }
  return {
    claim_boundary: "closed_historical_evaluation",
    state_id: stateId,
    limitations: requiredString(value, "limitations"),
    window: {
      axis: "target_month",
      origin_start: requiredString(window, "origin_start"),
      origin_end: requiredString(window, "origin_end"),
      target_start: monthField(window, "target_start"),
      target_end: monthField(window, "target_end"),
      extract_id: optionalString(window, "extract_id"),
      feature_set_id: optionalString(window, "feature_set_id"),
      evaluation_stage: optionalString(window, "evaluation_stage"),
      summary_source: optionalString(window, "summary_source"),
      interval_warning: optionalString(window, "interval_warning"),
      empirical_interval_coverage: optionalDecimal(window, "empirical_interval_coverage"),
      empirical_interval_coverage_unit: "share",
    },
    returned_row_count: returned,
    points,
  };
}

function parseHoldoutCase(value: unknown): HoldoutCase {
  if (!isRecord(value)) {
    throw new ContractError("Holdout case is not an object.");
  }
  if (value.unit !== "cents/kWh" || value.ridge_role !== "closed_prediction" || value.actual_role !== "observed") {
    throw new ContractError("Holdout case role or unit is unexpected.");
  }
  return {
    state_id: requiredString(value, "state_id"),
    forecast_origin: requiredString(value, "forecast_origin"),
    target_month: monthField(value, "target_month"),
    ridge_prediction_cents_per_kwh: decimalField(value, "ridge_prediction_cents_per_kwh"),
    actual_cents_per_kwh: decimalField(value, "actual_cents_per_kwh"),
    seasonal_naive_prediction_cents_per_kwh: decimalField(value, "seasonal_naive_prediction_cents_per_kwh"),
    unit: "cents/kWh",
    ridge_role: "closed_prediction",
    actual_role: "observed",
  };
}

export function parseHoldoutCases(value: unknown): HoldoutCasesResponse {
  if (!isRecord(value) || value.claim_boundary !== "closed_historical_evaluation" || value.unit !== "cents/kWh") {
    throw new ContractError("Holdout cases response is unexpected.");
  }
  if (!Array.isArray(value.cases)) {
    throw new ContractError("Holdout cases are missing.");
  }
  const cases = value.cases.map(parseHoldoutCase);
  if (integerField(value, "row_count") !== cases.length) {
    throw new ContractError("Holdout case count does not match the rows.");
  }
  return {
    claim_boundary: "closed_historical_evaluation",
    limitations: requiredString(value, "limitations"),
    unit: "cents/kWh",
    row_count: cases.length,
    cases,
  };
}

function nullableText(value: unknown, label: string): string | null {
  if (value === null) {
    return null;
  }
  if (typeof value !== "string" || value.length === 0) {
    throw new ContractError(`${label} is not text.`);
  }
  return value;
}

function parseFinanceScenario(value: unknown): FinanceScenarioResult {
  if (!isRecord(value) || value.claim_boundary !== "hypothetical_energy_cost") {
    throw new ContractError("Finance scenario claim is unexpected.");
  }
  if (value.price_source !== "typed_hypothetical" && value.price_source !== "holdout_ridge") {
    throw new ContractError("Finance price source is unexpected.");
  }
  if (
    value.facility_average_demand_unit !== "MW" ||
    value.annual_consumption_unit !== "kWh" ||
    value.price_unit !== "cents/kWh" ||
    value.annual_electricity_cost_unit !== "USD" ||
    value.cost_difference_unit !== "USD"
  ) {
    throw new ContractError("Finance units are unexpected.");
  }
  if (typeof value.model_derived_eia_price !== "boolean") {
    throw new ContractError("Finance model flag is not boolean.");
  }
  return {
    scenario_name: requiredString(value, "scenario_name"),
    price_source: value.price_source,
    price_label: requiredString(value, "price_label"),
    claim_boundary: "hypothetical_energy_cost",
    it_capacity_mw: decimalField(value, "it_capacity_mw"),
    pue: decimalField(value, "pue"),
    utilization: decimalField(value, "utilization"),
    operating_hours_per_year: decimalField(value, "operating_hours_per_year"),
    facility_average_demand_mw: decimalField(value, "facility_average_demand_mw"),
    facility_average_demand_unit: "MW",
    annual_consumption_kwh: decimalField(value, "annual_consumption_kwh"),
    annual_consumption_unit: "kWh",
    price_cents_per_kwh: decimalField(value, "price_cents_per_kwh"),
    price_unit: "cents/kWh",
    annual_electricity_cost_usd: decimalField(value, "annual_electricity_cost_usd"),
    annual_electricity_cost_unit: "USD",
    baseline_scenario_name: requiredString(value, "baseline_scenario_name"),
    cost_difference_vs_baseline_usd: decimalField(value, "cost_difference_vs_baseline_usd"),
    cost_difference_unit: "USD",
    model_derived_eia_price: value.model_derived_eia_price,
    model_price_warning: nullableText(value.model_price_warning, "Model price warning"),
  };
}

export function parseFinance(value: unknown): FinanceResponse {
  if (!isRecord(value) || value.claim_boundary !== "hypothetical_energy_cost" || !Array.isArray(value.scenarios)) {
    throw new ContractError("Finance response is incomplete.");
  }
  const boundary = value.closed_holdout_claim_boundary;
  if (boundary !== null && boundary !== "closed_historical_evaluation") {
    throw new ContractError("Finance holdout claim is unexpected.");
  }
  return {
    claim_boundary: "hypothetical_energy_cost",
    closed_holdout_claim_boundary: boundary,
    closed_holdout_limitation: nullableText(value.closed_holdout_limitation, "Closed holdout limitation"),
    scenarios: value.scenarios.map(parseFinanceScenario),
  };
}

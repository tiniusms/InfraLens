import type {
  ArtifactId,
  ArtifactReport,
  ArtifactStatus,
  ArtifactValidation,
  ErrorCode,
  ErrorResponse,
  EvaluationSummary,
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

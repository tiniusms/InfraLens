export type ArtifactId =
  | "committed_summary"
  | "price_history"
  | "holdout_cases"
  | "pjm_2025_tables"
  | "pjm_2026_tables";

export type ArtifactStatus = "missing" | "present_unvalidated" | "valid" | "invalid";

export type ArtifactValidation = "not_applicable" | "deferred" | "validated" | "failed";

export type ErrorCode =
  | "artifact_missing"
  | "validation_error"
  | "malformed_vintage"
  | "artifact_invalid";

export type ErrorResponse = {
  code: ErrorCode;
  message: string;
  artifact_id: ArtifactId | null;
  field: string | null;
};

export type ArtifactReport = {
  artifact_id: ArtifactId;
  status: ArtifactStatus;
  validation: ArtifactValidation;
  detail: string | null;
};

export type StatusResponse = {
  claim_boundary: null;
  prototype_caption: string;
  presence_mode: "portable_summary" | "local_full_data";
  presence_mode_meaning: "file_existence_only";
  artifacts: ArtifactReport[];
};

export type StateMae = {
  n_scored: number;
  paired_baseline_mae: string;
  ridge_mae: string;
};

export type HistoryPoint = {
  state_id: string;
  period: string;
  observed_price_cents_per_kwh: string;
  unit: "cents/kWh";
  role: "observed";
};

export type HistoryResponse = {
  claim_boundary: "observed_history";
  state_id: string | null;
  extract_id: string;
  retrieved_at: string | null;
  source_name: string | null;
  recorded_price_units: string | null;
  unit: "cents/kWh";
  earliest_period: string;
  latest_period: string;
  extract_row_count: number;
  returned_row_count: number;
  limitations: string;
  series_name: string;
  points: HistoryPoint[];
};

export type SeriesValue = {
  cents_per_kwh: string;
  unit: "cents/kWh";
  role: "observed" | "closed_prediction";
};

export type HoldoutPoint = {
  state_id: string;
  target_month: string;
  actual: SeriesValue & { role: "observed" };
  ridge: SeriesValue & { role: "closed_prediction" };
  seasonal_naive: SeriesValue & { role: "closed_prediction" };
  interval: {
    lower_cents_per_kwh: string | null;
    upper_cents_per_kwh: string | null;
    covered: boolean | null;
    unit: "cents/kWh";
  };
  provenance: {
    forecast_origin: string;
  };
};

export type HoldoutResponse = {
  claim_boundary: "closed_historical_evaluation";
  state_id: string | null;
  limitations: string;
  window: {
    axis: "target_month";
    origin_start: string;
    origin_end: string;
    target_start: string;
    target_end: string;
    extract_id: string | null;
    feature_set_id: string | null;
    evaluation_stage: string | null;
    summary_source: string | null;
    interval_warning: string | null;
    empirical_interval_coverage: string | null;
    empirical_interval_coverage_unit: "share";
  };
  returned_row_count: number;
  points: HoldoutPoint[];
};

export type EvaluationSummary = {
  claim_boundary: "closed_historical_evaluation";
  source_label: string;
  limitations: string;
  units: {
    mae: "cents/kWh";
    improvement: "percent";
    threshold: "percent";
    interval_coverage: "share";
  };
  executed_on: string;
  runner_commit: string;
  summary: {
    primary_criterion: string;
    ridge_mae: string;
    paired_baseline_mae: string;
    mae_improvement_percent: string;
    primary_threshold_percent: number;
    primary_threshold_ratio: string;
    interval_coverage: string;
    nominal_interval_coverage: string;
    mae_by_state: Record<"MD" | "NJ" | "OH" | "PA" | "VA", StateMae>;
  };
};

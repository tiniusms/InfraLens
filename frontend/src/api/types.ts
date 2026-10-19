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

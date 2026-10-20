import type { ArtifactId, ArtifactStatus } from "../api/types";

const ROLES: Record<ArtifactId, string> = {
  committed_summary: "Committed holdout summary",
  price_history: "Observed price history",
  holdout_cases: "Frozen holdout cases",
  pjm_2025_tables: "PJM 2025 Tables workbook",
  pjm_2026_tables: "PJM 2026 Tables workbook",
};

const ALLOWS: Record<ArtifactStatus, string> = {
  missing: "Leave it unavailable. Do not download a substitute or rerun the final holdout.",
  present_unvalidated:
    "The file is on disk. Validation has not run, so measures from this file are not shown.",
  valid: "The existing reader accepted this file. That check is not a new evaluation.",
  invalid: "Validation failed. Contents of this file are not shown.",
};

export function artifactRole(id: ArtifactId): string {
  return ROLES[id];
}

export function artifactAllows(status: ArtifactStatus): string {
  return ALLOWS[status];
}

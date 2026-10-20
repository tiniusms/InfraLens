import type { ArtifactStatus, ArtifactValidation } from "../../api/types";

const STATUS_LABEL: Record<ArtifactStatus, string> = {
  missing: "Missing",
  present_unvalidated: "Present, unvalidated",
  valid: "Valid",
  invalid: "Invalid",
};

type ArtifactStatusMarkProps = {
  status: ArtifactStatus;
  validation: ArtifactValidation;
};

export function ArtifactStatusMark({ status, validation }: ArtifactStatusMarkProps) {
  const label = STATUS_LABEL[status];
  if (status === "missing") {
    return (
      <span data-indicator="missing" data-validation={validation} className="unavailable-chip px-2 py-1 text-[12px] leading-4 font-semibold tracking-[0.04em]">
        {label}
      </span>
    );
  }
  if (status === "present_unvalidated") {
    return (
      <span data-indicator="file-present" data-validation={validation} className="present-chip px-2 py-1 text-[12px] leading-4 font-semibold tracking-[0.04em]">
        {label}
      </span>
    );
  }
  if (status === "invalid") {
    return (
      <span data-indicator="invalid" data-validation={validation} className="operational-panel px-2 py-1 text-[12px] leading-4 font-semibold tracking-[0.04em]">
        {label}
      </span>
    );
  }
  return (
    <span data-indicator="validated" data-validation={validation} className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink">
      {label}
    </span>
  );
}

import type { StatusResponse } from "../api/types";
import { ArtifactStatusMark } from "../components/status/ArtifactStatusMark";
import { artifactAllows, artifactRole } from "./artifactCopy";

const MODE_LABEL = {
  portable_summary: "Portable summary",
  local_full_data: "Local full data",
} as const;

function StackedLabel({ children }: { children: string }) {
  return (
    <span className="mb-1 block text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase sm:hidden">
      {children}
    </span>
  );
}

export function EvidenceTable({ status }: { status: StatusResponse }) {
  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-[16px] leading-6 font-semibold">Evidence</h2>
        <p className="mt-2 max-w-[68ch] text-[15px] leading-6 text-ink">{status.prototype_caption}</p>
        <p className="mt-2 text-[15px] leading-6 text-ink-muted">
          Presence mode <span className="numeric text-ink">{status.presence_mode}</span> ({MODE_LABEL[status.presence_mode]}).
          Meaning <span className="text-ink">{status.presence_mode_meaning}</span>. A file on disk is not the same as a validated file. The present chip marks presence only.
        </p>
      </div>
      <div className="overflow-x-auto" role="region" aria-label="Evidence">
        {/* Explicit roles keep the table semantics when rows stack below 640 px. */}
        <table role="table" className="w-full border-collapse text-left text-[15px] leading-6 max-sm:block">
          <thead role="rowgroup" className="bg-paper-inset text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase max-sm:hidden">
            <tr role="row">
              <th role="columnheader" className="px-3 py-2 font-semibold">Role</th>
              <th role="columnheader" className="px-3 py-2 font-semibold">Status</th>
              <th role="columnheader" className="px-3 py-2 font-semibold">Validation</th>
              <th role="columnheader" className="px-3 py-2 font-semibold">What this status allows</th>
            </tr>
          </thead>
          <tbody role="rowgroup" className="max-sm:block">
            {status.artifacts.map((artifact) => (
              <tr
                key={artifact.artifact_id}
                role="row"
                data-artifact={artifact.artifact_id}
                className="border-t border-line align-top max-sm:block max-sm:py-2"
              >
                <th role="rowheader" className="px-3 py-3 font-semibold text-ink max-sm:block max-sm:py-1" scope="row">
                  {artifactRole(artifact.artifact_id)}
                </th>
                <td role="cell" className="px-3 py-3 max-sm:block max-sm:py-1">
                  <StackedLabel>Status</StackedLabel>
                  <ArtifactStatusMark status={artifact.status} validation={artifact.validation} />
                </td>
                <td role="cell" className="px-3 py-3 text-ink max-sm:block max-sm:py-1">
                  <StackedLabel>Validation</StackedLabel>
                  {artifact.validation}
                </td>
                <td role="cell" className="px-3 py-3 text-ink max-sm:block max-sm:py-1">
                  <StackedLabel>What this status allows</StackedLabel>
                  {artifactAllows(artifact.status)}
                  {artifact.detail ? <span className="mt-1 block text-ink-muted">{artifact.detail}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

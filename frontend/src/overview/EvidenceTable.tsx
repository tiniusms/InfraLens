import type { StatusResponse } from "../api/types";
import { ArtifactStatusMark } from "../components/status/ArtifactStatusMark";
import { artifactAllows, artifactRole } from "./artifactCopy";

const MODE_LABEL = {
  portable_summary: "Portable summary",
  local_full_data: "Local full data",
} as const;

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
        <table className="w-full border-collapse text-left text-[15px] leading-6">
          <thead className="bg-paper-inset text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
            <tr>
              <th className="px-3 py-2 font-semibold">Role</th>
              <th className="px-3 py-2 font-semibold">Status</th>
              <th className="px-3 py-2 font-semibold">Validation</th>
              <th className="px-3 py-2 font-semibold">What this status allows</th>
            </tr>
          </thead>
          <tbody>
            {status.artifacts.map((artifact) => (
              <tr key={artifact.artifact_id} data-artifact={artifact.artifact_id} className="border-t border-line align-top">
                <th className="px-3 py-3 font-semibold text-ink" scope="row">
                  {artifactRole(artifact.artifact_id)}
                </th>
                <td className="px-3 py-3">
                  <ArtifactStatusMark status={artifact.status} validation={artifact.validation} />
                </td>
                <td className="px-3 py-3 text-ink">{artifact.validation}</td>
                <td className="px-3 py-3 text-ink">
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

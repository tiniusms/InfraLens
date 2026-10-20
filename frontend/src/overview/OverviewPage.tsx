import { useEffect, useState } from "react";
import { ApiClientError } from "../api/client";
import type { EvaluationSummary, StatusResponse } from "../api/types";
import { useApi } from "../api/useApi";
import { ErrorState } from "../components/status/ErrorState";
import { LoadingState } from "../components/status/LoadingState";
import { UnavailableState } from "../components/status/UnavailableState";
import { PageHeader } from "../components/shell/PageHeader";
import { EvaluationFinding } from "./EvaluationFinding";
import { EvidenceTable } from "./EvidenceTable";

type Resource<T> = { state: "loading" } | { state: "ready"; data: T } | { state: "error"; error: ApiClientError };

function asClientError(error: unknown): ApiClientError {
  if (error instanceof ApiClientError) {
    return error;
  }
  return new ApiClientError("connection", "The InfraLens API did not respond.");
}

function Failure({ error, subject }: { error: ApiClientError; subject: string }) {
  if (error.kind === "connection") {
    return (
      <ErrorState
        title="Connection unavailable"
        message={`The InfraLens API did not respond for ${subject}. Figures from that request are not shown, because this page does not keep a local copy of the frozen metrics.`}
      />
    );
  }
  if (error.code === "artifact_missing") {
    return <UnavailableState title="Artifact unavailable" message={error.message} />;
  }
  return <ErrorState title="Request failed" message={error.message} />;
}

export function OverviewPage() {
  const api = useApi();
  const [summary, setSummary] = useState<Resource<EvaluationSummary>>({ state: "loading" });
  const [status, setStatus] = useState<Resource<StatusResponse>>({ state: "loading" });
  const [requestApi, setRequestApi] = useState(api);
  if (requestApi !== api) {
    setRequestApi(api);
    setSummary({ state: "loading" });
    setStatus({ state: "loading" });
  }

  useEffect(() => {
    document.title = "Overview · InfraLens";
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    api
      .getEvaluationSummary(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setSummary({ state: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setSummary({ state: "error", error: asClientError(error) });
        }
      });
    api
      .getStatus(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setStatus({ state: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setStatus({ state: "error", error: asClientError(error) });
        }
      });
    return () => controller.abort();
  }, [api]);

  return (
    <>
      <PageHeader
        title="Overview"
        scope="Frozen commercial-price evaluation for VA, PA, OH, MD, and NJ. This page reads the stored result. It does not rescore it."
      />
      <div className="flex flex-col gap-8">
        {summary.state === "loading" ? <LoadingState label="Loading the frozen evaluation." /> : null}
        {summary.state === "error" ? <Failure error={summary.error} subject="the evaluation summary" /> : null}
        {summary.state === "ready" ? <EvaluationFinding evaluation={summary.data} /> : null}
        {status.state === "loading" ? <LoadingState label="Loading artifact status." /> : null}
        {status.state === "error" ? <Failure error={status.error} subject="artifact status" /> : null}
        {status.state === "ready" ? <EvidenceTable status={status.data} /> : null}
      </div>
    </>
  );
}

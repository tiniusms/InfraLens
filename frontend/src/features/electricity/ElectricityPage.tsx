import { useEffect, useRef, useState } from "react";
import { ApiClientError } from "../../api/client";
import type { EvaluationSummary, HistoryResponse, HoldoutResponse } from "../../api/types";
import { useApi } from "../../api/useApi";
import { ScrollRegion } from "../../components/charts/ScrollRegion";
import { PageHeader } from "../../components/shell/PageHeader";
import { ErrorState } from "../../components/status/ErrorState";
import { LoadingState } from "../../components/status/LoadingState";
import { UnavailableState } from "../../components/status/UnavailableState";
import { shareToPercentText, signedIntegerText } from "../../lib/format";
import { HistoryChart } from "./HistoryChart";
import { HoldoutChart } from "./HoldoutChart";
import { historyRows, holdoutRows } from "./series";
import { StateControl } from "./StateControl";
import { type EiaState } from "./states";

type Resource<T> = { state: "loading" } | { state: "ready"; data: T } | { state: "error"; error: ApiClientError };

function asClientError(error: unknown): ApiClientError {
  if (error instanceof ApiClientError) {
    return error;
  }
  return new ApiClientError("connection", "The InfraLens API did not respond.");
}

function RequestNotice({ error, title }: { error: ApiClientError; title: string }) {
  if (error.kind === "connection") {
    return (
      <ErrorState
        title="Connection unavailable"
        message={`The InfraLens API did not respond for ${title}. This page does not keep a local copy of the series.`}
      />
    );
  }
  if (error.code === "artifact_missing") {
    return <UnavailableState title={`${title} unavailable`} message={error.message} />;
  }
  return <ErrorState title="Request failed" message={error.message} />;
}

function supplied(value: string | null): string {
  return value ?? "Not supplied";
}

function coveredText(value: boolean | null): string {
  if (value === null) {
    return "Not supplied";
  }
  return value ? "Covered" : "Not covered";
}

export function ElectricityPage() {
  const api = useApi();
  const [stateId, setStateId] = useState<EiaState>("VA");
  const [history, setHistory] = useState<Resource<HistoryResponse>>({ state: "loading" });
  const [holdout, setHoldout] = useState<Resource<HoldoutResponse>>({ state: "loading" });
  const [summary, setSummary] = useState<Resource<EvaluationSummary>>({ state: "loading" });
  const [loadedState, setLoadedState] = useState(stateId);
  const historyTicket = useRef(0);
  const holdoutTicket = useRef(0);

  if (loadedState !== stateId) {
    setLoadedState(stateId);
    setHistory({ state: "loading" });
    setHoldout({ state: "loading" });
  }

  useEffect(() => {
    document.title = "Electricity Intelligence · InfraLens";
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const ticket = historyTicket.current + 1;
    historyTicket.current = ticket;
    api
      .getHistory(stateId, controller.signal)
      .then((data) => {
        if (ticket === historyTicket.current) {
          setHistory({ state: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || ticket !== historyTicket.current) {
          return;
        }
        setHistory({ state: "error", error: asClientError(error) });
      });
    return () => controller.abort();
  }, [api, stateId]);

  useEffect(() => {
    const controller = new AbortController();
    const ticket = holdoutTicket.current + 1;
    holdoutTicket.current = ticket;
    api
      .getHoldout(stateId, controller.signal)
      .then((data) => {
        if (ticket === holdoutTicket.current) {
          setHoldout({ state: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || ticket !== holdoutTicket.current) {
          return;
        }
        setHoldout({ state: "error", error: asClientError(error) });
      });
    return () => controller.abort();
  }, [api, stateId]);

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
    return () => controller.abort();
  }, [api]);

  return (
    <>
      <PageHeader
        title="Electricity Intelligence"
        scope="Observed EIA commercial average retail prices are a public retail proxy, not a data-center tariff. The traces below the history are closed historical holdout evaluations, not live forecasts."
      />
      <div className="flex flex-col gap-8">
        <StateControl value={stateId} onChange={setStateId} />
        <p className="text-[15px] leading-6 text-ink" aria-live="polite">
          Showing {stateId}.
        </p>
        <HistorySection resource={history} />
        <HoldoutSection resource={holdout} summary={summary} />
      </div>
    </>
  );
}

function HistorySection({ resource }: { resource: Resource<HistoryResponse> }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-[16px] leading-6 font-semibold">Observed commercial average price</h2>
      {resource.state === "loading" ? <LoadingState label="Loading observed prices." /> : null}
      {resource.state === "error" ? <RequestNotice error={resource.error} title="Price history" /> : null}
      {resource.state === "ready" ? <HistoryReady history={resource.data} /> : null}
    </section>
  );
}

function HistoryReady({ history }: { history: HistoryResponse }) {
  const rows = historyRows(history);
  return (
    <>
      {rows.length > 0 && history.state_id ? (
        <HistoryChart rows={rows} stateId={history.state_id} />
      ) : (
        <UnavailableState title="Price history unavailable" message="The API returned no observed prices for this state." />
      )}
      <dl className="grid gap-2 text-[15px] leading-6">
        <div>
          <dt className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">Extract</dt>
          <dd className="break-all">{history.extract_id}</dd>
        </div>
        <div>
          <dt className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">Source</dt>
          <dd>{supplied(history.source_name)}</dd>
        </div>
        <div>
          <dt className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">Recorded units</dt>
          <dd>{supplied(history.recorded_price_units)}</dd>
        </div>
        <div>
          <dt className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">Display unit</dt>
          <dd>{history.unit}</dd>
        </div>
        <div>
          <dt className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">Rows</dt>
          <dd className="numeric">
            {history.returned_row_count} returned, {history.extract_row_count} in the extract
          </dd>
        </div>
        <div>
          <dt className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">Observed months</dt>
          <dd className="numeric">
            {history.earliest_period} through {history.latest_period}
          </dd>
        </div>
        <div>
          <dt className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">Retrieved at</dt>
          <dd>{supplied(history.retrieved_at)}</dd>
        </div>
      </dl>
      <p className="max-w-[68ch] text-[15px] leading-6 text-ink">{history.limitations}</p>
      <ScrollRegion
        label="Observed price table"
        maxHeightClass="max-h-96"
        cue={`Scroll to read all ${rows.length} observed months and every column. Every returned row stays in this table.`}
      >
        <table className="w-full min-w-[40rem] border-collapse text-left text-[15px] leading-6 whitespace-nowrap">
          <caption className="sr-only">Observed commercial prices by month</caption>
          <thead className="bg-paper-inset text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
            <tr>
              <th className="px-3 py-2 font-semibold">Observed month</th>
              <th className="px-3 py-2 font-semibold">State</th>
              <th className="px-3 py-2 font-semibold">Price, cents/kWh</th>
              <th className="px-3 py-2 font-semibold">Role</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.stateId}-${row.period}`} className="border-t border-line">
                <th className="numeric px-3 py-2 font-semibold" scope="row">
                  {row.period}
                </th>
                <td className="px-3 py-2">{row.stateId}</td>
                <td className="numeric px-3 py-2">{row.priceText}</td>
                <td className="px-3 py-2">{row.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollRegion>
    </>
  );
}

function HoldoutSection({
  resource,
  summary,
}: {
  resource: Resource<HoldoutResponse>;
  summary: Resource<EvaluationSummary>;
}) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-[16px] leading-6 font-semibold">Closed historical evaluation</h2>
      <Criterion summary={summary} />
      {resource.state === "loading" ? <LoadingState label="Loading the closed holdout." /> : null}
      {resource.state === "error" ? <RequestNotice error={resource.error} title="Closed holdout" /> : null}
      {resource.state === "ready" ? <HoldoutReady holdout={resource.data} summary={summary} /> : null}
    </section>
  );
}

function Criterion({ summary }: { summary: Resource<EvaluationSummary> }) {
  if (summary.state === "loading") {
    return <LoadingState label="Loading the frozen criterion." />;
  }
  if (summary.state === "error") {
    return <RequestNotice error={summary.error} title="Frozen criterion" />;
  }
  const stored = summary.data.summary;
  const gate = signedIntegerText(stored.primary_threshold_percent);
  return (
    <div data-surface="finding" className="finding-panel px-4 py-4">
      <p className="text-[12px] leading-4 font-semibold tracking-[0.04em] uppercase">Frozen EIA holdout</p>
      <h3 className="mt-2 font-serif text-[28px] leading-9 font-semibold">Primary criterion: {stored.primary_criterion}</h3>
      <p className="mt-3 max-w-[68ch] text-[15px] leading-6">
        Nominal interval coverage is stored share {stored.nominal_interval_coverage} (
        {shareToPercentText(stored.nominal_interval_coverage)}% as a percent reading). Observed interval coverage is
        stored share {stored.interval_coverage} ({shareToPercentText(stored.interval_coverage)}% as a percent reading).
        The 75–85% band is a diagnostic for the nominal interval. It is not the primary relative-improvement gate of{" "}
        {gate} {summary.data.units.threshold}.
      </p>
      <p className="mt-3 max-w-[68ch] text-[15px] leading-6">{summary.data.limitations}</p>
    </div>
  );
}

function HoldoutReady({ holdout, summary }: { holdout: HoldoutResponse; summary: Resource<EvaluationSummary> }) {
  const rows = holdoutRows(holdout);
  const coverage = holdout.window.empirical_interval_coverage;
  return (
    <>
      <p className="max-w-[68ch] text-[15px] leading-6 text-ink">{holdout.limitations}</p>
      {holdout.window.interval_warning ? (
        <p className="max-w-[68ch] text-[15px] leading-6 text-ink">{holdout.window.interval_warning}</p>
      ) : null}
      <p className="max-w-[68ch] text-[15px] leading-6 text-ink">
        Chart empirical interval coverage, {holdout.window.empirical_interval_coverage_unit}: {supplied(coverage)}
        {coverage ? ` (${shareToPercentText(coverage)}% as a percent reading of the stored share)` : ""}. The horizontal
        axis is {holdout.window.axis}.
      </p>
      {rows.length > 0 && holdout.state_id ? (
        <HoldoutChart rows={rows} stateId={holdout.state_id} />
      ) : (
        <UnavailableState title="Closed holdout unavailable" message="The API returned no closed cases for this state." />
      )}
      <p className="max-w-[68ch] text-[15px] leading-6 text-ink-muted">
        Forecast origins {holdout.window.origin_start} through {holdout.window.origin_end}. Target months{" "}
        {holdout.window.target_start} through {holdout.window.target_end}. Feature set{" "}
        {supplied(holdout.window.feature_set_id)}. Stage {supplied(holdout.window.evaluation_stage)}. Summary source{" "}
        <span className="break-all">{supplied(holdout.window.summary_source)}</span>. Extract{" "}
        <span className="break-all">{supplied(holdout.window.extract_id)}</span>.{" "}
        {summary.state === "ready" ? `Runner ${summary.data.runner_commit}.` : ""}
      </p>
      <ScrollRegion label="Closed holdout table">
        <table className="w-full min-w-[64rem] border-collapse text-left text-[15px] leading-6 whitespace-nowrap">
          <caption className="sr-only">Closed holdout cases by target month</caption>
          <thead className="bg-paper-inset text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
            <tr>
              <th className="px-3 py-2 font-semibold">Target month</th>
              <th className="px-3 py-2 font-semibold">Forecast origin</th>
              <th className="px-3 py-2 font-semibold">Actual observed</th>
              <th className="px-3 py-2 font-semibold">Actual role</th>
              <th className="px-3 py-2 font-semibold">Ridge closed prediction</th>
              <th className="px-3 py-2 font-semibold">Ridge role</th>
              <th className="px-3 py-2 font-semibold">Seasonal-naive closed prediction</th>
              <th className="px-3 py-2 font-semibold">Naive role</th>
              <th className="px-3 py-2 font-semibold">Interval lower</th>
              <th className="px-3 py-2 font-semibold">Interval upper</th>
              <th className="px-3 py-2 font-semibold">Covered</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.targetMonth}-${row.forecastOrigin}`} className="border-t border-line">
                <th className="numeric px-3 py-2 font-semibold" scope="row">
                  {row.targetMonth}
                </th>
                <td className="numeric px-3 py-2">{row.forecastOrigin}</td>
                <td className="numeric px-3 py-2">{row.actualText}</td>
                <td className="px-3 py-2">{row.actualRole}</td>
                <td className="numeric px-3 py-2">{row.ridgeText}</td>
                <td className="px-3 py-2">{row.ridgeRole}</td>
                <td className="numeric px-3 py-2">{row.naiveText}</td>
                <td className="px-3 py-2">{row.naiveRole}</td>
                <td className="numeric px-3 py-2">{supplied(row.lowerText)}</td>
                <td className="numeric px-3 py-2">{supplied(row.upperText)}</td>
                <td className="px-3 py-2">{coveredText(row.covered)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollRegion>
    </>
  );
}

import { useEffect, useRef, useState } from "react";
import { ApiClientError } from "../../api/client";
import type { PjmCatalogResponse, PjmScreenResponse } from "../../api/types";
import { useApi } from "../../api/useApi";
import { PageHeader } from "../../components/shell/PageHeader";
import { ErrorState } from "../../components/status/ErrorState";
import { LoadingState } from "../../components/status/LoadingState";
import { UnavailableState } from "../../components/status/UnavailableState";

type CatalogResource =
  | { state: "loading" }
  | { state: "ready"; data: PjmCatalogResponse }
  | { state: "error"; error: ApiClientError };

type Phase =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; screen: PjmScreenResponse }
  | { status: "error"; error: ApiClientError };

const FIELD_CLASS =
  "w-full min-w-0 rounded-[2px] border border-line bg-paper-raised px-3 py-2 text-[15px] leading-6 text-ink lg:w-auto";

const DEFAULT_ZONE = "AEP";
const DEFAULT_YEAR = 2026;
const DEFAULT_AS_OF = "2026-02-06";

function isCalendarDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    return false;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const utc = new Date(Date.UTC(year, month - 1, day));
  return utc.getUTCFullYear() === year && utc.getUTCMonth() === month - 1 && utc.getUTCDate() === day;
}

function asClientError(error: unknown): ApiClientError {
  if (error instanceof ApiClientError) {
    return error;
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return new ApiClientError("connection", "The request was cancelled.");
  }
  return new ApiClientError("connection", "The InfraLens API did not respond.");
}

function publishedNumber(value: number): string {
  return Object.is(value, -0) ? "0" : `${value}`;
}

function fileLabel(value: string): string {
  const slash = Math.max(value.lastIndexOf("/"), value.lastIndexOf("\\"));
  return slash >= 0 ? value.slice(slash + 1) : value;
}

export function PjmPage() {
  const api = useApi();
  const [catalog, setCatalog] = useState<CatalogResource>({ state: "loading" });
  const [zoneChoice, setZoneChoice] = useState<string | null>(null);
  const [yearChoice, setYearChoice] = useState<number | null>(null);
  const [asOf, setAsOf] = useState(DEFAULT_AS_OF);
  const [phase, setPhase] = useState<Phase>({ status: "idle" });
  const ticket = useRef(0);

  useEffect(() => {
    document.title = "PJM Infrastructure Explorer · InfraLens";
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    api
      .getPjmCatalog(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setCatalog({ state: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setCatalog({ state: "error", error: asClientError(error) });
        }
      });
    return () => controller.abort();
  }, [api]);

  const zone =
    catalog.state === "ready"
      ? zoneChoice !== null && catalog.data.zones.includes(zoneChoice)
        ? zoneChoice
        : catalog.data.zones.includes(DEFAULT_ZONE)
          ? DEFAULT_ZONE
          : catalog.data.zones[0]
      : null;
  const year =
    catalog.state === "ready"
      ? yearChoice !== null && catalog.data.forecast_years.includes(yearChoice)
        ? yearChoice
        : catalog.data.forecast_years.includes(DEFAULT_YEAR)
          ? DEFAULT_YEAR
          : catalog.data.forecast_years[0]
      : null;
  const asOfValid = isCalendarDate(asOf);

  useEffect(() => {
    if (catalog.state !== "ready" || zone === null || zone === undefined || year === null || year === undefined) {
      return;
    }
    if (!asOfValid || !catalog.data.zones.includes(zone) || !catalog.data.forecast_years.includes(year)) {
      return;
    }
    const controller = new AbortController();
    const currentTicket = ticket.current + 1;
    ticket.current = currentTicket;
    api
      .getPjmScreen(zone, year, asOf, controller.signal)
      .then((screen) => {
        if (currentTicket !== ticket.current || controller.signal.aborted) {
          return;
        }
        setPhase({ status: "ready", screen });
      })
      .catch((error: unknown) => {
        if (currentTicket !== ticket.current || controller.signal.aborted) {
          return;
        }
        const failure = asClientError(error);
        if (failure.kind === "connection" && failure.message === "The request was cancelled.") {
          return;
        }
        setPhase({ status: "error", error: failure });
      });
    return () => controller.abort();
  }, [api, asOf, asOfValid, catalog, year, zone]);

  return (
    <>
      <PageHeader
        title="PJM Infrastructure Explorer"
        scope="Zonal planning screening from published load-forecast tables. This is not a state-level price forecast, and it does not rank locations."
      />
      {catalog.state === "loading" ? <LoadingState label="Loading the PJM zone catalog." /> : null}
      {catalog.state === "error" ? <CatalogError error={catalog.error} /> : null}
      {catalog.state === "ready" && zone !== null && zone !== undefined && year !== null && year !== undefined ? (
        <div className="flex flex-col gap-8">
          <Cautions geographic={catalog.data.geographic_warning} largeLoad={catalog.data.large_load_warning} />
          <form
            className="flex flex-col gap-4 lg:flex-row lg:items-start"
            onSubmit={(event) => event.preventDefault()}
          >
            <SelectControl
              id="pjm_zone"
              label="PJM zone"
              value={zone}
              options={catalog.data.zones}
              onChange={(value) => {
                setZoneChoice(value);
                setPhase({ status: "loading" });
              }}
            />
            <SelectControl
              id="forecast_year"
              label="Forecast year"
              value={String(year)}
              options={catalog.data.forecast_years.map(String)}
              onChange={(value) => {
                setYearChoice(Number(value));
                setPhase({ status: "loading" });
              }}
            />
            <div className="min-w-0 lg:max-w-64">
              <label htmlFor="as_of" className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
                As-of date
              </label>
              <input
                id="as_of"
                className={`${FIELD_CLASS} numeric mt-1`}
                inputMode="numeric"
                autoComplete="off"
                spellCheck={false}
                aria-invalid={asOfValid ? undefined : true}
                aria-describedby={asOfValid ? "as_of-hint" : "as_of-hint as_of-error"}
                value={asOf}
                onChange={(event) => {
                  setAsOf(event.target.value);
                  setPhase({ status: "idle" });
                }}
              />
              <p id="as_of-hint" className="mt-1 text-[15px] leading-6 text-ink-muted">
                Evidence-eligibility cutoff, as YYYY-MM-DD. A vintage is eligible only when its availability date is on or before this day.
              </p>
              {asOfValid ? null : (
                <p id="as_of-error" className="mt-1 text-[15px] leading-6" role="alert">
                  Enter a real calendar date as YYYY-MM-DD. The previous vintage is not shown.
                </p>
              )}
            </div>
          </form>
          <ScreenResult phase={phase} asOfValid={asOfValid} />
        </div>
      ) : null}
    </>
  );
}

function CatalogError({ error }: { error: ApiClientError }) {
  if (error.kind === "connection") {
    return (
      <ErrorState
        title="Connection unavailable"
        message="The InfraLens API did not respond for the PJM catalog. Zones are not substituted."
      />
    );
  }
  if (error.code === "artifact_missing") {
    return <UnavailableState title="Zonal screening unavailable" message={error.message} />;
  }
  return <ErrorState title="The zone catalog was not usable" message={error.message} />;
}

function Cautions({ geographic, largeLoad }: { geographic: string; largeLoad: string }) {
  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Geographic caution" className="border border-line px-4 py-4">
        <h2 className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">Geographic caution</h2>
        <p className="mt-2 text-[15px] leading-6">{geographic}</p>
      </section>
      <section aria-label="Large-load caution" className="border border-line px-4 py-4">
        <h2 className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">Large-load caution</h2>
        <p className="mt-2 text-[15px] leading-6">{largeLoad}</p>
      </section>
    </div>
  );
}

function SelectControl({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="min-w-0 lg:w-48">
      <label htmlFor={id} className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
        {label}
      </label>
      <select id={id} className={`${FIELD_CLASS} mt-1`} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

function ScreenResult({ phase, asOfValid }: { phase: Phase; asOfValid: boolean }) {
  return (
    <section aria-live="polite" aria-busy={phase.status === "loading"} aria-label="Zone-year screening" className="flex flex-col gap-6">
      {!asOfValid ? null : phase.status === "idle" || phase.status === "loading" ? (
        <LoadingState label="Loading the selected vintage." />
      ) : null}
      {phase.status === "error" ? <ScreenError error={phase.error} /> : null}
      {phase.status === "ready" ? <ScreenReady screen={phase.screen} /> : null}
    </section>
  );
}

function ScreenError({ error }: { error: ApiClientError }) {
  if (error.kind === "connection") {
    return (
      <ErrorState
        title="Connection unavailable"
        message="The InfraLens API did not respond. No screening measures are shown."
      />
    );
  }
  if (error.code === "artifact_missing") {
    return <UnavailableState title="Zonal screening unavailable" message={error.message} />;
  }
  if (error.code === "malformed_vintage") {
    return <ErrorState title="Published vintage is not usable" message={error.message} />;
  }
  if (error.kind === "invalid_body") {
    return <ErrorState title="Response was not usable" message={error.message} />;
  }
  return <ErrorState title="The screening request was rejected" message={error.message} />;
}

function ScreenReady({ screen }: { screen: PjmScreenResponse }) {
  if (!screen.available) {
    return (
      <UnavailableState
        title="Unpublished on this as-of date"
        message={screen.unavailable_reason ?? "Measures are not shown."}
      />
    );
  }
  return (
    <div className="flex flex-col gap-8">
      <VintageSummary screen={screen} />
      <MeasuresTable screen={screen} />
      <Provenance screen={screen} />
    </div>
  );
}

function VintageSummary({ screen }: { screen: PjmScreenResponse }) {
  return (
    <section aria-label="Selected vintage" className="flex flex-col gap-3">
      <h2 className="text-[16px] leading-6 font-semibold">Selected vintage</h2>
      <p className="text-[15px] leading-6 text-ink-muted">
        The service selected one public vintage for {screen.pjm_zone}, forecast year {screen.forecast_year}, as of {screen.as_of_date}.
      </p>
      <dl className="flex flex-col gap-3 text-[15px] leading-6">
        <Fact label="Report vintage year" value={screen.ltlf_vintage_year === null ? "Not published" : String(screen.ltlf_vintage_year)} />
        <Fact label="Original publication date" value={screen.original_release_date ?? "Not published"} />
        <Fact label="Revision date" value={screen.revision_date ?? "No revision date is recorded for this vintage."} />
        <Fact label="Vintage available at" value={screen.vintage_available_at ?? "Not published"} />
      </dl>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-t border-line pt-3">
      <dt className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">{label}</dt>
      <dd className="numeric mt-1 text-ink">{value}</dd>
    </div>
  );
}

function MeasuresTable({ screen }: { screen: PjmScreenResponse }) {
  const rows: Array<{ label: string; definition: string; value: number | null; unit: string }> = [
    {
      label: "B1 summer peak demand",
      definition: "Table B1 summer peak demand for this zone and forecast year.",
      value: screen.summer_peak_mw,
      unit: screen.measure_unit,
    },
    {
      label: "B-9 above-embedded adjustment",
      definition: "Table B-9 above-embedded adjustment. This is not data-center demand and is not added to B-9b.",
      value: screen.above_embedded_mw,
      unit: screen.measure_unit,
    },
    {
      label: "B-9b total-associated adjustment",
      definition: "Table B-9b total-associated adjustment. This is not data-center demand and is not added to B-9.",
      value: screen.total_associated_mw,
      unit: screen.measure_unit,
    },
  ];
  return (
    <section aria-label="Published measures" className="flex flex-col gap-3">
      <h2 className="text-[16px] leading-6 font-semibold">Published measures</h2>
      <div tabIndex={0} aria-label="Screening measures" className="overflow-x-auto focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">
        <table className="w-full border-collapse text-left text-[15px] leading-6">
          <caption className="sr-only">
            B1 summer peak, B-9 above-embedded adjustment, and B-9b total-associated adjustment stay on separate rows.
          </caption>
          <thead>
            <tr className="border-b border-line text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
              <th scope="col" className="py-2 pr-4 font-semibold">Measure</th>
              <th scope="col" className="py-2 pr-4 font-semibold">Published value</th>
              <th scope="col" className="py-2 font-semibold">Unit</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-b border-line">
                <th scope="row" className="py-3 pr-4 font-normal">
                  <span className="block text-ink">{row.label}</span>
                  <span className="mt-1 block text-ink-muted">{row.definition}</span>
                </th>
                <td className="numeric py-3 pr-4 align-top whitespace-nowrap text-ink">
                  {row.value === null ? "Not published" : publishedNumber(row.value)}
                </td>
                <td className="py-3 align-top text-ink-muted">{row.unit}</td>
              </tr>
            ))}
            {screen.summer_peak_10yr_cagr !== null ? (
              <tr className="border-b border-line">
                <th scope="row" className="py-3 pr-4 font-normal">
                  <span className="block text-ink">10-year summer-peak CAGR</span>
                  <span className="mt-1 block text-ink-muted">{screen.cagr_percent_label}</span>
                </th>
                <td className="numeric py-3 pr-4 align-top text-ink whitespace-normal">
                  {publishedNumber(screen.summer_peak_10yr_cagr)}
                  {screen.cagr_percent_per_year === null ? null : (
                    <span className="mt-1 block">{publishedNumber(screen.cagr_percent_per_year)} percent per year</span>
                  )}
                </td>
                <td className="py-3 align-top text-ink-muted">decimal per year</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Provenance({ screen }: { screen: PjmScreenResponse }) {
  return (
    <section aria-label="Source evidence" className="flex flex-col gap-3">
      <h2 className="text-[16px] leading-6 font-semibold">Source evidence</h2>
      <ul className="flex flex-col gap-4">
        {screen.source_tables.map((table, index) => {
          const url = screen.source_urls[index] ?? "";
          const retrieved = screen.retrieved_at[index] ?? "";
          return (
            <li key={`${table}-${index}`} className="border-t border-line pt-3 text-[15px] leading-6">
              <p className="text-ink">
                {table}. {fileLabel(screen.source_files[index] ?? "")}
              </p>
              {url.startsWith("https://") ? (
                <a className="break-all text-ink underline" href={url}>
                  {url}
                </a>
              ) : (
                <p className="break-all text-ink-muted">{url === "" ? "No source URL was returned." : url}</p>
              )}
              <p className="text-ink-muted">retrieved_at {retrieved === "" ? "was not supplied." : retrieved}</p>
            </li>
          );
        })}
      </ul>
      <p className="max-w-[68ch] text-[15px] leading-6 text-ink-muted">{screen.retrieval_note}</p>
    </section>
  );
}

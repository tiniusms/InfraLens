import { useEffect, useRef, useState, type RefObject } from "react";
import { ApiClientError } from "../../api/client";
import type { FinanceResponse, HoldoutCase, HoldoutCasesResponse } from "../../api/types";
import { useApi } from "../../api/useApi";
import { PageHeader } from "../../components/shell/PageHeader";
import { Button } from "../../components/ui/button";
import { ErrorState } from "../../components/status/ErrorState";
import { LoadingState } from "../../components/status/LoadingState";
import { UnavailableState } from "../../components/status/UnavailableState";
import {
  ENERGY_CHARGE_IDENTITY,
  INITIAL_DRAFT,
  buildFinanceRequest,
  caseKeyId,
  errorSummaryItems,
  findCase,
  operatingHoursWarning,
  type ErrorSummaryItem,
  type FinanceDraft,
  type ScenarioDraft,
} from "./request";

type CasesResource =
  | { state: "loading" }
  | { state: "ready"; data: HoldoutCasesResponse }
  | { state: "error"; error: ApiClientError };

type Phase =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "stale" }
  | { status: "error"; error: ApiClientError }
  | { status: "ready"; response: FinanceResponse };

const FIELD_CLASS =
  "w-full min-w-0 rounded-[2px] border bg-paper-raised px-3 py-2 text-[15px] leading-6 text-ink";

function fieldClass(invalid: boolean): string {
  return `${FIELD_CLASS} ${invalid ? "border-ink ring-1 ring-inset ring-ink" : "border-line"}`;
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

function draftSnapshot(draft: FinanceDraft): string {
  return JSON.stringify(draft);
}

export function FinancePage() {
  const api = useApi();
  const [draft, setDraft] = useState<FinanceDraft>(INITIAL_DRAFT);
  const [cases, setCases] = useState<CasesResource>({ state: "loading" });
  const [phase, setPhase] = useState<Phase>({ status: "idle" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const ticket = useRef(0);
  const draftRef = useRef(draft);
  const focusFirstError = useRef(false);
  const errorSummary = useRef<HTMLDivElement>(null);
  const summaryItems = errorSummaryItems(fieldErrors);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    if (!focusFirstError.current) {
      return;
    }
    focusFirstError.current = false;
    const first = errorSummaryItems(fieldErrors)[0];
    if (!first) {
      return;
    }
    const target = first.targetId ? document.getElementById(first.targetId) : null;
    (target ?? errorSummary.current)?.focus();
  }, [fieldErrors]);

  useEffect(() => {
    document.title = "Financial Scenario Studio · InfraLens";
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    api
      .getHoldoutCases(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setCases({ state: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setCases({ state: "error", error: asClientError(error) });
        }
      });
    return () => controller.abort();
  }, [api]);

  const availableCases = cases.state === "ready" ? cases.data.cases : [];
  const ridgeAvailable = availableCases.length > 0;

  function markEdited() {
    setPhase((current) => {
      if (current.status === "ready" || current.status === "loading" || current.status === "stale") {
        return { status: "stale" };
      }
      if (current.status === "error") {
        return { status: "idle" };
      }
      return current;
    });
    setFieldErrors({});
  }

  function updateDraft(next: FinanceDraft) {
    setDraft(next);
    markEdited();
  }

  function updateScenario(key: "baseline" | "comparison", patch: Partial<ScenarioDraft>) {
    const scenario = { ...draft[key], ...patch };
    if (patch.source === "holdout_ridge" && !findCase(availableCases, scenario.caseId) && availableCases[0]) {
      scenario.caseId = caseKeyId(availableCases[0]);
    }
    updateDraft({ ...draft, [key]: scenario });
  }

  async function calculate() {
    const built = buildFinanceRequest(draft, availableCases);
    focusFirstError.current = Object.keys(built.errors).length > 0;
    setFieldErrors(built.errors);
    if (!built.request) {
      return;
    }
    const snapshot = draftSnapshot(draft);
    const currentTicket = ticket.current + 1;
    ticket.current = currentTicket;
    setPhase({ status: "loading" });
    try {
      const response = await api.postFinanceScenarios(built.request);
      if (currentTicket !== ticket.current) {
        return;
      }
      if (draftSnapshot(draftRef.current) !== snapshot) {
        setPhase({ status: "stale" });
        return;
      }
      setPhase({ status: "ready", response });
    } catch (error: unknown) {
      if (currentTicket !== ticket.current) {
        return;
      }
      const failure = asClientError(error);
      if (failure.kind === "connection" && failure.message === "The request was cancelled.") {
        return;
      }
      if (draftSnapshot(draftRef.current) !== snapshot) {
        setPhase({ status: "stale" });
        return;
      }
      setPhase({ status: "error", error: failure });
      if (failure.field) {
        focusFirstError.current = true;
        setFieldErrors(mapServerField(failure.field, failure.message, draft));
      }
    }
  }

  return (
    <>
      <PageHeader
        title="Financial Scenario Studio"
        scope="An annual energy charge is calculated by the Python service from a stated price. This page does not multiply that identity. The charge is not a complete tariff, a discounted cash flow, or an investment outcome."
      />
      <form
        className="grid gap-8 lg:grid-cols-12"
        aria-busy={phase.status === "loading"}
        onSubmit={(event) => {
          event.preventDefault();
          void calculate();
        }}
      >
        {summaryItems.length > 0 ? <ErrorSummary items={summaryItems} containerRef={errorSummary} /> : null}
        <div className="flex min-w-0 flex-col gap-6 lg:col-span-5">
          <fieldset className="flex flex-col gap-4">
            <legend className="text-[16px] leading-6 font-semibold">Facility assumptions</legend>
            <Field
              id="it_capacity_mw"
              label="IT capacity, MW"
              hint="Zero is allowed. There is no upper limit on this page."
              value={draft.itCapacityMw}
              error={fieldErrors.it_capacity_mw}
              onChange={(value) => updateDraft({ ...draft, itCapacityMw: value })}
            />
            <Field
              id="pue"
              label="PUE"
              hint="Power usage effectiveness. Must be at least 1. 1.30 is sent as 1.30."
              value={draft.pue}
              error={fieldErrors.pue}
              onChange={(value) => updateDraft({ ...draft, pue: value })}
            />
            <Field
              id="utilization"
              label="Utilization, percent"
              hint="80 means 80 percent. The request sends the share 0.80, not 80 and not a dollar amount."
              value={draft.utilizationPercent}
              error={fieldErrors.utilization}
              onChange={(value) => updateDraft({ ...draft, utilizationPercent: value })}
            />
            <Field
              id="operating_hours_per_year"
              label="Operating hours per year"
              hint="8760 is a non-leap 365 × 24 annualization. It is a scenario assumption."
              value={draft.operatingHours}
              error={fieldErrors.operating_hours_per_year}
              warning={operatingHoursWarning(draft.operatingHours)}
              onChange={(value) => updateDraft({ ...draft, operatingHours: value })}
            />
          </fieldset>
          <ScenarioEditor
            title="Baseline scenario"
            nameId="baseline_name"
            priceId="baseline_price"
            caseId="baseline_case"
            priceHint="12 means 12 cents per kilowatt-hour, not 0.12 dollars per kilowatt-hour."
            draft={draft.baseline}
            cases={availableCases}
            ridgeAvailable={ridgeAvailable}
            errors={fieldErrors}
            onChange={(patch) => updateScenario("baseline", patch)}
          />
          <ScenarioEditor
            title="Comparison scenario"
            nameId="comparison_name"
            priceId="comparison_price"
            caseId="comparison_case"
            priceHint="10 means 10 cents per kilowatt-hour, not 0.10 dollars per kilowatt-hour."
            draft={draft.comparison}
            cases={availableCases}
            ridgeAvailable={ridgeAvailable}
            errors={fieldErrors}
            onChange={(patch) => updateScenario("comparison", patch)}
          />
          <CasesNotice resource={cases} />
          <div>
            <Button type="submit" disabled={phase.status === "loading"}>
              {phase.status === "loading" ? "Calculating" : "Calculate annual energy charge"}
            </Button>
          </div>
        </div>
        <div className="min-w-0 lg:col-span-6 lg:col-start-7">
          <Results phase={phase} />
        </div>
      </form>
    </>
  );
}

function mapServerField(field: string, message: string, draft: FinanceDraft): Record<string, string> {
  if (field === "price_cents_per_kwh") {
    const errors: Record<string, string> = {};
    if (draft.baseline.source === "typed_hypothetical") {
      errors.baseline_price = message;
    }
    if (draft.comparison.source === "typed_hypothetical") {
      errors.comparison_price = message;
    }
    if (Object.keys(errors).length === 0) {
      errors.form = message;
    }
    return errors;
  }
  if (field === "case_key") {
    const errors: Record<string, string> = {};
    if (draft.baseline.source === "holdout_ridge") {
      errors.baseline_case = message;
    }
    if (draft.comparison.source === "holdout_ridge") {
      errors.comparison_case = message;
    }
    return Object.keys(errors).length > 0 ? errors : { form: message };
  }
  if (field === "scenario_name" || field === "scenarios") {
    return { baseline_name: message, comparison_name: message };
  }
  if (field === "baseline_name") {
    return { baseline_name: message };
  }
  return { [field]: message };
}

function ErrorSummary({
  items,
  containerRef,
}: {
  items: ErrorSummaryItem[];
  containerRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      ref={containerRef}
      role="alert"
      tabIndex={-1}
      data-error-summary
      className="rounded-[2px] border-2 border-ink bg-paper-raised px-4 py-4 text-ink lg:col-span-12"
    >
      <h2 className="text-[16px] leading-6 font-semibold">
        {items.length === 1 ? "Check 1 input" : `Check ${items.length} inputs`}
      </h2>
      <ul className="mt-2 flex flex-col gap-1 text-[15px] leading-6">
        {items.map((item) => {
          const { targetId } = item;
          return (
            <li key={item.key}>
              {targetId ? (
                <a
                  href={`#${targetId}`}
                  className="underline"
                  onClick={(event) => {
                    event.preventDefault();
                    document.getElementById(targetId)?.focus();
                  }}
                >
                  {item.label}: {item.message}
                </a>
              ) : (
                <span>
                  {item.label}: {item.message}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function FieldError({ id, message }: { id: string; message: string }) {
  return (
    <p id={id} className="mt-1 border-l-2 border-ink pl-2 text-[15px] leading-6 font-semibold text-ink">
      <span>Error: </span>
      {message}
    </p>
  );
}

function Field({
  id,
  label,
  hint,
  value,
  error,
  warning,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  value: string;
  error?: string;
  warning?: string | null;
  onChange: (value: string) => void;
}) {
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const warningId = `${id}-warning`;
  const describedBy = [hintId, error ? errorId : null, warning ? warningId : null].filter(Boolean).join(" ");
  return (
    <div>
      <label htmlFor={id} className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
        {label}
      </label>
      <input
        id={id}
        className={`${fieldClass(Boolean(error))} numeric mt-1`}
        inputMode="decimal"
        autoComplete="off"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <p id={hintId} className="mt-1 text-[15px] leading-6 text-ink-muted">
        {hint}
      </p>
      {error ? <FieldError id={errorId} message={error} /> : null}
      {warning ? (
        <p id={warningId} role="status" className="mt-1 border-l-2 border-line pl-2 text-[15px] leading-6 text-ink">
          <span className="font-semibold">Warning: </span>
          {warning}
        </p>
      ) : null}
    </div>
  );
}

function ScenarioEditor({
  title,
  nameId,
  priceId,
  caseId,
  priceHint,
  draft,
  cases,
  ridgeAvailable,
  errors,
  onChange,
}: {
  title: string;
  nameId: string;
  priceId: string;
  caseId: string;
  priceHint: string;
  draft: ScenarioDraft;
  cases: readonly HoldoutCase[];
  ridgeAvailable: boolean;
  errors: Record<string, string>;
  onChange: (patch: Partial<ScenarioDraft>) => void;
}) {
  const selected = findCase(cases, draft.caseId);
  const states = [...new Set(cases.map((item) => item.state_id))];
  const origins = selected
    ? [...new Set(cases.filter((item) => item.state_id === selected.state_id).map((item) => item.forecast_origin))]
    : [];
  const months = selected
    ? cases
        .filter((item) => item.state_id === selected.state_id && item.forecast_origin === selected.forecast_origin)
        .map((item) => item.target_month)
    : [];
  return (
    <fieldset className="flex flex-col gap-4 border border-line p-4">
      <legend className="px-1 text-[16px] leading-6 font-semibold">{title}</legend>
      <div>
        <label htmlFor={nameId} className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
          Scenario name
        </label>
        <input
          id={nameId}
          className={`${fieldClass(Boolean(errors[nameId]))} mt-1`}
          autoComplete="off"
          aria-invalid={errors[nameId] ? true : undefined}
          aria-describedby={errors[nameId] ? `${nameId}-error` : undefined}
          value={draft.name}
          onChange={(event) => onChange({ name: event.target.value })}
        />
        {errors[nameId] ? <FieldError id={`${nameId}-error`} message={errors[nameId]} /> : null}
      </div>
      <div role="radiogroup" aria-label={`${title} price source`} className="flex flex-col gap-2">
        <SourceRadio
          name={nameId}
          checked={draft.source === "typed_hypothetical"}
          label="Typed hypothetical cents/kWh"
          onSelect={() => onChange({ source: "typed_hypothetical" })}
        />
        <SourceRadio
          name={nameId}
          checked={draft.source === "holdout_ridge"}
          disabled={!ridgeAvailable}
          label="Closed historical Ridge holdout quote"
          onSelect={() => onChange({ source: "holdout_ridge" })}
        />
      </div>
      {draft.source === "typed_hypothetical" ? (
        <Field
          id={priceId}
          label="Energy price, cents/kWh"
          hint={priceHint}
          value={draft.priceCents}
          error={errors[priceId]}
          onChange={(value) => onChange({ priceCents: value })}
        />
      ) : (
        <CaseSelectors
          caseField={caseId}
          error={errors[caseId]}
          selected={selected}
          states={states}
          origins={origins}
          months={months}
          cases={cases}
          onSelect={(next) => onChange({ caseId: caseKeyId(next) })}
        />
      )}
    </fieldset>
  );
}

function SourceRadio({
  name,
  checked,
  disabled,
  label,
  onSelect,
}: {
  name: string;
  checked: boolean;
  disabled?: boolean;
  label: string;
  onSelect: () => void;
}) {
  return (
    <label className="flex items-start gap-2 text-[15px] leading-6">
      <input
        type="radio"
        name={name}
        className="mt-1"
        checked={checked}
        disabled={disabled}
        onChange={() => {
          if (!disabled) {
            onSelect();
          }
        }}
      />
      <span>{label}</span>
    </label>
  );
}

function CaseSelectors({
  caseField,
  error,
  selected,
  states,
  origins,
  months,
  cases,
  onSelect,
}: {
  caseField: string;
  error?: string;
  selected: HoldoutCase | null;
  states: string[];
  origins: string[];
  months: string[];
  cases: readonly HoldoutCase[];
  onSelect: (item: HoldoutCase) => void;
}) {
  function choose(stateId: string, origin: string, month: string) {
    const match = cases.find(
      (item) => item.state_id === stateId && item.forecast_origin === origin && item.target_month === month,
    );
    if (match) {
      onSelect(match);
    }
  }
  return (
    <div className="flex flex-col gap-3">
      <SelectField
        id={`${caseField}-state`}
        label="State"
        value={selected?.state_id ?? ""}
        options={states}
        errorId={error ? `${caseField}-error` : undefined}
        onChange={(stateId) => {
          const next = cases.find((item) => item.state_id === stateId);
          if (next) {
            onSelect(next);
          }
        }}
      />
      <SelectField
        id={`${caseField}-origin`}
        label="Forecast origin"
        value={selected?.forecast_origin ?? ""}
        options={origins}
        onChange={(origin) => {
          if (selected) {
            const month = cases.find((item) => item.state_id === selected.state_id && item.forecast_origin === origin);
            if (month) {
              choose(selected.state_id, origin, month.target_month);
            }
          }
        }}
      />
      <SelectField
        id={`${caseField}-month`}
        label="Target month"
        value={selected?.target_month ?? ""}
        options={months}
        onChange={(month) => {
          if (selected) {
            choose(selected.state_id, selected.forecast_origin, month);
          }
        }}
      />
      {error ? <FieldError id={`${caseField}-error`} message={error} /> : null}
      {selected ? <CaseContext item={selected} /> : null}
    </div>
  );
}

function SelectField({
  id,
  label,
  value,
  options,
  errorId,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: string[];
  errorId?: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
        {label}
      </label>
      <select
        id={id}
        className={`${fieldClass(Boolean(errorId))} mt-1`}
        aria-invalid={errorId ? true : undefined}
        aria-describedby={errorId}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

function CaseContext({ item }: { item: HoldoutCase }) {
  return (
    <div className="text-[15px] leading-6 text-ink-muted">
      <p>Closed historical Ridge prediction, {item.ridge_prediction_cents_per_kwh} cents/kWh. Not a forward-looking forecast.</p>
      <p>Observed actual on the target month, {item.actual_cents_per_kwh} cents/kWh. Historical context only.</p>
      <p>
        Seasonal-naive closed prediction, {item.seasonal_naive_prediction_cents_per_kwh} cents/kWh. Historical context
        only.
      </p>
    </div>
  );
}

function CasesNotice({ resource }: { resource: CasesResource }) {
  if (resource.state === "loading") {
    return <LoadingState label="Loading closed holdout cases." />;
  }
  if (resource.state === "error") {
    if (resource.error.kind === "connection") {
      return (
        <ErrorState
          title="Connection unavailable"
          message="Closed holdout cases did not load because the InfraLens API did not respond, so Ridge quotes are unavailable until this page is reloaded. Calculating a typed price also needs the API and works only while it responds. Your inputs stay on this page."
        />
      );
    }
    if (resource.error.code === "artifact_missing") {
      return <UnavailableState title="Ridge quotes unavailable" message={resource.error.message} />;
    }
    return <ErrorState title="Holdout cases were not readable" message={resource.error.message} />;
  }
  if (resource.data.cases.length === 0) {
    return (
      <UnavailableState
        title="Ridge quotes unavailable"
        message="The API returned no frozen holdout cases. A Ridge price is not offered in their place."
      />
    );
  }
  return (
    <p className="text-[15px] leading-6 text-ink-muted">
      {resource.data.row_count} closed holdout cases are available. {resource.data.limitations}
    </p>
  );
}

function Results({ phase }: { phase: Phase }) {
  return (
    <section aria-live="polite" aria-label="Annual energy charge" className="flex flex-col gap-4">
      <h2 className="text-[16px] leading-6 font-semibold">Annual energy charge</h2>
      {phase.status === "idle" ? (
        <p className="text-[15px] leading-6 text-ink-muted">
          Results appear after you calculate. Editing inputs does not run the calculator.
        </p>
      ) : null}
      {phase.status === "loading" ? <LoadingState label="Calculating the annual energy charge." /> : null}
      {phase.status === "stale" ? (
        <p className="text-[15px] leading-6 text-ink">Inputs changed — recalculate.</p>
      ) : null}
      {phase.status === "error" ? <FinanceError error={phase.error} /> : null}
      {phase.status === "ready" ? <FinanceReady response={phase.response} /> : null}
    </section>
  );
}

function FinanceError({ error }: { error: ApiClientError }) {
  if (error.kind === "connection") {
    return (
      <ErrorState
        title="Connection unavailable"
        message="The InfraLens API did not respond. No energy charge is shown. Your inputs are unchanged. Calculate again once the API responds."
      />
    );
  }
  if (error.code === "artifact_missing") {
    return <UnavailableState title="Ridge quotes unavailable" message={error.message} />;
  }
  if (error.kind === "invalid_body") {
    return <ErrorState title="Response was not usable" message={error.message} />;
  }
  return <ErrorState title="The calculator rejected the inputs" message={error.message} />;
}

function FinanceReady({ response }: { response: FinanceResponse }) {
  const baseline = response.scenarios.find((row) => row.scenario_name === row.baseline_scenario_name) ?? response.scenarios[0];
  const comparison = response.scenarios.find((row) => row !== baseline) ?? baseline;
  if (!baseline) {
    return <ErrorState title="Response was not usable" message="The calculator returned no scenarios." />;
  }
  const shared = baseline;
  return (
    <div className="flex flex-col gap-4">
      {response.closed_holdout_limitation ? (
        <div data-surface="finding" className="finding-panel px-4 py-4">
          <p className="text-[15px] leading-6">{response.closed_holdout_limitation}</p>
        </div>
      ) : null}
      <dl className="flex flex-col gap-3 text-[15px] leading-6">
        <ResultRow label="Facility average demand" value={`${shared.facility_average_demand_mw} ${shared.facility_average_demand_unit}`} />
        <ResultRow label="Annual consumption" value={`${shared.annual_consumption_kwh} ${shared.annual_consumption_unit}`} />
        <ResultRow label="Operating hours" value={shared.operating_hours_per_year} />
        <ResultRow
          label={`${baseline.scenario_name} price`}
          value={`${baseline.price_cents_per_kwh} ${baseline.price_unit}`}
          detail={baseline.price_label}
        />
        <ResultRow
          label={`${baseline.scenario_name} annual energy charge`}
          value={`${baseline.annual_electricity_cost_usd} ${baseline.annual_electricity_cost_unit}`}
        />
        {comparison !== baseline ? (
          <>
            <ResultRow
              label={`${comparison.scenario_name} price`}
              value={`${comparison.price_cents_per_kwh} ${comparison.price_unit}`}
              detail={comparison.price_label}
            />
            <ResultRow
              label={`${comparison.scenario_name} annual energy charge`}
              value={`${comparison.annual_electricity_cost_usd} ${comparison.annual_electricity_cost_unit}`}
            />
            <ResultRow
              label="Comparison minus baseline"
              value={`${comparison.cost_difference_vs_baseline_usd} ${comparison.cost_difference_unit}`}
              detail="The sign is the calculator's difference. A negative amount is not labeled as savings or success."
            />
          </>
        ) : null}
      </dl>
      {response.scenarios.map((row) =>
        row.model_price_warning && row.model_price_warning !== response.closed_holdout_limitation ? (
          <div key={row.scenario_name} data-surface="finding" className="finding-panel px-4 py-4">
            <p className="text-[15px] leading-6">{row.model_price_warning}</p>
          </div>
        ) : null,
      )}
      <p className="max-w-[68ch] text-[15px] leading-6 text-ink-muted">{ENERGY_CHARGE_IDENTITY}</p>
    </div>
  );
}

function ResultRow({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="border-t border-line pt-3">
      <dt className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">{label}</dt>
      <dd className="numeric mt-1 break-all text-ink">{value}</dd>
      {detail ? <dd className="mt-1 text-ink-muted">{detail}</dd> : null}
    </div>
  );
}

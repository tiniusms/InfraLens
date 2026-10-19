import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ApiClientError, createClient, type ApiClient } from "../api/client";
import { ApiProvider } from "../api/ApiProvider";
import type { EvaluationSummary, HistoryResponse, HoldoutResponse } from "../api/types";
import { ThemeProvider } from "../components/shell/ThemeProvider";
import { historyTicks, holdoutRows, holdoutScale } from "../features/electricity/series";
import { AppRoutes } from "../routes/AppRoutes";

const summary: EvaluationSummary = {
  claim_boundary: "closed_historical_evaluation",
  source_label: "docs/final_eia_holdout_oneshot.json",
  limitations: "Closed historical evaluation. Not a validated production forecast.",
  units: { mae: "cents/kWh", improvement: "percent", threshold: "percent", interval_coverage: "share" },
  executed_on: "2026-10-04",
  runner_commit: "ee5bcf6d541a1b15822f705e4099320f6f05dc32",
  summary: {
    primary_criterion: "FAIL",
    ridge_mae: "2.6384726503825626",
    paired_baseline_mae: "2.6136666666666666",
    mae_improvement_percent: "-0.9490875034777213",
    primary_threshold_percent: 10,
    primary_threshold_ratio: "0.1",
    interval_coverage: "0.0",
    nominal_interval_coverage: "0.8",
    mae_by_state: {
      MD: { n_scored: 12, paired_baseline_mae: "1", ridge_mae: "1" },
      NJ: { n_scored: 12, paired_baseline_mae: "1", ridge_mae: "1" },
      OH: { n_scored: 12, paired_baseline_mae: "1", ridge_mae: "1" },
      PA: { n_scored: 12, paired_baseline_mae: "1", ridge_mae: "1" },
      VA: { n_scored: 12, paired_baseline_mae: "1", ridge_mae: "1" },
    },
  },
};

function history(state: string, price: string): HistoryResponse {
  return {
    claim_boundary: "observed_history",
    state_id: state,
    extract_id: "eia_retail_sales_monthly_com_20260911T190524Z.parquet",
    retrieved_at: "2026-09-11T19:05:24Z",
    source_name: "EIA retail sales",
    recorded_price_units: "cents/kWh",
    unit: "cents/kWh",
    earliest_period: "2001-01",
    latest_period: "2001-02",
    extract_row_count: 2,
    returned_row_count: 2,
    limitations: "The period is the sales month, not the publication date. This chart is not a forecast.",
    series_name: "Historical observed commercial average price (cents/kWh)",
    points: [
      { state_id: state, period: "2001-01", observed_price_cents_per_kwh: price, unit: "cents/kWh", role: "observed" },
      {
        state_id: state,
        period: "2001-02",
        observed_price_cents_per_kwh: `${price}1`,
        unit: "cents/kWh",
        role: "observed",
      },
    ],
  };
}

function holdout(state: string, actual: string, withBand: boolean): HoldoutResponse {
  return {
    claim_boundary: "closed_historical_evaluation",
    state_id: state,
    limitations: "Closed historical evaluation, not a forward forecast",
    returned_row_count: 2,
    window: {
      axis: "target_month",
      origin_start: "2024-07-31",
      origin_end: "2024-08-31",
      target_start: "2025-07",
      target_end: "2025-08",
      extract_id: "eia_retail_sales_monthly_com_20260911T190524Z.parquet",
      feature_set_id: "eia_commercial_price_v1",
      evaluation_stage: "final_holdout",
      summary_source: "docs/final_eia_holdout_oneshot.json",
      interval_warning:
        "Stored Ridge residual interval, nominal 80%. Empirical coverage on this closed holdout is 0%. Not a forward-looking forecast interval.",
      empirical_interval_coverage: "0",
      empirical_interval_coverage_unit: "share",
    },
    points: [
      {
        state_id: state,
        target_month: "2025-07",
        actual: { cents_per_kwh: actual, unit: "cents/kWh", role: "observed" },
        ridge: { cents_per_kwh: "8.25", unit: "cents/kWh", role: "closed_prediction" },
        seasonal_naive: { cents_per_kwh: "7.5", unit: "cents/kWh", role: "closed_prediction" },
        interval: withBand
          ? { lower_cents_per_kwh: "6.5", upper_cents_per_kwh: "9.5", covered: false, unit: "cents/kWh" }
          : { lower_cents_per_kwh: null, upper_cents_per_kwh: null, covered: null, unit: "cents/kWh" },
        provenance: { forecast_origin: "2024-07-31" },
      },
      {
        state_id: state,
        target_month: "2025-08",
        actual: { cents_per_kwh: "10.5", unit: "cents/kWh", role: "observed" },
        ridge: { cents_per_kwh: "8.5", unit: "cents/kWh", role: "closed_prediction" },
        seasonal_naive: { cents_per_kwh: "7.75", unit: "cents/kWh", role: "closed_prediction" },
        interval: { lower_cents_per_kwh: null, upper_cents_per_kwh: "9.0", covered: null, unit: "cents/kWh" },
        provenance: { forecast_origin: "2024-08-31" },
      },
    ],
  };
}

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function renderElectricity(client: ApiClient) {
  return render(
    <ThemeProvider>
      <ApiProvider client={client}>
        <MemoryRouter initialEntries={["/electricity"]}>
          <AppRoutes />
        </MemoryRouter>
      </ApiProvider>
    </ThemeProvider>,
  );
}

describe("electricity intelligence", () => {
  it("keeps the five states on one keyboard group and ignores a stale response", async () => {
    const user = userEvent.setup();
    const jobs = new Map<string, ReturnType<typeof deferred<HistoryResponse>>>();
    const holdouts = new Map<string, ReturnType<typeof deferred<HoldoutResponse>>>();
    const client: ApiClient = {
      getStatus: () => new Promise(() => undefined),
      getEvaluationSummary: () => Promise.resolve(summary),
      getHistory: (state) => {
        const job = deferred<HistoryResponse>();
        jobs.set(state, job);
        return job.promise;
      },
      getHoldout: (state) => {
        const job = deferred<HoldoutResponse>();
        holdouts.set(state, job);
        return job.promise;
      },
      getHoldoutCases: () => new Promise(() => undefined),
      postFinanceScenarios: () => new Promise(() => undefined),
    };
    renderElectricity(client);

    expect(screen.getByRole("radio", { name: "VA" })).toHaveAttribute("aria-checked", "true");
    for (const state of ["VA", "PA", "OH", "MD", "NJ"]) {
      expect(screen.getByRole("radio", { name: state })).toBeInTheDocument();
    }

    screen.getByRole("radio", { name: "VA" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "PA" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "PA" })).toHaveFocus();

    jobs.get("PA")?.resolve(history("PA", "22.2"));
    holdouts.get("PA")?.resolve(holdout("PA", "12.2", true));
    expect(await screen.findByText("22.2")).toBeInTheDocument();
    expect(screen.getByText("Showing PA.")).toBeInTheDocument();

    jobs.get("VA")?.resolve(history("VA", "11.1"));
    holdouts.get("VA")?.resolve(holdout("VA", "11.1", true));
    expect(screen.queryByText("11.1")).not.toBeInTheDocument();
    expect(screen.getByText("22.2")).toBeInTheDocument();

    const prices = { OH: "33.3", MD: "44.4", NJ: "55.5" } as const;
    for (const state of ["OH", "MD", "NJ"] as const) {
      await user.click(screen.getByRole("radio", { name: state }));
      jobs.get(state)?.resolve(history(state, prices[state]));
      holdouts.get(state)?.resolve(holdout(state, prices[state], true));
      const historyTable = await screen.findByRole("region", { name: "Observed price table" });
      expect(within(historyTable).getAllByText(state).length).toBeGreaterThan(0);
      expect(within(historyTable).getByText(prices[state])).toBeInTheDocument();
      expect(screen.getByText(`Showing ${state}.`)).toBeInTheDocument();
    }
  });

  it("plots target month, stored bounds, roles, and the frozen criterion", async () => {
    const client: ApiClient = {
      getStatus: () => new Promise(() => undefined),
      getEvaluationSummary: () => Promise.resolve(summary),
      getHistory: (state) => Promise.resolve(history(state, "11.1")),
      getHoldout: (state) => Promise.resolve(holdout(state, "13.25", true)),
      getHoldoutCases: () => new Promise(() => undefined),
      postFinanceScenarios: () => new Promise(() => undefined),
    };
    renderElectricity(client);

    expect(await screen.findByRole("heading", { name: "Primary criterion: FAIL" })).toBeInTheDocument();
    expect(screen.getByText(/75–85% band is a diagnostic/)).toBeInTheDocument();
    expect(screen.getByText(/not the primary relative-improvement gate of \+10 percent/)).toBeInTheDocument();
    expect(screen.getByText(/nominal 80%/)).toBeInTheDocument();
    expect(screen.getByText(/stored share 0.0/)).toBeInTheDocument();
    expect(screen.getByText(/Chart empirical interval coverage, share: 0/)).toBeInTheDocument();

    const chart = document.querySelector("[data-chart='holdout']");
    expect(chart).toHaveAttribute("data-x", "target_month");
    expect(document.querySelector("[data-chart='history']")).toHaveAttribute("data-markers", "none");
    expect(document.querySelector("[data-series='actual']")).toHaveAttribute("data-stroke", "var(--series-actual)");
    expect(document.querySelector("[data-series='ridge']")).toHaveAttribute("data-dash", "6 4");
    expect(document.querySelector("[data-series='naive']")).toHaveAttribute("data-dash", "1.5 4");
    expect(document.querySelector("[data-series='band']")).toBeInTheDocument();

    const table = screen.getByRole("region", { name: "Closed holdout table" });
    const month = within(table).getByRole("row", { name: /2025-07/ });
    expect(within(month).getByRole("rowheader", { name: "2025-07" })).toBeInTheDocument();
    expect(within(month).getByText("2024-07-31")).toBeInTheDocument();
    expect(within(month).getByText("observed")).toBeInTheDocument();
    expect(within(month).getAllByText("closed_prediction")).toHaveLength(2);
    expect(within(month).getByText("6.5")).toBeInTheDocument();
    expect(within(month).getByText("9.5")).toBeInTheDocument();

    const openBound = within(table).getByRole("row", { name: /2025-08/ });
    expect(within(openBound).getAllByText("Not supplied").length).toBeGreaterThan(0);
    expect(screen.getByText(/The period is the sales month, not the publication date/)).toBeInTheDocument();
    expect(screen.getByText(/eia_commercial_price_v1/)).toBeInTheDocument();
    expect(screen.getByText(/final_holdout/)).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "dark" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.querySelector("[data-series='ridge']")).toHaveAttribute("data-stroke", "var(--series-ridge)");
    expect(document.querySelector("[data-series='naive']")).toHaveAttribute("data-stroke", "var(--series-naive)");
  });

  it("spaces long history ticks so the final month stays readable", () => {
    const periods = ["2001-01", "2005-01", "2010-01", "2015-01", "2020-01", "2025-01", "2026-06", "2026-05", "2026-04"];
    expect(historyTicks(periods)).toEqual(["2001-01", "2005-01", "2010-01", "2015-01", "2020-01", "2026-04"]);
  });

  it("does not invent an interval when either stored bound is missing", () => {
    const rows = holdoutRows(holdout("VA", "13.25", false));
    expect(rows[0]?.band).toBeNull();
    expect(rows[1]?.band).toBeNull();
    expect(rows[0]?.targetMonth).toBe("2025-07");
    expect(rows[0]?.forecastOrigin).not.toBe(rows[0]?.targetMonth);
    const scale = holdoutScale(rows);
    expect(scale.domain[0]).toBeGreaterThan(0);
    expect(scale.domain[0]).toBeLessThan(7.5);
    expect(scale.domain[1]).toBeGreaterThan(13.25);
    expect(scale.ticks.every((tick) => Number.isInteger(tick * 2))).toBe(true);
    const withBand = holdoutScale(holdoutRows(holdout("VA", "13.25", true)));
    expect(withBand.domain[0]).toBeLessThan(6.5);
  });

  it("shows a missing history without hiding the holdout", async () => {
    const client: ApiClient = {
      getStatus: () => new Promise(() => undefined),
      getEvaluationSummary: () => Promise.resolve(summary),
      getHistory: () =>
        Promise.reject(new ApiClientError("http", "EIA commercial price history is not on this machine.", 404, "artifact_missing")),
      getHoldout: (state) => Promise.resolve(holdout(state, "13.25", true)),
      getHoldoutCases: () => new Promise(() => undefined),
      postFinanceScenarios: () => new Promise(() => undefined),
    };
    renderElectricity(client);
    expect(await screen.findByRole("heading", { name: "Price history unavailable" })).toBeInTheDocument();
    expect(await screen.findByText("13.25")).toBeInTheDocument();
    expect(screen.queryByText("11.1")).not.toBeInTheDocument();
  });

  it("shows a missing holdout without hiding history", async () => {
    const client: ApiClient = {
      getStatus: () => new Promise(() => undefined),
      getEvaluationSummary: () => Promise.resolve(summary),
      getHistory: (state) => Promise.resolve(history(state, "11.1")),
      getHoldout: () =>
        Promise.reject(
          new ApiClientError("http", "The frozen holdout case file is not on this machine.", 404, "artifact_missing"),
        ),
      getHoldoutCases: () => new Promise(() => undefined),
      postFinanceScenarios: () => new Promise(() => undefined),
    };
    renderElectricity(client);
    expect(await screen.findByRole("heading", { name: "Closed holdout unavailable" })).toBeInTheDocument();
    expect(await screen.findByText("11.1")).toBeInTheDocument();
    expect(screen.queryByText("13.25")).not.toBeInTheDocument();
  });

  it("does not show series or the finding wash when the API cannot be read", async () => {
    const error = new ApiClientError("connection", "The InfraLens API did not respond.");
    const client: ApiClient = {
      getStatus: () => Promise.reject(error),
      getEvaluationSummary: () => Promise.reject(error),
      getHistory: () => Promise.reject(error),
      getHoldout: () => Promise.reject(error),
      getHoldoutCases: () => new Promise(() => undefined),
      postFinanceScenarios: () => new Promise(() => undefined),
    };
    renderElectricity(client);
    expect(await screen.findAllByRole("heading", { name: "Connection unavailable" })).toHaveLength(3);
    expect(screen.queryByText("FAIL")).not.toBeInTheDocument();
    expect(screen.queryByText("11.1")).not.toBeInTheDocument();
    expect(screen.queryByText("13.25")).not.toBeInTheDocument();
    expect(document.querySelector("[data-surface='finding']")).toBeNull();
    expect(document.querySelector("[data-chart]")).toBeNull();
  });

  it("rejects a holdout payload whose axis is not target month", async () => {
    const fetchImpl = async () =>
      new Response(
        JSON.stringify({
          ...holdout("VA", "13.25", true),
          window: { ...holdout("VA", "13.25", true).window, axis: "forecast_origin" },
        }),
        { status: 200 },
      );
    const client = createClient({ baseUrl: "http://127.0.0.1:8000", fetchImpl });
    await expect(client.getHoldout("VA")).rejects.toMatchObject({ kind: "invalid_body" });
  });

  it("requests the EIA history and holdout paths", async () => {
    const urls: string[] = [];
    const fetchImpl = async (input: RequestInfo | URL) => {
      const url = String(input);
      urls.push(url);
      if (url.includes("/api/v1/eia/history")) {
        return new Response(JSON.stringify(history("OH", "4.5")), { status: 200 });
      }
      return new Response(JSON.stringify(holdout("OH", "4.5", true)), { status: 200 });
    };
    const client = createClient({ baseUrl: "http://127.0.0.1:8000", fetchImpl });
    await client.getHistory("OH");
    await client.getHoldout("OH");
    expect(urls).toContain("http://127.0.0.1:8000/api/v1/eia/history?state_id=OH");
    expect(urls).toContain("http://127.0.0.1:8000/api/v1/eia/holdout?state_id=OH");
  });
});

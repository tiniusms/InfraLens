import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ApiClientError, createClient, type ApiClient } from "../api/client";
import { ApiProvider } from "../api/ApiProvider";
import type { FinanceRequest, FinanceResponse, HoldoutCasesResponse } from "../api/types";
import { ThemeProvider } from "../components/shell/ThemeProvider";
import { INITIAL_DRAFT, buildFinanceRequest, percentToShare } from "../features/finance/request";
import { AppRoutes } from "../routes/AppRoutes";

const RIDGE_WARNING =
  "This price is a model-derived EIA scenario, not a validated investment forecast. The frozen 60-case holdout primary criterion is FAIL. Both Ridge and the seasonal-naive baseline systematically underpredicted. Empirical interval coverage was 0%.";

const cases: HoldoutCasesResponse = {
  claim_boundary: "closed_historical_evaluation",
  limitations: "Closed historical evaluation. Not a validated production forecast and not an investment recommendation.",
  unit: "cents/kWh",
  row_count: 1,
  cases: [
    {
      state_id: "VA",
      forecast_origin: "2024-07-31",
      target_month: "2025-07",
      ridge_prediction_cents_per_kwh: "8.633043510306178",
      actual_cents_per_kwh: "10.21",
      seasonal_naive_prediction_cents_per_kwh: "8.84",
      unit: "cents/kWh",
      ridge_role: "closed_prediction",
      actual_role: "observed",
    },
  ],
};

function scenarioResult(
  name: string,
  price: string,
  cost: string,
  delta: string,
  derived = false,
  consumption = "455520000",
): FinanceResponse["scenarios"][number] {
  return {
    scenario_name: name,
    price_source: derived ? "holdout_ridge" : "typed_hypothetical",
    price_label: derived
      ? "Closed holdout Ridge prediction. Not a forward-looking forecast."
      : "Typed hypothetical energy price. Not a model forecast.",
    claim_boundary: "hypothetical_energy_cost",
    it_capacity_mw: "50",
    pue: "1.3",
    utilization: "0.8",
    operating_hours_per_year: "8760",
    facility_average_demand_mw: "52",
    facility_average_demand_unit: "MW",
    annual_consumption_kwh: consumption,
    annual_consumption_unit: "kWh",
    price_cents_per_kwh: price,
    price_unit: "cents/kWh",
    annual_electricity_cost_usd: cost,
    annual_electricity_cost_unit: "USD",
    baseline_scenario_name: "Baseline",
    cost_difference_vs_baseline_usd: delta,
    cost_difference_unit: "USD",
    model_derived_eia_price: derived,
    model_price_warning: derived ? RIDGE_WARNING : null,
  };
}

function typedResponse(
  cost = "54662400",
  comparisonCost = "45552000",
  delta = "-9110400",
  consumption = "455520000",
): FinanceResponse {
  return {
    claim_boundary: "hypothetical_energy_cost",
    closed_holdout_claim_boundary: null,
    closed_holdout_limitation: null,
    scenarios: [
      scenarioResult("Baseline", "12", cost, "0", false, consumption),
      scenarioResult("Comparison", "10", comparisonCost, delta, false, consumption),
    ],
  };
}

function renderFinance(client: ApiClient) {
  return render(
    <ThemeProvider>
      <ApiProvider client={client}>
        <MemoryRouter initialEntries={["/finance"]}>
          <AppRoutes />
        </MemoryRouter>
      </ApiProvider>
    </ThemeProvider>,
  );
}

function clientWith(
  post: ApiClient["postFinanceScenarios"],
  holdout: ApiClient["getHoldoutCases"] = () =>
    Promise.reject(
      new ApiClientError(
        "http",
        "Frozen holdout cases are not available. A Ridge price cannot be supplied in their place.",
        404,
        "artifact_missing",
      ),
    ),
): ApiClient {
  return {
    getStatus: () => new Promise(() => undefined),
    getEvaluationSummary: () => new Promise(() => undefined),
    getHistory: () => new Promise(() => undefined),
    getHoldout: () => new Promise(() => undefined),
    getHoldoutCases: holdout,
    postFinanceScenarios: post,
  };
}

describe("financial scenario studio", () => {
  it("converts 80 percent to the share 0.80 and keeps prices in cents", () => {
    expect(percentToShare("80")).toBe("0.80");
    expect(percentToShare("8")).toBe("0.08");
    expect(percentToShare("100")).toBe("1.00");
    const built = buildFinanceRequest(INITIAL_DRAFT, []);
    expect(built.errors).toEqual({});
    expect(built.request).toEqual({
      it_capacity_mw: "50",
      pue: "1.30",
      utilization: "0.80",
      operating_hours_per_year: "8760",
      baseline_name: "Baseline",
      scenarios: [
        { name: "Baseline", source: "typed_hypothetical", price_cents_per_kwh: "12" },
        { name: "Comparison", source: "typed_hypothetical", price_cents_per_kwh: "10" },
      ],
    });
    expect(JSON.stringify(built.request)).not.toContain("0.12");
    expect(JSON.stringify(built.request)).not.toContain("model_derived");
  });

  it("shows the authoritative 50 MW charge and does not attach a Ridge warning to typed prices", async () => {
    const user = userEvent.setup();
    const posts: FinanceRequest[] = [];
    renderFinance(
      clientWith(async (body) => {
        posts.push(body);
        return typedResponse();
      }),
    );

    expect(await screen.findByRole("heading", { name: "Ridge quotes unavailable" })).toBeInTheDocument();
    for (const radio of screen.getAllByRole("radio", { name: "Closed historical Ridge holdout quote" })) {
      expect(radio).toBeDisabled();
    }
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));

    expect(await screen.findByText("455520000 kWh")).toBeInTheDocument();
    expect(screen.getByText("54662400 USD")).toBeInTheDocument();
    expect(screen.getByText("-9110400 USD")).toBeInTheDocument();
    expect(screen.queryByText(/FAIL/)).not.toBeInTheDocument();
    expect(posts[0]?.utilization).toBe("0.80");
    expect(posts[0]?.scenarios.map((item) => item.price_cents_per_kwh)).toEqual(["12", "10"]);
  });

  it("displays a non-matching cost instead of calculating one in the browser", async () => {
    const user = userEvent.setup();
    renderFinance(clientWith(async () => typedResponse("1", "1", "0")));
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    const results = await screen.findByRole("region", { name: "Annual energy charge" });
    expect(within(results).getAllByText("1 USD").length).toBeGreaterThan(0);
    expect(within(results).queryByText("54662400 USD")).not.toBeInTheDocument();
  });

  it("sends a real case key and shows the Ridge warning only from the response", async () => {
    const user = userEvent.setup();
    const posts: FinanceRequest[] = [];
    renderFinance(
      clientWith(
        async (body) => {
          posts.push(body);
          return {
            claim_boundary: "hypothetical_energy_cost",
            closed_holdout_claim_boundary: "closed_historical_evaluation",
            closed_holdout_limitation: RIDGE_WARNING,
            scenarios: [
              scenarioResult("Baseline", "12", "54662400", "0"),
              scenarioResult("Comparison", "8.633043510306178", "39320000", "-15342400", true),
            ],
          };
        },
        async () => cases,
      ),
    );

    const comparison = await screen.findByRole("group", { name: "Comparison scenario" });
    await user.click(within(comparison).getByRole("radio", { name: "Closed historical Ridge holdout quote" }));
    expect(within(comparison).getByText(/Closed historical Ridge prediction, 8.633043510306178/)).toBeInTheDocument();
    expect(within(comparison).getByText(/Observed actual on the target month, 10.21/)).toBeInTheDocument();
    expect(within(comparison).getByText(/Seasonal-naive closed prediction, 8.84/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));

    expect(posts[0]?.scenarios[1]).toEqual({
      name: "Comparison",
      source: "holdout_ridge",
      case_key: { state_id: "VA", forecast_origin: "2024-07-31", target_month: "2025-07" },
    });
    expect(JSON.stringify(posts[0])).not.toContain("model_derived");
    expect(await screen.findByText(RIDGE_WARNING)).toBeInTheDocument();
    expect(screen.getAllByText(RIDGE_WARNING)).toHaveLength(1);
  });

  it("keeps typed scenarios available when holdout cases are missing", async () => {
    const user = userEvent.setup();
    let posted = false;
    renderFinance(
      clientWith(async () => {
        posted = true;
        return typedResponse();
      }),
    );
    expect(await screen.findByText(/A Ridge price cannot be supplied/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    expect(await screen.findByText("54662400 USD")).toBeInTheDocument();
    expect(posted).toBe(true);
  });

  it("drops a late response after the inputs change and ignores an older request", async () => {
    const user = userEvent.setup();
    const resolvers: Array<(value: FinanceResponse) => void> = [];
    renderFinance(
      clientWith(
        () =>
          new Promise((resolve) => {
            resolvers.push(resolve);
          }),
      ),
    );
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    await user.clear(screen.getByLabelText("IT capacity, MW"));
    await user.type(screen.getByLabelText("IT capacity, MW"), "60");
    expect(screen.getByText("Inputs changed — recalculate.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    resolvers[1]?.(typedResponse("22", "22", "0", "1"));
    resolvers[0]?.(typedResponse());
    expect((await screen.findAllByText("22 USD")).length).toBeGreaterThan(0);
    expect(screen.queryByText("54662400 USD")).not.toBeInTheDocument();
    expect(screen.queryByText("455520000 kWh")).not.toBeInTheDocument();
  });

  it("maps a validation error onto the field and allows a retry", async () => {
    const user = userEvent.setup();
    let attempt = 0;
    renderFinance(
      clientWith(async () => {
        attempt += 1;
        if (attempt === 1) {
          throw new ApiClientError("http", "pue must be at least 1.", 422, "validation_error", "pue");
        }
        return typedResponse();
      }),
    );
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    expect(screen.getByLabelText("PUE")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getAllByText("pue must be at least 1.").length).toBeGreaterThan(0);
    expect(screen.queryByText("54662400 USD")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    expect(await screen.findByText("54662400 USD")).toBeInTheDocument();
  });

  it("does not post or show a charge when the scenario name is empty", async () => {
    const user = userEvent.setup();
    const post = vi.fn();
    renderFinance(clientWith(post));
    await user.clear(screen.getByLabelText("Scenario name", { selector: "#baseline_name" }));
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    expect(screen.getByText("Enter a baseline scenario name.")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByText("54662400 USD")).not.toBeInTheDocument();
  });

  it("fails closed when the finance payload does not match the contract", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/eia/holdout/cases")) {
        return new Response(
          JSON.stringify({
            code: "artifact_missing",
            message: "Frozen holdout cases are not available.",
            artifact_id: "holdout_cases",
          }),
          { status: 404 },
        );
      }
      if (init?.method === "POST") {
        return new Response(JSON.stringify({ claim_boundary: "nope", scenarios: [] }), { status: 200 });
      }
      return new Response("no", { status: 500 });
    });
    renderFinance(createClient({ baseUrl: "http://127.0.0.1:8000", fetchImpl }));
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    expect(await screen.findByText("The response did not match the API contract. Figures are not shown.")).toBeInTheDocument();
    expect(screen.queryByText("54662400 USD")).not.toBeInTheDocument();
    expect(screen.queryByText(/FAIL/)).not.toBeInTheDocument();
  });
});

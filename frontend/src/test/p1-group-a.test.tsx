import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClientError, type ApiClient } from "../api/client";
import { ApiProvider } from "../api/ApiProvider";
import type { FinanceRequest, FinanceResponse, HistoryResponse } from "../api/types";
import { ThemeProvider } from "../components/shell/ThemeProvider";
import { AppRoutes } from "../routes/AppRoutes";

const originalMatchMedia = window.matchMedia;

afterEach(() => {
  Object.defineProperty(window, "matchMedia", { writable: true, configurable: true, value: originalMatchMedia });
});

/** A viewport whose 1024 px media query can be crossed during a test. */
function installViewport(initialDesktop: boolean) {
  let desktop = initialDesktop;
  const listeners = new Set<() => void>();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      get matches() {
        return query.includes("min-width: 1024px") ? desktop : false;
      },
      media: query,
      onchange: null,
      addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
  return (next: boolean) => {
    act(() => {
      desktop = next;
      listeners.forEach((listener) => listener());
    });
  };
}

function scenario(name: string, price: string, cost: string, delta: string): FinanceResponse["scenarios"][number] {
  return {
    scenario_name: name,
    price_source: "typed_hypothetical",
    price_label: "Typed hypothetical energy price. Not a model forecast.",
    claim_boundary: "hypothetical_energy_cost",
    it_capacity_mw: "300",
    pue: "1.3",
    utilization: "0.8",
    operating_hours_per_year: "8760",
    facility_average_demand_mw: "312",
    facility_average_demand_unit: "MW",
    annual_consumption_kwh: "2733120000",
    annual_consumption_unit: "kWh",
    price_cents_per_kwh: price,
    price_unit: "cents/kWh",
    annual_electricity_cost_usd: cost,
    annual_electricity_cost_unit: "USD",
    baseline_scenario_name: "Baseline",
    cost_difference_vs_baseline_usd: delta,
    cost_difference_unit: "USD",
    model_derived_eia_price: false,
    model_price_warning: null,
  };
}

const financeResponse: FinanceResponse = {
  claim_boundary: "hypothetical_energy_cost",
  closed_holdout_claim_boundary: null,
  closed_holdout_limitation: null,
  scenarios: [
    scenario("Baseline", "12", "327974400", "0"),
    scenario("Comparison", "10", "273312000", "-54662400"),
  ],
};

const connectionError = () => new ApiClientError("connection", "The InfraLens API did not respond.");

function client(overrides: Partial<ApiClient> = {}): ApiClient {
  const pending = () => new Promise<never>(() => undefined);
  return {
    getStatus: pending,
    getEvaluationSummary: pending,
    getHistory: pending as () => Promise<HistoryResponse>,
    getHoldout: pending,
    getHoldoutCases: () =>
      Promise.reject(new ApiClientError("http", "Frozen holdout cases are not available.", 404, "artifact_missing")),
    postFinanceScenarios: () => Promise.resolve(financeResponse),
    getPjmCatalog: pending,
    getPjmScreen: pending,
    ...overrides,
  };
}

function renderAt(path: string, api: ApiClient) {
  return render(
    <ThemeProvider>
      <ApiProvider client={api}>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </ApiProvider>
    </ThemeProvider>,
  );
}

function mobileHeader(): HTMLElement {
  const header = screen.getByRole("button", { name: "Sections" }).closest("header");
  if (!header) {
    throw new Error("The mobile header is missing.");
  }
  return header;
}

describe("US-01: crossing the 1024 px breakpoint", () => {
  it.each([
    ["desktop to mobile", true],
    ["mobile to desktop", false],
  ])("keeps the Electricity state and does not refetch, %s", async (_label, startDesktop) => {
    const cross = installViewport(startDesktop);
    const user = userEvent.setup();
    const getHistory = vi.fn(() => new Promise<HistoryResponse>(() => undefined));
    renderAt("/electricity", client({ getHistory }));

    await user.click(screen.getByRole("radio", { name: "MD" }));
    const main = screen.getByRole("main");
    const requests = getHistory.mock.calls.length;

    cross(!startDesktop);
    expect(screen.getByRole("radio", { name: "MD" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("main")).toBe(main);

    cross(startDesktop);
    expect(screen.getByRole("radio", { name: "MD" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("main")).toBe(main);
    expect(getHistory).toHaveBeenCalledTimes(requests);
  });

  it.each([
    ["desktop to mobile", true],
    ["mobile to desktop", false],
  ])("keeps Finance inputs and the result without a second POST, %s", async (_label, startDesktop) => {
    const cross = installViewport(startDesktop);
    const user = userEvent.setup();
    const post = vi.fn(() => Promise.resolve(financeResponse));
    renderAt("/finance", client({ postFinanceScenarios: post }));

    await user.clear(screen.getByLabelText("IT capacity, MW"));
    await user.type(screen.getByLabelText("IT capacity, MW"), "300");
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    expect(await screen.findByText("327974400 USD")).toBeInTheDocument();

    for (const desktop of [!startDesktop, startDesktop]) {
      cross(desktop);
      expect(screen.getByLabelText("IT capacity, MW")).toHaveValue("300");
      expect(screen.getByText("327974400 USD")).toBeInTheDocument();
    }
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("does not reopen the Sections sheet after a round trip through desktop", async () => {
    const cross = installViewport(false);
    const user = userEvent.setup();
    renderAt("/electricity", client());

    await user.click(screen.getByRole("button", { name: "Sections" }));
    expect(await screen.findByRole("dialog", { name: "Sections" })).toBeInTheDocument();

    cross(true);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    cross(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sections" })).toHaveAttribute("aria-expanded", "false");
  });
});

describe("ST-01: unknown routes", () => {
  it.each(["/no-such-route", "/finance/nope"])("renders not found inside the shell at %s", async (path) => {
    installViewport(true);
    const user = userEvent.setup();
    renderAt(path, client());

    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(document.title).toBe("Page not found · InfraLens");
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: "Financial Scenario Studio" })).not.toHaveAttribute("aria-current");

    await user.click(screen.getByRole("link", { name: "Go to Overview" }));
    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
  });

  it("labels the mobile section correctly for unknown and case-variant routes", () => {
    installViewport(false);
    const unknown = renderAt("/no-such-route", client());
    expect(within(mobileHeader()).getByText("Page not found")).toBeInTheDocument();
    unknown.unmount();

    renderAt("/FINANCE", client());
    expect(screen.getByRole("heading", { level: 1, name: "Financial Scenario Studio" })).toBeInTheDocument();
    expect(within(mobileHeader()).getByText("Financial Scenario Studio")).toBeInTheDocument();
  });
});

describe("US-02: operating hours above a leap year", () => {
  it("warns above 8,784 and still sends the value unchanged", async () => {
    installViewport(true);
    const user = userEvent.setup();
    const posts: FinanceRequest[] = [];
    renderAt(
      "/finance",
      client({
        postFinanceScenarios: (body) => {
          posts.push(body);
          return Promise.resolve(financeResponse);
        },
      }),
    );
    const hours = screen.getByLabelText("Operating hours per year");

    await user.clear(hours);
    await user.type(hours, "8784");
    expect(screen.queryByText(/above 8,784/)).not.toBeInTheDocument();

    await user.clear(hours);
    await user.type(hours, "9000");
    const warning = screen.getByText(/above 8,784/);
    expect(hours.getAttribute("aria-describedby")).toContain(warning.id);
    expect(hours).not.toHaveAttribute("aria-invalid");

    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    expect(await screen.findByText("327974400 USD")).toBeInTheDocument();
    expect(posts).toHaveLength(1);
    expect(posts[0]?.operating_hours_per_year).toBe("9000");
  });
});

describe("US-03: validation errors", () => {
  it("shows a linked summary, distinguishes errors from hints, and focuses the first error", async () => {
    installViewport(true);
    const user = userEvent.setup();
    const post = vi.fn(() => Promise.resolve(financeResponse));
    renderAt("/finance", client({ postFinanceScenarios: post }));

    await user.clear(screen.getByLabelText("PUE"));
    await user.type(screen.getByLabelText("PUE"), "0.9");
    await user.clear(screen.getByLabelText("Energy price, cents/kWh", { selector: "#comparison_price" }));
    await user.type(screen.getByLabelText("Energy price, cents/kWh", { selector: "#comparison_price" }), "-5");
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));

    const summary = screen.getByRole("alert");
    expect(within(summary).getByRole("heading", { name: "Check 2 inputs" })).toBeInTheDocument();
    const links = within(summary).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["#pue", "#comparison_price"]);
    expect(screen.getByLabelText("PUE")).toHaveFocus();
    expect(post).not.toHaveBeenCalled();

    const error = document.getElementById("pue-error");
    const hint = document.getElementById("pue-hint");
    expect(error).toHaveTextContent("Error: PUE must be at least 1.");
    expect(error?.className).toContain("font-semibold");
    expect(hint?.className).not.toContain("font-semibold");
    expect(screen.getByLabelText("PUE").className).toContain("border-ink");

    await user.click(links[1] as HTMLElement);
    expect(screen.getByLabelText("Energy price, cents/kWh", { selector: "#comparison_price" })).toHaveFocus();
  });

  it("focuses a field rejected by the server", async () => {
    installViewport(true);
    const user = userEvent.setup();
    renderAt(
      "/finance",
      client({
        postFinanceScenarios: () =>
          Promise.reject(new ApiClientError("http", "pue must be at least 1.", 422, "validation_error", "pue")),
      }),
    );
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    expect(await screen.findByRole("heading", { name: "Check 1 input" })).toBeInTheDocument();
    expect(screen.getByLabelText("PUE")).toHaveFocus();
  });
});

describe("CT-04: Finance with the API down", () => {
  it("states what needs the API, shows no charge, keeps inputs, and recovers typed prices", async () => {
    installViewport(true);
    const user = userEvent.setup();
    let apiUp = false;
    const getHoldoutCases = vi.fn(() => Promise.reject(connectionError()));
    renderAt(
      "/finance",
      client({
        getHoldoutCases,
        postFinanceScenarios: () => (apiUp ? Promise.resolve(financeResponse) : Promise.reject(connectionError())),
      }),
    );

    expect(await screen.findByText(/Ridge quotes are unavailable until this page is reloaded/)).toBeInTheDocument();
    expect(screen.getByText(/Calculating a typed price also needs the API/)).toBeInTheDocument();
    expect(screen.queryByText(/can still be calculated/)).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("Closed historical Ridge holdout quote")[0]).toBeDisabled();

    await user.clear(screen.getByLabelText("IT capacity, MW"));
    await user.type(screen.getByLabelText("IT capacity, MW"), "300");
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    expect(await screen.findByText(/No energy charge is shown/)).toBeInTheDocument();
    expect(screen.queryByText("327974400 USD")).not.toBeInTheDocument();
    expect(screen.getByLabelText("IT capacity, MW")).toHaveValue("300");

    apiUp = true;
    await user.click(screen.getByRole("button", { name: "Calculate annual energy charge" }));
    expect(await screen.findByText("327974400 USD")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Closed historical Ridge holdout quote")[0]).toBeDisabled();
    expect(getHoldoutCases).toHaveBeenCalledTimes(1);
  });
});

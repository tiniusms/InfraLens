import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { ApiClient } from "../api/client";
import { ApiClientError } from "../api/client";
import { ApiProvider } from "../api/ApiProvider";
import type { ArtifactReport, EvaluationSummary, StatusResponse } from "../api/types";
import { ThemeProvider } from "../components/shell/ThemeProvider";
import { shareToPercentText } from "../lib/format";
import { AppRoutes } from "../routes/AppRoutes";

const frozenSummary: EvaluationSummary = {
  claim_boundary: "closed_historical_evaluation",
  source_label: "docs/final_eia_holdout_oneshot.json",
  limitations: "Closed historical evaluation. Not a validated production forecast and not an investment recommendation.",
  units: {
    mae: "cents/kWh",
    improvement: "percent",
    threshold: "percent",
    interval_coverage: "share",
  },
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
      MD: { n_scored: 12, paired_baseline_mae: "3.608333333333333", ridge_mae: "3.385474686685759" },
      NJ: { n_scored: 12, paired_baseline_mae: "3.178333333333333", ridge_mae: "2.726084766988411" },
      OH: { n_scored: 12, paired_baseline_mae: "2.1574999999999998", ridge_mae: "2.3859318296585297" },
      PA: { n_scored: 12, paired_baseline_mae: "2.3425000000000007", ridge_mae: "2.344845390825365" },
      VA: { n_scored: 12, paired_baseline_mae: "1.7816666666666672", ridge_mae: "2.3500265777547478" },
    },
  },
};

function artifact(
  artifact_id: ArtifactReport["artifact_id"],
  status: ArtifactReport["status"],
  validation: ArtifactReport["validation"],
): ArtifactReport {
  return { artifact_id, status, validation, detail: null };
}

const mixedStatus: StatusResponse = {
  claim_boundary: null,
  prototype_caption: "Historical evaluation and infrastructure-screening prototype. Not a live production forecasting system.",
  presence_mode: "portable_summary",
  presence_mode_meaning: "file_existence_only",
  artifacts: [
    artifact("committed_summary", "valid", "validated"),
    artifact("price_history", "present_unvalidated", "deferred"),
    artifact("holdout_cases", "missing", "not_applicable"),
    artifact("pjm_2025_tables", "invalid", "failed"),
    artifact("pjm_2026_tables", "missing", "not_applicable"),
  ],
};

function readyClient(): ApiClient {
  return {
    getStatus: () => Promise.resolve(mixedStatus),
    getEvaluationSummary: () => Promise.resolve(frozenSummary),
    getHistory: () => new Promise(() => undefined),
    getHoldout: () => new Promise(() => undefined),
    getHoldoutCases: () => new Promise(() => undefined),
    postFinanceScenarios: () => new Promise(() => undefined),
    getPjmCatalog: () => new Promise(() => undefined),
    getPjmScreen: () => new Promise(() => undefined),
  };
}

function failedClient(error: ApiClientError): ApiClient {
  return {
    getStatus: () => Promise.reject(error),
    getEvaluationSummary: () => Promise.reject(error),
    getHistory: () => Promise.reject(error),
    getHoldout: () => Promise.reject(error),
    getHoldoutCases: () => Promise.reject(error),
    postFinanceScenarios: () => Promise.reject(error),
    getPjmCatalog: () => Promise.reject(error),
    getPjmScreen: () => Promise.reject(error),
  };
}

function setDesktop(desktop: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes("min-width: 1024px") ? desktop : false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

function renderAt(path: string, client: ApiClient = readyClient()) {
  return render(
    <ThemeProvider>
      <ApiProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </ApiProvider>
    </ThemeProvider>,
  );
}

describe("navigation", () => {
  it("renders the four routes from the sidebar", async () => {
    setDesktop(true);
    const user = userEvent.setup();
    renderAt("/electricity");

    expect(screen.getByRole("heading", { name: "Electricity Intelligence" })).toBeInTheDocument();
    expect(document.title).toBe("Electricity Intelligence · InfraLens");

    await user.click(screen.getByRole("link", { name: "Financial Scenario Studio" }));
    expect(screen.getByRole("heading", { name: "Financial Scenario Studio" })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "PJM Infrastructure Explorer" }));
    expect(screen.getByRole("heading", { name: "PJM Infrastructure Explorer" })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Overview" }));
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  });

  it("makes the state MAE table a labeled keyboard scroll region", async () => {
    setDesktop(false);
    renderAt("/");
    const region = await screen.findByRole("region", { name: "State MAE" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(screen.getByText("Scroll horizontally to read every column")).toBeInTheDocument();
    expect(within(region).getByRole("columnheader", { name: "Seasonal-naive MAE" })).toBeInTheDocument();
    expect(within(region).getByText("1.7816666666666672")).toBeInTheDocument();
    expect(within(region).getByText("2.3500265777547478")).toBeInTheDocument();
    region.focus();
    expect(region).toHaveFocus();
  });

  it("moves focus into the section sheet and returns it on Escape", async () => {
    setDesktop(false);
    const user = userEvent.setup();
    renderAt("/finance");

    const opener = screen.getByRole("button", { name: "Sections" });
    opener.focus();
    await user.click(opener);

    const dialog = await screen.findByRole("dialog", { name: "Sections" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("link", { name: "Electricity Intelligence" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});

describe("theme", () => {
  it("switches the document theme and records both token sets", async () => {
    setDesktop(true);
    document.documentElement.dataset.theme = "light";
    const user = userEvent.setup();
    renderAt("/pjm");

    const light = screen.getByRole("button", { name: "light" });
    const dark = screen.getByRole("button", { name: "dark" });
    expect(light).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement.dataset.theme).toBe("light");

    await user.click(dark);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(dark).toHaveAttribute("aria-pressed", "true");
    expect(light).toHaveAttribute("aria-pressed", "false");

    await user.click(light);
    expect(document.documentElement.dataset.theme).toBe("light");

    const tokens = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../styles/tokens.css"), "utf8");
    for (const hex of [
      "#f6f4ef",
      "#fffdfa",
      "#efebe3",
      "#1c2430",
      "#3e4a57",
      "#d8d2c8",
      "#1f4e79",
      "#b85c38",
      "#2f6f4e",
      "#e7d3c8",
      "#f3e6e3",
      "#6b2222",
      "#f6f1e4",
      "#6b5420",
      "#e7f2ec",
      "#1e5c40",
      "#14181e",
      "#1c222b",
      "#12161c",
      "#e8e4dc",
      "#b7c0ca",
      "#313843",
      "#9ec0dc",
      "#e3b09a",
      "#a9cdb8",
      "#5c463c",
      "#2a1717",
      "#f0d2cc",
      "#2a2418",
      "#e6d3a8",
      "#1a2c22",
      "#c9e6d6",
    ]) {
      expect(tokens.toLowerCase()).toContain(hex);
    }
    expect(tokens).toContain("--series-band-opacity: 0.45");
    expect(tokens).toContain("--series-band-opacity: 0.55");
  });
});

describe("overview", () => {
  it("renders the frozen criterion from the API response", async () => {
    setDesktop(true);
    renderAt("/");

    expect(await screen.findByRole("heading", { name: "Primary criterion: FAIL" })).toBeInTheDocument();
    expect(screen.getByText("2.6384726503825626")).toBeInTheDocument();
    expect(screen.getByText("2.6136666666666666")).toBeInTheDocument();
    expect(screen.getByText("-0.9490875034777213")).toBeInTheDocument();
    expect(screen.getByText("+10")).toBeInTheDocument();
    expect(screen.getByText("0.0")).toBeInTheDocument();
    expect(screen.getByText("0% as a percent reading of the stored share")).toBeInTheDocument();
    expect(screen.getByText("80% as a percent reading of the stored share")).toBeInTheDocument();

    const history = screen.getByRole("row", { name: /Observed price history/ });
    expect(within(history).getByText("Present, unvalidated")).toBeInTheDocument();
    expect(within(history).queryByText("Valid")).not.toBeInTheDocument();
    expect(within(history).getByText("deferred")).toBeInTheDocument();
    expect(history.querySelector("[data-indicator='file-present']")).not.toBeNull();
    expect(history.querySelector("[data-indicator='validated']")).toBeNull();

    const summary = screen.getByRole("row", { name: /Committed holdout summary/ });
    expect(within(summary).getByText("Valid")).toBeInTheDocument();
    expect(summary.querySelector("[data-indicator='validated']")).not.toBeNull();
    expect(summary.querySelector("[data-indicator='file-present']")).toBeNull();

    const cases = screen.getByRole("row", { name: /Frozen holdout cases/ });
    expect(within(cases).getByText("Missing")).toBeInTheDocument();
    expect(cases.querySelector("[data-indicator='missing']")).not.toBeNull();

    const workbook = screen.getByRole("row", { name: /PJM 2025 Tables workbook/ });
    expect(within(workbook).getByText("Invalid")).toBeInTheDocument();
    expect(workbook.querySelector("[data-indicator='invalid']")).not.toBeNull();
  });

  it("does not invent frozen metrics when the API is unreachable", async () => {
    setDesktop(true);
    renderAt("/", failedClient(new ApiClientError("connection", "The InfraLens API did not respond.")));

    expect(await screen.findAllByRole("alert")).toHaveLength(2);
    expect(screen.getAllByRole("heading", { name: "Connection unavailable" })).toHaveLength(2);
    expect(screen.queryByText("FAIL")).not.toBeInTheDocument();
    expect(screen.queryByText("2.6384726503825626")).not.toBeInTheDocument();
    expect(screen.queryByText("2.6136666666666666")).not.toBeInTheDocument();
    expect(screen.queryByText("-0.9490875034777213")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Primary criterion/ })).not.toBeInTheDocument();
    expect(document.querySelector("[data-surface='finding']")).toBeNull();
  });

  it("treats a failed summary request as operational, not as the scientific finding", async () => {
    setDesktop(true);
    renderAt(
      "/",
      failedClient(new ApiClientError("http", "Committed holdout summary is incomplete.", 500, "artifact_invalid")),
    );

    expect(await screen.findAllByRole("heading", { name: "Request failed" })).toHaveLength(2);
    expect(screen.queryByText("FAIL")).not.toBeInTheDocument();
    expect(document.querySelector("[data-surface='finding']")).toBeNull();
    expect(document.querySelector("[data-surface='operational']")).not.toBeNull();
  });
});

describe("share display", () => {
  it("converts a stored share to a percent reading without binary rounding", () => {
    expect(shareToPercentText("0.0")).toBe("0");
    expect(shareToPercentText("0.8")).toBe("80");
    expect(shareToPercentText("0.10")).toBe("10");
  });
});

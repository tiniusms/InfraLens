import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ApiClientError, createClient, type ApiClient } from "../api/client";
import { ApiProvider } from "../api/ApiProvider";
import type { PjmCatalogResponse, PjmScreenResponse } from "../api/types";
import { ThemeProvider } from "../components/shell/ThemeProvider";
import { AppRoutes } from "../routes/AppRoutes";

const ZONES = [
  "AE", "BGE", "DPL", "JCPL", "METED", "PECO", "PENLC", "PEPCO", "PL", "PS", "RECO", "UGI",
  "AEP", "APS", "ATSI", "COMED", "DAYTON", "DEOK", "DLCO", "EKPC", "OVEC", "DOM",
];
const YEARS = Array.from({ length: 22 }, (_, index) => 2025 + index);

const GEOGRAPHIC =
  "PJM zones and US states are not interchangeable. Some zones cross state borders. This tab does not join a zone to an EIA state, allocate MW to a state, or rank locations.";
const LARGE_LOAD =
  "B-9 above-embedded MW and B-9b total-associated MW are separate forecast adjustment measures. Neither is isolated data-center MW, and neither is a verified realized load. They are not added together.";
const CAGR_LABEL = "10-year CAGR percent per year (decimal × 100; not a separate published field)";
const RETRIEVAL =
  "retrieved_at is the later local file-creation time of the cached workbooks. This is not a PJM publication date and not a download receipt.";

const catalog: PjmCatalogResponse = {
  claim_boundary: "pjm_zonal_planning",
  zones: ZONES,
  forecast_year_min: 2025,
  forecast_year_max: 2046,
  forecast_years: YEARS,
  geographic_warning: GEOGRAPHIC,
  large_load_warning: LARGE_LOAD,
  measure_unit: "MW",
  cagr_unit: "decimal_per_year",
};

function screenBody(overrides: Partial<PjmScreenResponse> = {}): PjmScreenResponse {
  return {
    claim_boundary: "pjm_zonal_planning",
    available: true,
    pjm_zone: "AEP",
    forecast_year: 2026,
    as_of_date: "2026-02-06",
    ltlf_vintage_year: 2026,
    summer_peak_mw: 24635,
    summer_peak_10yr_cagr: 0.0525293343,
    cagr_percent_per_year: 5.25293343,
    cagr_percent_label: CAGR_LABEL,
    above_embedded_mw: 1913,
    total_associated_mw: 2699,
    original_release_date: "2026-01-14",
    revision_date: "2026-02-06",
    vintage_available_at: "2026-02-06",
    source_tables: ["B1", "B-9", "B-9b"],
    source_files: [
      "2026-load-report-tables.xlsx",
      "2026-load-report-tables.xlsx",
      "2026-load-report-tables.xlsx",
    ],
    source_urls: [
      "https://www.pjm.com/-/media/DotCom/planning/res-adeq/load-forecast/2026-load-report-tables.xlsx",
      "https://www.pjm.com/-/media/DotCom/planning/res-adeq/load-forecast/2026-load-report-tables.xlsx",
      "https://www.pjm.com/-/media/DotCom/planning/res-adeq/load-forecast/2026-load-report-tables.xlsx",
    ],
    retrieved_at: ["2026-03-01T12:00:00+00:00", "2026-03-01T12:00:00+00:00", "2026-03-01T12:00:00+00:00"],
    retrieval_note: RETRIEVAL,
    unavailable_reason: null,
    geographic_warning: GEOGRAPHIC,
    large_load_warning: LARGE_LOAD,
    measure_unit: "MW",
    cagr_unit: "decimal_per_year",
    ...overrides,
  };
}

const vintage2025 = screenBody({
  as_of_date: "2025-06-30",
  ltlf_vintage_year: 2025,
  summer_peak_mw: 25788,
  summer_peak_10yr_cagr: 0.0547154909,
  cagr_percent_per_year: 5.47154909,
  above_embedded_mw: 3621,
  total_associated_mw: 3936,
  original_release_date: "2025-01-24",
  revision_date: null,
  vintage_available_at: "2025-01-24",
  source_files: ["2025-load-report-tables.xlsx", "2025-load-report-tables.xlsx", "2025-load-report-tables.xlsx"],
  source_urls: [
    "https://www.pjm.com/-/media/DotCom/planning/res-adeq/load-forecast/2025-load-report-tables.xlsx",
    "https://www.pjm.com/-/media/DotCom/planning/res-adeq/load-forecast/2025-load-report-tables.xlsx",
    "https://www.pjm.com/-/media/DotCom/planning/res-adeq/load-forecast/2025-load-report-tables.xlsx",
  ],
});

function unpublished(): PjmScreenResponse {
  return screenBody({
    available: false,
    as_of_date: "2025-01-23",
    ltlf_vintage_year: null,
    summer_peak_mw: null,
    summer_peak_10yr_cagr: null,
    cagr_percent_per_year: null,
    above_embedded_mw: null,
    total_associated_mw: null,
    original_release_date: null,
    revision_date: null,
    vintage_available_at: null,
    source_tables: [],
    source_files: [],
    source_urls: [],
    retrieved_at: [],
    unavailable_reason: "No PJM Tables vintage covering this zone and forecast year was public on the as-of date.",
  });
}

function renderPjm(client: ApiClient) {
  return render(
    <ThemeProvider>
      <ApiProvider client={client}>
        <MemoryRouter initialEntries={["/pjm"]}>
          <AppRoutes />
        </MemoryRouter>
      </ApiProvider>
    </ThemeProvider>,
  );
}

function clientWith(
  screenFor: ApiClient["getPjmScreen"],
  catalogFor: ApiClient["getPjmCatalog"] = async () => catalog,
): ApiClient {
  return {
    getStatus: () => new Promise(() => undefined),
    getEvaluationSummary: () => new Promise(() => undefined),
    getHistory: () => new Promise(() => undefined),
    getHoldout: () => new Promise(() => undefined),
    getHoldoutCases: () => new Promise(() => undefined),
    postFinanceScenarios: () => new Promise(() => undefined),
    getPjmCatalog: catalogFor,
    getPjmScreen: screenFor,
  };
}

describe("PJM infrastructure explorer", () => {
  it("fills zone and year choices from the catalog and requests the default AEP 2026 vintage", async () => {
    const calls: Array<{ zone: string; year: number; asOf: string }> = [];
    renderPjm(
      clientWith(async (zone, year, asOf) => {
        calls.push({ zone, year, asOf });
        return screenBody();
      }),
    );

    expect(await screen.findByRole("option", { name: "AEP" })).toBeInTheDocument();
    for (const zone of ZONES) {
      expect(screen.getByRole("option", { name: zone })).toBeInTheDocument();
    }
    for (const year of YEARS) {
      expect(screen.getByRole("option", { name: String(year) })).toBeInTheDocument();
    }
    expect(screen.queryByRole("option", { name: "VA" })).not.toBeInTheDocument();
    expect(screen.getByText(GEOGRAPHIC)).toBeInTheDocument();
    expect(screen.getByText(LARGE_LOAD)).toBeInTheDocument();
    expect(await screen.findByRole("row", { name: /B1 summer peak demand/ })).toHaveTextContent("24635");
    expect(screen.getByRole("row", { name: /B-9 above-embedded adjustment/ })).toHaveTextContent("1913");
    expect(screen.getByRole("row", { name: /B-9b total-associated adjustment/ })).toHaveTextContent("2699");
    expect(screen.queryByText("4612")).not.toBeInTheDocument();
    expect(screen.getByText("2026", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("0.0525293343")).toBeInTheDocument();
    expect(screen.getByText(/5\.25293343 percent per year/)).toBeInTheDocument();
    expect(screen.getByText(CAGR_LABEL)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /2026-load-report-tables/ })[0]).toHaveAttribute(
      "href",
      "https://www.pjm.com/-/media/DotCom/planning/res-adeq/load-forecast/2026-load-report-tables.xlsx",
    );
    expect(screen.getByText(RETRIEVAL)).toBeInTheDocument();
    expect(screen.queryByText(/risk score/i)).not.toBeInTheDocument();
    expect(calls[0]).toEqual({ zone: "AEP", year: 2026, asOf: "2026-02-06" });
  });

  it("selects the 2025 vintage for 2025-06-30 and 2026-01-14", async () => {
    const user = userEvent.setup();
    renderPjm(
      clientWith(async (_zone, _year, asOf) => {
        if (asOf === "2026-02-06") {
          return screenBody();
        }
        return vintage2025;
      }),
    );
    expect(await screen.findByText("24635")).toBeInTheDocument();

    const date = screen.getByLabelText("As-of date");
    await user.clear(date);
    await user.type(date, "2025-06-30");
    expect(await screen.findByText("25788")).toBeInTheDocument();
    expect(screen.getAllByText("2025-01-24").length).toBeGreaterThan(0);
    expect(screen.getByText("No revision date is recorded for this vintage.")).toBeInTheDocument();
    expect(screen.queryByText("24635")).not.toBeInTheDocument();

    await user.clear(date);
    await user.type(date, "2026-01-14");
    expect(await screen.findByText("3621")).toBeInTheDocument();
    expect(screen.getByText("3936")).toBeInTheDocument();
    expect(screen.queryByText("2699")).not.toBeInTheDocument();
  });

  it("renders an unpublished as-of date without zero measures", async () => {
    const user = userEvent.setup();
    renderPjm(
      clientWith(async (_zone, _year, asOf) => (asOf === "2025-01-23" ? unpublished() : screenBody())),
    );
    expect(await screen.findByText("24635")).toBeInTheDocument();
    const date = screen.getByLabelText("As-of date");
    await user.clear(date);
    await user.type(date, "2025-01-23");
    expect(await screen.findByRole("heading", { name: "Unpublished on this as-of date" })).toBeInTheDocument();
    expect(screen.getByText(/was public on the as-of date/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("0 MW")).not.toBeInTheDocument();
    expect(screen.queryByText("24635")).not.toBeInTheDocument();
    expect(screen.getByLabelText("PJM zone")).toBeEnabled();
  });

  it("keeps a published zero and a published negative on separate rows", async () => {
    renderPjm(
      clientWith(async () =>
        screenBody({
          pjm_zone: "EKPC",
          above_embedded_mw: 0,
          total_associated_mw: -10,
        }),
      ),
    );
    const above = await screen.findByRole("row", { name: /B-9 above-embedded adjustment/ });
    const total = screen.getByRole("row", { name: /B-9b total-associated adjustment/ });
    expect(within(above).getByText("0")).toBeInTheDocument();
    expect(within(total).getByText("-10")).toBeInTheDocument();
    expect(within(above).getByText("B-9 above-embedded adjustment")).toBeInTheDocument();
    expect(within(total).getByText("B-9b total-associated adjustment")).toBeInTheDocument();
    expect(screen.queryByText("-10 MW total")).not.toBeInTheDocument();
  });

  it("shows the API display percent instead of multiplying the decimal", async () => {
    renderPjm(
      clientWith(async () =>
        screenBody({
          summer_peak_10yr_cagr: 0.5,
          cagr_percent_per_year: 1.25,
          source_files: [
            "/Users/someone/data/raw/pjm/2026-load-report-tables.xlsx",
            "/Users/someone/data/raw/pjm/2026-load-report-tables.xlsx",
            "/Users/someone/data/raw/pjm/2026-load-report-tables.xlsx",
          ],
        }),
      ),
    );
    expect(await screen.findByText("0.5")).toBeInTheDocument();
    expect(screen.getByText(/1\.25 percent per year/)).toBeInTheDocument();
    expect(screen.queryByText(/^50$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/Users\/someone/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/2026-load-report-tables\.xlsx/).length).toBeGreaterThan(0);
  });

  it("shows an unavailable panel when the workbooks are missing and does not invent measures", async () => {
    renderPjm(
      clientWith(async () => {
        throw new ApiClientError(
          "http",
          "The official 2025 or 2026 PJM Tables workbook is not on this machine, so zonal screening is unavailable.",
          404,
          "artifact_missing",
          null,
        );
      }),
    );
    expect(await screen.findByRole("heading", { name: "Zonal screening unavailable" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("24635")).not.toBeInTheDocument();
    expect(screen.getByLabelText("PJM zone")).toHaveValue("AEP");
  });

  it("shows a malformed vintage error and does not fall back to another vintage", async () => {
    renderPjm(
      clientWith(async () => {
        throw new ApiClientError(
          "http",
          "This published vintage is incomplete or contradictory. An older vintage is not substituted.",
          409,
          "malformed_vintage",
        );
      }),
    );
    expect(await screen.findByRole("heading", { name: "Published vintage is not usable" })).toBeInTheDocument();
    expect(screen.getByText(/older vintage is not substituted/)).toBeInTheDocument();
    expect(screen.queryByText("25788")).not.toBeInTheDocument();
    expect(screen.queryByText("24635")).not.toBeInTheDocument();
  });

  it("rejects an impossible as-of date before requesting and reports a 422 without measures", async () => {
    const user = userEvent.setup();
    let calls = 0;
    renderPjm(
      clientWith(async () => {
        calls += 1;
        if (calls > 1) {
          throw new ApiClientError("http", "forecast_year is outside the screening range.", 422, "validation_error", "forecast_year");
        }
        return screenBody();
      }),
    );
    expect(await screen.findByText("24635")).toBeInTheDocument();
    const date = screen.getByLabelText("As-of date");
    await user.clear(date);
    await user.type(date, "2025-13-01");
    expect(screen.getByText(/real calendar date/)).toBeInTheDocument();
    expect(screen.queryByText("24635")).not.toBeInTheDocument();
    const callsAfterInvalid = calls;

    await user.clear(date);
    await user.type(date, "2026-02-06");
    expect(await screen.findByRole("heading", { name: "The screening request was rejected" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(calls).toBeGreaterThan(callsAfterInvalid);
  });

  it("reports a network failure and an invalid payload without fabricated measures", async () => {
    const { unmount } = renderPjm(
      clientWith(async () => {
        throw new ApiClientError("connection", "The InfraLens API did not respond.");
      }),
    );
    expect(await screen.findByRole("heading", { name: "Connection unavailable" })).toBeInTheDocument();
    expect(screen.queryByText("24635")).not.toBeInTheDocument();
    unmount();

    renderPjm(
      createClient({
        baseUrl: "http://127.0.0.1:8000",
        fetchImpl: async (input) => {
          const url = String(input);
          if (url.endsWith("/api/v1/pjm/catalog")) {
            return new Response(JSON.stringify(catalog), { status: 200 });
          }
          return new Response(JSON.stringify({ claim_boundary: "nope" }), { status: 200 });
        },
      }),
    );
    expect(await screen.findByText(/did not match the API contract/)).toBeInTheDocument();
    expect(screen.queryByText("24635")).not.toBeInTheDocument();
  });

  it("drops a late screen after the as-of date changes", async () => {
    const user = userEvent.setup();
    const resolvers: Array<(value: PjmScreenResponse) => void> = [];
    renderPjm(
      clientWith(
        () =>
          new Promise((resolve) => {
            resolvers.push(resolve);
          }),
      ),
    );
    expect(await screen.findByLabelText("As-of date")).toBeInTheDocument();
    expect(resolvers).toHaveLength(1);
    const date = screen.getByLabelText("As-of date");
    await user.clear(date);
    await user.type(date, "2025-06-30");
    expect(resolvers.length).toBeGreaterThan(1);
    resolvers[resolvers.length - 1]?.(vintage2025);
    resolvers[0]?.(screenBody());
    expect(await screen.findByText("25788")).toBeInTheDocument();
    expect(screen.queryByText("24635")).not.toBeInTheDocument();
  });

  it("does not invent zones when the catalog cannot be loaded", async () => {
    let screened = false;
    renderPjm(
      clientWith(
        async () => {
          screened = true;
          return screenBody();
        },
        async () => {
          throw new ApiClientError("connection", "The InfraLens API did not respond.");
        },
      ),
    );
    expect(await screen.findByText(/Zones are not substituted/)).toBeInTheDocument();
    expect(screen.queryByLabelText("PJM zone")).not.toBeInTheDocument();
    expect(screened).toBe(false);
  });
});

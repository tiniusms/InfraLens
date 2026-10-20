import { describe, expect, it, vi } from "vitest";
import { createClient, resolveApiBaseUrl } from "../api/client";

const summaryBody = {
  claim_boundary: "closed_historical_evaluation",
  source_label: "docs/final_eia_holdout_oneshot.json",
  limitations: "Closed historical evaluation.",
  units: {
    mae: "cents/kWh",
    mae_difference: "cents/kWh",
    improvement: "percent",
    threshold: "percent",
    interval_coverage: "share",
    interval_width: "cents/kWh",
  },
  executed_on: "2026-10-04",
  runner_commit: "ee5bcf6d541a1b15822f705e4099320f6f05dc32",
  label: "label",
  note: "note",
  python: "3.13.7",
  architecture: "arm64",
  environment: "test",
  source_cases: "data/processed/final_holdout/final_holdout_cases.parquet",
  source_summary: "data/processed/final_holdout/final_holdout_summary.json",
  selected_alpha_by_origin: {},
  selected_alpha_origin_counts: {},
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

describe("api client", () => {
  it("requests the Phase 1 status and summary paths", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/status")) {
        return new Response(
          JSON.stringify({
            claim_boundary: null,
            prototype_caption: "Historical evaluation prototype.",
            presence_mode: "portable_summary",
            presence_mode_meaning: "file_existence_only",
            artifacts: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/api/v1/evaluation/summary")) {
        return new Response(JSON.stringify(summaryBody), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("no", { status: 404 });
    });

    const client = createClient({ baseUrl: "http://127.0.0.1:8000", fetchImpl });
    const status = await client.getStatus();
    const summary = await client.getEvaluationSummary();

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/status",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/evaluation/summary",
      expect.objectContaining({ method: "GET" }),
    );
    expect(status.presence_mode).toBe("portable_summary");
    expect(summary.summary.primary_criterion).toBe("FAIL");
    expect(summary.summary.ridge_mae).toBe("2.6384726503825626");
  });

  it("rejects a numeric MAE instead of coercing it", async () => {
    const fetchImpl = vi.fn(
      async () =>
        new Response(JSON.stringify({ ...summaryBody, summary: { ...summaryBody.summary, ridge_mae: 2.5 } }), {
          status: 200,
        }),
    );
    const client = createClient({ baseUrl: "http://127.0.0.1:8000", fetchImpl });
    await expect(client.getEvaluationSummary()).rejects.toMatchObject({ kind: "invalid_body" });
  });
});

describe("resolveApiBaseUrl", () => {
  it("keeps the local default when unset and allows an explicit same-origin base", () => {
    expect(resolveApiBaseUrl(undefined)).toBe("http://127.0.0.1:8000");
    expect(resolveApiBaseUrl("")).toBe("");
    expect(resolveApiBaseUrl("https://example.invalid/")).toBe("https://example.invalid");
  });
});

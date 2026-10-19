import type { FinanceRequest, FinanceScenarioInput, HoldoutCase } from "../../api/types";
import { isDecimalString } from "../../lib/format";

export type PriceSource = "typed_hypothetical" | "holdout_ridge";

export type ScenarioDraft = {
  name: string;
  source: PriceSource;
  priceCents: string;
  caseId: string;
};

export type FinanceDraft = {
  itCapacityMw: string;
  pue: string;
  utilizationPercent: string;
  operatingHours: string;
  baseline: ScenarioDraft;
  comparison: ScenarioDraft;
};

export const INITIAL_DRAFT: FinanceDraft = {
  itCapacityMw: "50",
  pue: "1.30",
  utilizationPercent: "80",
  operatingHours: "8760",
  baseline: { name: "Baseline", source: "typed_hypothetical", priceCents: "12", caseId: "" },
  comparison: { name: "Comparison", source: "typed_hypothetical", priceCents: "10", caseId: "" },
};

export const ENERGY_CHARGE_IDENTITY = [
  "Facility average demand (MW) = IT capacity (MW) × utilization × PUE.",
  "Annual consumption (kWh) = facility average demand (MW) × 1000 × operating hours.",
  "Annual energy charge (USD) = annual consumption (kWh) × price (cents/kWh) / 100.",
].join(" ");

export function caseKeyId(item: Pick<HoldoutCase, "state_id" | "forecast_origin" | "target_month">): string {
  return `${item.state_id}\u001f${item.forecast_origin}\u001f${item.target_month}`;
}

export function findCase(cases: readonly HoldoutCase[], caseId: string): HoldoutCase | null {
  return cases.find((item) => caseKeyId(item) === caseId) ?? null;
}

/** Convert a percent entry to a utilization share string. 80 becomes 0.80. */
export function percentToShare(percent: string): string | null {
  const text = percent.trim();
  if (!isDecimalString(text) || text.startsWith("-")) {
    return null;
  }
  const [whole, fraction = ""] = text.split(".");
  const digits = `${whole}${fraction}`;
  const point = whole.length - 2;
  if (point > 0) {
    const share = `${digits.slice(0, point)}.${digits.slice(point)}`;
    return share.endsWith(".") ? share.slice(0, -1) : share;
  }
  return `0.${"0".repeat(-point)}${digits}`;
}

function compareDecimal(left: string, right: string): number {
  const [leftWhole, leftFraction = ""] = left.split(".");
  const [rightWhole, rightFraction = ""] = right.split(".");
  const scale = Math.max(leftFraction.length, rightFraction.length);
  const leftScaled = BigInt(`${leftWhole}${leftFraction.padEnd(scale, "0")}`);
  const rightScaled = BigInt(`${rightWhole}${rightFraction.padEnd(scale, "0")}`);
  if (leftScaled < rightScaled) {
    return -1;
  }
  if (leftScaled > rightScaled) {
    return 1;
  }
  return 0;
}

function scenarioInput(
  draft: ScenarioDraft,
  cases: readonly HoldoutCase[],
  priceField: string,
  caseField: string,
  errors: Record<string, string>,
): FinanceScenarioInput | null {
  const name = draft.name.trim();
  if (name.length === 0) {
    errors[priceField.replace("price", "name")] = "Enter a scenario name.";
  }
  if (draft.source === "typed_hypothetical") {
    const price = draft.priceCents.trim();
    if (!isDecimalString(price) || price.startsWith("-")) {
      errors[priceField] = "Enter the energy price in cents per kWh, such as 12.";
    }
    if (name.length === 0) {
      return null;
    }
    return { name, source: "typed_hypothetical", price_cents_per_kwh: price };
  }
  const selected = findCase(cases, draft.caseId);
  if (!selected) {
    errors[caseField] = "Choose a frozen holdout case. This page does not supply a Ridge price.";
    return null;
  }
  if (name.length === 0) {
    return null;
  }
  return {
    name,
    source: "holdout_ridge",
    case_key: {
      state_id: selected.state_id,
      forecast_origin: selected.forecast_origin,
      target_month: selected.target_month,
    },
  };
}

export function buildFinanceRequest(
  draft: FinanceDraft,
  cases: readonly HoldoutCase[],
): { request: FinanceRequest | null; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const capacity = draft.itCapacityMw.trim();
  const pue = draft.pue.trim();
  const hours = draft.operatingHours.trim();
  const share = percentToShare(draft.utilizationPercent);

  if (!isDecimalString(capacity) || capacity.startsWith("-")) {
    errors.it_capacity_mw = "Enter IT capacity in MW. Zero is allowed.";
  }
  if (!isDecimalString(pue) || pue.startsWith("-") || compareDecimal(pue, "1") < 0) {
    errors.pue = "PUE must be at least 1.";
  }
  if (share === null || compareDecimal(share, "0") < 0 || compareDecimal(share, "1") > 0) {
    errors.utilization = "Enter utilization from 0 through 100 percent. 80 is sent as 0.80.";
  }
  if (!isDecimalString(hours) || hours.startsWith("-") || compareDecimal(hours, "0") <= 0) {
    errors.operating_hours_per_year = "Operating hours must be positive.";
  }

  const baselineName = draft.baseline.name.trim();
  const comparisonName = draft.comparison.name.trim();
  if (baselineName.length === 0) {
    errors.baseline_name = "Enter a baseline scenario name.";
  }
  if (comparisonName.length === 0) {
    errors.comparison_name = "Enter a comparison scenario name.";
  }
  if (baselineName.length > 0 && baselineName === comparisonName) {
    errors.comparison_name = "Baseline and comparison names must be different.";
  }

  const baseline = scenarioInput(draft.baseline, cases, "baseline_price", "baseline_case", errors);
  const comparison = scenarioInput(draft.comparison, cases, "comparison_price", "comparison_case", errors);
  if (baselineName.length === 0) {
    errors.baseline_name = "Enter a baseline scenario name.";
  }

  if (
    Object.keys(errors).length > 0 ||
    baseline === null ||
    comparison === null ||
    share === null ||
    !isDecimalString(capacity) ||
    !isDecimalString(pue) ||
    !isDecimalString(hours)
  ) {
    return { request: null, errors };
  }

  return {
    request: {
      it_capacity_mw: capacity,
      pue,
      utilization: share,
      operating_hours_per_year: hours,
      baseline_name: baselineName,
      scenarios: [baseline, comparison],
    },
    errors,
  };
}

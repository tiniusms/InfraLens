import type { HistoryResponse, HoldoutResponse } from "../../api/types";
import { isDecimalString } from "../../lib/format";

export type HistoryRow = {
  period: string;
  stateId: string;
  price: number;
  priceText: string;
  role: "observed";
  unit: "cents/kWh";
  seriesName: string;
};

export type HoldoutRow = {
  targetMonth: string;
  forecastOrigin: string;
  actual: number;
  actualText: string;
  actualRole: "observed";
  ridge: number;
  ridgeText: string;
  ridgeRole: "closed_prediction";
  naive: number;
  naiveText: string;
  naiveRole: "closed_prediction";
  band: [number, number] | null;
  lowerText: string | null;
  upperText: string | null;
  covered: boolean | null;
};

function plotNumber(text: string): number {
  if (!isDecimalString(text)) {
    throw new Error("Chart value is not a decimal string.");
  }
  const value = Number(text);
  if (!Number.isFinite(value)) {
    throw new Error("Chart value is not finite.");
  }
  return value;
}

export function historyRows(history: HistoryResponse): HistoryRow[] {
  return history.points.map((point) => ({
    period: point.period,
    stateId: point.state_id,
    price: plotNumber(point.observed_price_cents_per_kwh),
    priceText: point.observed_price_cents_per_kwh,
    role: point.role,
    unit: point.unit,
    seriesName: history.series_name,
  }));
}

export function holdoutRows(holdout: HoldoutResponse): HoldoutRow[] {
  return holdout.points.map((point) => {
    const lower = point.interval.lower_cents_per_kwh;
    const upper = point.interval.upper_cents_per_kwh;
    const band =
      lower !== null && upper !== null
        ? ([plotNumber(lower), plotNumber(upper)] as [number, number])
        : null;
    return {
      targetMonth: point.target_month,
      forecastOrigin: point.provenance.forecast_origin,
      actual: plotNumber(point.actual.cents_per_kwh),
      actualText: point.actual.cents_per_kwh,
      actualRole: point.actual.role,
      ridge: plotNumber(point.ridge.cents_per_kwh),
      ridgeText: point.ridge.cents_per_kwh,
      ridgeRole: point.ridge.role,
      naive: plotNumber(point.seasonal_naive.cents_per_kwh),
      naiveText: point.seasonal_naive.cents_per_kwh,
      naiveRole: point.seasonal_naive.role,
      band,
      lowerText: lower,
      upperText: upper,
      covered: point.interval.covered,
    };
  });
}

function axisStep(span: number): number {
  if (span > 8) {
    return 2;
  }
  if (span > 3) {
    return 1;
  }
  return 0.5;
}

export function holdoutScale(rows: HoldoutRow[]): { domain: [number, number]; ticks: number[] } {
  const values = rows.flatMap((row) => [row.actual, row.ridge, row.naive, ...(row.band ?? [])]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 0.5);
  const step = axisStep(span);
  const low = Math.floor((min - span * 0.08) / step) * step;
  const high = Math.ceil((max + span * 0.08) / step) * step;
  const ticks: number[] = [];
  for (let value = low; value <= high + step * 0.01; value += step) {
    ticks.push(Number(value.toFixed(2)));
  }
  return { domain: [low, high], ticks };
}

function monthsBetween(start: string, end: string): number {
  const [startYear, startMonth] = start.split("-").map(Number);
  const [endYear, endMonth] = end.split("-").map(Number);
  return (endYear - startYear) * 12 + (endMonth - startMonth);
}

export function historyTicks(periods: string[]): string[] {
  if (periods.length <= 8) {
    return periods;
  }
  const first = periods[0];
  const last = periods[periods.length - 1];
  const selected = periods.filter((period) => {
    const year = Number(period.slice(0, 4));
    return (
      period.endsWith("-01") &&
      year % 5 === 0 &&
      monthsBetween(first, period) >= 24 &&
      monthsBetween(period, last) >= 24
    );
  });
  const ticks = [first, ...selected, last];
  return ticks.filter((period, index) => ticks.indexOf(period) === index);
}

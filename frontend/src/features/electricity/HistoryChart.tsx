import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartScroll } from "../../components/charts/ChartScroll";
import { SeriesLegend } from "../../components/charts/SeriesLegend";
import type { HistoryRow } from "./series";
import { historyTicks } from "./series";

type HistoryChartProps = {
  rows: HistoryRow[];
  stateId: string;
};

type TooltipState = {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: HistoryRow }>;
};

function HistoryTooltip({ active, payload }: TooltipState) {
  const row = payload?.[0]?.payload;
  if (!active || !row) {
    return null;
  }
  return (
    <div className="max-w-[min(320px,calc(100vw-2rem))] border border-line bg-paper-raised px-3 py-2 text-[15px] leading-6 break-words text-ink">
      <p>{row.period}</p>
      <p>{row.seriesName}</p>
      <p className="numeric">
        {row.priceText} {row.unit}
      </p>
    </div>
  );
}

export function HistoryChart({ rows, stateId }: HistoryChartProps) {
  const ticks = historyTicks(rows.map((row) => row.period));
  return (
    <div>
      <ChartScroll label="Observed price chart" minWidth={640}>
      <div
        role="img"
        aria-label={`Observed commercial price for ${stateId}, ${rows.length} months, in cents per kilowatt-hour`}
        data-chart="history"
        data-x="period"
        data-markers="none"
        className="h-[360px] w-full"
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis
              dataKey="period"
              ticks={ticks}
              interval={0}
              tick={{ fill: "var(--ink-muted)", fontSize: 12 }}
              axisLine={{ stroke: "var(--line)" }}
              tickLine={{ stroke: "var(--line)" }}
            />
            <YAxis
              tick={{ fill: "var(--ink-muted)", fontSize: 12 }}
              axisLine={{ stroke: "var(--line)" }}
              tickLine={{ stroke: "var(--line)" }}
              width={48}
              label={{ value: "cents/kWh", angle: -90, position: "insideLeft", fill: "var(--ink-muted)", fontSize: 12 }}
            />
            <Tooltip content={<HistoryTooltip />} isAnimationActive={false} />
            <Line
              dataKey="price"
              name="Actual observed price"
              stroke="var(--series-actual)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 3, stroke: "none", fill: "var(--series-actual)" }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      </ChartScroll>
      <SeriesLegend items={[{ id: "actual", label: "Actual observed price", stroke: "var(--series-actual)" }]} />
    </div>
  );
}

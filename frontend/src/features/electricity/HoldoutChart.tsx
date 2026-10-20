import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartScroll } from "../../components/charts/ChartScroll";
import { SeriesLegend } from "../../components/charts/SeriesLegend";
import { useTheme } from "../../components/shell/useTheme";
import { holdoutScale, type HoldoutRow } from "./series";

type HoldoutChartProps = {
  rows: HoldoutRow[];
  stateId: string;
};

type TooltipState = {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: HoldoutRow }>;
};

function boundText(value: string | null): string {
  return value ?? "Not supplied";
}

function HoldoutTooltip({ active, payload }: TooltipState) {
  const row = payload?.[0]?.payload;
  if (!active || !row) {
    return null;
  }
  return (
    <div className="max-w-[min(320px,calc(100vw-2rem))] border border-line bg-paper-raised px-3 py-2 text-[15px] leading-6 break-words text-ink">
      <p>Target month {row.targetMonth}</p>
      <p className="numeric">Actual observed price {row.actualText} cents/kWh</p>
      <p className="numeric">Ridge closed prediction {row.ridgeText} cents/kWh</p>
      <p className="numeric">Seasonal-naive closed prediction {row.naiveText} cents/kWh</p>
      <p className="numeric">Interval lower {boundText(row.lowerText)} cents/kWh</p>
      <p className="numeric">Interval upper {boundText(row.upperText)} cents/kWh</p>
    </div>
  );
}

function bandOpacity(): number {
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--series-band-opacity").trim();
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : 0.45;
}

export function HoldoutChart({ rows, stateId }: HoldoutChartProps) {
  useTheme();
  const opacity = bandOpacity();
  const scale = holdoutScale(rows);
  const hasBand = rows.some((row) => row.band !== null);
  const legend = [
    { id: "actual", label: "Actual observed price", stroke: "var(--series-actual)" },
    { id: "ridge", label: "Ridge closed prediction", stroke: "var(--series-ridge)", dash: "6 4" },
    { id: "naive", label: "Seasonal-naive closed prediction", stroke: "var(--series-naive)", dash: "1.5 4" },
  ];
  if (hasBand) {
    legend.push({ id: "band", label: "Stored residual interval", stroke: "var(--series-band)", dash: "" });
  }
  return (
    <div>
      <ChartScroll label="Closed holdout chart" minWidth={760}>
      <div
        role="img"
        aria-label={`Closed holdout for ${stateId} by target month, ${rows.length} cases, in cents per kilowatt-hour`}
        data-chart="holdout"
        data-x="target_month"
        data-markers="point"
        className="h-[360px] w-full"
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 8, bottom: 24 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis
              dataKey="targetMonth"
              tick={{ fill: "var(--ink-muted)", fontSize: 12 }}
              axisLine={{ stroke: "var(--line)" }}
              tickLine={{ stroke: "var(--line)" }}
              interval={0}
              angle={-40}
              textAnchor="end"
              height={56}
            />
            <YAxis
              domain={scale.domain}
              ticks={scale.ticks}
              tick={{ fill: "var(--ink-muted)", fontSize: 12 }}
              axisLine={{ stroke: "var(--line)" }}
              tickLine={{ stroke: "var(--line)" }}
              width={48}
              label={{ value: "cents/kWh", angle: -90, position: "insideLeft", fill: "var(--ink-muted)", fontSize: 12 }}
            />
            <Tooltip content={<HoldoutTooltip />} isAnimationActive={false} />
            {hasBand ? (
              <Area
                dataKey="band"
                stroke="none"
                fill="var(--series-band)"
                fillOpacity={opacity}
                isAnimationActive={false}
                connectNulls={false}
                legendType="none"
              />
            ) : null}
            <Line
              dataKey="actual"
              name="Actual observed price"
              stroke="var(--series-actual)"
              strokeWidth={2}
              dot={{ r: 2.5, stroke: "none", fill: "var(--series-actual)" }}
              activeDot={{ r: 3, stroke: "none", fill: "var(--series-actual)" }}
              isAnimationActive={false}
            />
            <Line
              dataKey="ridge"
              name="Ridge closed prediction"
              stroke="var(--series-ridge)"
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={{ r: 2.5, stroke: "none", fill: "var(--series-ridge)" }}
              activeDot={{ r: 3, stroke: "none", fill: "var(--series-ridge)" }}
              isAnimationActive={false}
            />
            <Line
              dataKey="naive"
              name="Seasonal-naive closed prediction"
              stroke="var(--series-naive)"
              strokeWidth={2}
              strokeDasharray="1.5 4"
              dot={{ r: 2.5, stroke: "none", fill: "var(--series-naive)" }}
              activeDot={{ r: 3, stroke: "none", fill: "var(--series-naive)" }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      </ChartScroll>
      <SeriesLegend
        items={legend.map((item) => ({
          ...item,
          band: item.id === "band",
        }))}
      />
    </div>
  );
}

type LegendItem = {
  id: string;
  label: string;
  stroke: string;
  dash?: string;
  band?: boolean;
};

type SeriesLegendProps = {
  items: LegendItem[];
};

export function SeriesLegend({ items }: SeriesLegendProps) {
  return (
    <ul className="mt-3 flex flex-col gap-2">
      {items.map((item) => (
        <li key={item.id} className="flex items-center gap-3 text-[15px] leading-6 text-ink">
          <svg width="36" height="10" aria-hidden="true" data-series={item.id} data-stroke={item.stroke} data-dash={item.dash ?? ""}>
            {item.band ? (
              <rect x="0" y="2" width="36" height="6" fill="var(--series-band)" fillOpacity="var(--series-band-opacity)" />
            ) : (
              <line
                x1="0"
                y1="5"
                x2="36"
                y2="5"
                stroke={item.stroke}
                strokeWidth="2"
                strokeDasharray={item.dash}
              />
            )}
          </svg>
          <span>{item.label}</span>
        </li>
      ))}
    </ul>
  );
}

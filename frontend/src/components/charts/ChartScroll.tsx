import type { ReactNode } from "react";
import { useMinWidth } from "../../lib/useMinWidth";

type ChartScrollProps = {
  label: string;
  minWidth: number;
  children: ReactNode;
};

export function ChartScroll({ label, minWidth, children }: ChartScrollProps) {
  const desktop = useMinWidth(1024);
  if (desktop) {
    return children;
  }
  return (
    <div>
      <p className="mb-2 text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
        Scroll horizontally to read the axis
      </p>
      <div role="region" aria-label={label} tabIndex={0} className="overflow-x-auto border border-line">
        <div style={{ minWidth }}>{children}</div>
      </div>
    </div>
  );
}

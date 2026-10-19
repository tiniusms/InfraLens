import type { ReactNode } from "react";

type ScrollRegionProps = {
  label: string;
  children: ReactNode;
};

export function ScrollRegion({ label, children }: ScrollRegionProps) {
  return (
    <div className="mt-4">
      <p className="mb-2 text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
        Scroll horizontally to read every column
      </p>
      <div role="region" aria-label={label} tabIndex={0} className="overflow-x-auto border border-line">
        {children}
      </div>
    </div>
  );
}

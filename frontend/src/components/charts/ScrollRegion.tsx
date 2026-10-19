import type { ReactNode } from "react";

type ScrollRegionProps = {
  label: string;
  children: ReactNode;
  maxHeightClass?: string;
  cue?: string;
};

export function ScrollRegion({ label, children, maxHeightClass, cue }: ScrollRegionProps) {
  const bounded = maxHeightClass !== undefined;
  return (
    <div className="mt-4">
      <p className="mb-2 text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
        {cue ?? "Scroll horizontally to read every column"}
      </p>
      <div
        role="region"
        aria-label={label}
        tabIndex={0}
        className={`${bounded ? "overflow-auto" : "overflow-x-auto"} border border-line focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${maxHeightClass ?? ""}`}
      >
        {children}
      </div>
    </div>
  );
}

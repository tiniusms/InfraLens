import { useRef } from "react";
import { EIA_STATES, type EiaState } from "./states";

type StateControlProps = {
  value: EiaState;
  onChange: (state: EiaState) => void;
};

export function StateControl({ value, onChange }: StateControlProps) {
  const buttons = useRef<Partial<Record<EiaState, HTMLButtonElement>>>({});

  function move(offset: number) {
    const index = EIA_STATES.indexOf(value);
    const next = EIA_STATES[(index + offset + EIA_STATES.length) % EIA_STATES.length];
    onChange(next);
    buttons.current[next]?.focus();
  }

  return (
    <div
      role="radiogroup"
      aria-label="State"
      className="flex flex-wrap gap-2"
      onKeyDown={(event) => {
        if (event.key === "ArrowRight" || event.key === "ArrowDown") {
          event.preventDefault();
          move(1);
        }
        if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
          event.preventDefault();
          move(-1);
        }
      }}
    >
      {EIA_STATES.map((state) => {
        const selected = state === value;
        return (
          <button
            key={state}
            ref={(node) => {
              buttons.current[state] = node ?? undefined;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(state)}
            className={
              selected
                ? "rounded-[2px] border border-ink bg-paper-inset px-3 py-2 text-[15px] leading-6 font-semibold text-ink"
                : "rounded-[2px] border border-line bg-paper-raised px-3 py-2 text-[15px] leading-6 text-ink-muted"
            }
          >
            {state}
          </button>
        );
      })}
    </div>
  );
}

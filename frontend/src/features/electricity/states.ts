export const EIA_STATES = ["VA", "PA", "OH", "MD", "NJ"] as const;

export type EiaState = (typeof EIA_STATES)[number];

export function isEiaState(value: string): value is EiaState {
  return EIA_STATES.some((state) => state === value);
}

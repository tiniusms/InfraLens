import { PageShell } from "../components/shell/PageShell";

export function ElectricityPage() {
  return (
    <PageShell
      title="Electricity Intelligence"
      scope="Observed commercial prices and the closed holdout stay on this route. PJM zones are not mixed into the price series."
      notice="The observed-price history and the closed-holdout comparison are not on this page."
    />
  );
}

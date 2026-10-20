import type { EvaluationSummary } from "../api/types";
import { ScrollRegion } from "../components/charts/ScrollRegion";
import { shareToPercentText, signedIntegerText } from "../lib/format";

const STATE_ORDER = ["VA", "PA", "OH", "MD", "NJ"] as const;

type EvaluationFindingProps = {
  evaluation: EvaluationSummary;
};

export function EvaluationFinding({ evaluation }: EvaluationFindingProps) {
  const { summary, units } = evaluation;
  const gate = signedIntegerText(summary.primary_threshold_percent);
  const empiricalPercent = shareToPercentText(summary.interval_coverage);
  const nominalPercent = shareToPercentText(summary.nominal_interval_coverage);
  const findingSentence =
    summary.primary_criterion === "FAIL"
      ? `Ridge did not beat the seasonal-naive baseline by the required gate of ${gate} ${units.threshold}. These figures are historical evaluation results.`
      : `The stored primary criterion is ${summary.primary_criterion}. These figures are historical evaluation results.`;

  return (
    <section className="flex flex-col gap-8">
      <div data-surface="finding" className="finding-panel px-4 py-4">
        <p className="text-[12px] leading-4 font-semibold tracking-[0.04em] uppercase">Frozen EIA holdout</p>
        <h2 className="mt-2 font-serif text-[28px] leading-9 font-semibold">
          Primary criterion: {summary.primary_criterion}
        </h2>
        <p className="mt-3 max-w-[68ch] text-[15px] leading-6">{findingSentence}</p>
        <p className="mt-3 max-w-[68ch] text-[15px] leading-6">{evaluation.limitations}</p>
      </div>

      <dl className="border-t border-line">
        <Metric label={`Ridge MAE, ${units.mae}`} value={summary.ridge_mae} />
        <Metric label={`Seasonal-naive MAE, ${units.mae}`} value={summary.paired_baseline_mae} />
        <Metric
          label={`Relative improvement, ${units.improvement}`}
          value={summary.mae_improvement_percent}
        />
        <Metric label={`Required gate, ${units.threshold}`} value={gate} />
        <Metric
          label={`Required gate ratio`}
          value={summary.primary_threshold_ratio}
        />
        <Metric
          label={`Empirical interval coverage, ${units.interval_coverage}`}
          value={summary.interval_coverage}
          note={`${empiricalPercent}% as a percent reading of the stored share`}
        />
        <Metric
          label="Nominal interval coverage, share"
          value={summary.nominal_interval_coverage}
          note={`${nominalPercent}% as a percent reading of the stored share`}
        />
      </dl>

      <p className="max-w-[68ch] text-[15px] leading-6 text-ink">
        The evaluation covers five states, VA, PA, OH, MD, and NJ, using a public commercial price proxy.
        PJM zones stay separate from those states. The annual energy charge, in a later phase, is computed
        by the Python service.
      </p>

      <div>
        <h3 className="text-[16px] leading-6 font-semibold">State MAE</h3>
        <p className="mt-2 max-w-[68ch] text-[15px] leading-6 text-ink-muted">
          State MAE is descriptive. It sits outside the primary gate. Units are {units.mae}.
        </p>
        <ScrollRegion label="State MAE">
          <table className="w-full min-w-[36rem] border-collapse text-left text-[15px] leading-6 whitespace-nowrap">
            <thead className="bg-paper-inset text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">
              <tr>
                <th className="px-3 py-2 font-semibold">State</th>
                <th className="px-3 py-2 font-semibold">Scored</th>
                <th className="px-3 py-2 font-semibold">Ridge MAE</th>
                <th className="px-3 py-2 font-semibold">Seasonal-naive MAE</th>
              </tr>
            </thead>
            <tbody>
              {STATE_ORDER.map((state) => {
                const row = summary.mae_by_state[state];
                return (
                  <tr key={state} className="border-t border-line">
                    <th className="px-3 py-2 font-semibold text-ink" scope="row">
                      {state}
                    </th>
                    <td className="numeric px-3 py-2">{row.n_scored}</td>
                    <td className="numeric px-3 py-2">{row.ridge_mae}</td>
                    <td className="numeric px-3 py-2">{row.paired_baseline_mae}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </ScrollRegion>
      </div>

      <p className="text-[12px] leading-4 text-ink-muted">
        {evaluation.source_label}. Executed {evaluation.executed_on}. Runner {evaluation.runner_commit}.
        Claim boundary {evaluation.claim_boundary}.
      </p>
    </section>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="grid gap-1 border-b border-line py-3 sm:grid-cols-[minmax(16rem,22rem)_1fr] sm:gap-6">
      <dt className="text-[12px] leading-4 font-semibold tracking-[0.04em] text-ink-muted uppercase">{label}</dt>
      <dd className="numeric text-[15px] leading-6 text-ink">
        {value}
        {note ? <span className="mt-1 block font-normal text-ink-muted">{note}</span> : null}
      </dd>
    </div>
  );
}

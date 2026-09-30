# InfraLens Current Tasks

## Now
- [x] Scaffold Python package (`src/infralens`, tests, data dirs, feasibility-sprint deps).
- [x] Create GitHub repository and copy the onboarding pack into root.
- [x] Obtain/configure EIA API key.
- [x] Pull monthly commercial electricity price/sales history for PJM states.
- [ ] Inventory archived/current PJM load-forecast files and document publication dates.
- [x] Build first data dictionary with source, unit, frequency, availability date, and leakage risk.
- [x] Availability-adjusted seasonal-naive baseline (not unavailable t-12).
- [x] Run first publication-lag-constrained current-vintage backtest.
- [x] Regularized linear EIA baseline (Ridge) on the same development backtest. Holdout still untouched. PJM not joined.
- [x] Histogram gradient-boosting EIA candidate on the same features and development backtest. Holdout still untouched.
- [x] Select Ridge on the 1,145-case development comparison and freeze that model class and feature set. Holdout still untouched.
- [x] State-specific 80% absolute-residual intervals for the frozen Ridge model. Development evaluation only. Holdout still untouched. Method not retuned.
- [x] Exact Ridge coefficient explanations for each development origin. Not SHAP. Holdout still untouched.
- [x] Implement and test the locked final-holdout runner. The command has not been executed. Holdout actuals have not been scored.

## Next
- [ ] Financial engine + unit tests.
- [ ] Streamlit MVP.
- [ ] Execute `python -m infralens.evaluation.final_holdout` only after the runner commit is reviewed. That command has not been run.

## Later / Deferred
- MLflow tracking. Deferred 2026-09-29. `mlruns/` is gitignored, and the development evidence is already in `EVALUATION.md`, `EXPERIMENTS.md`, and `DECISIONS.md`. Do not add MLflow as a new tuning loop.

## Later / Stretch
- [ ] Utility-specific tariff enrichment.
- [ ] Automated FERC/state regulatory extraction.
- [ ] EPA/brownfield map integration.
- [ ] Texas/ERCOT expansion.

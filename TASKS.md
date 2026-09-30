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

## Next
- [ ] State-specific 80% absolute-residual intervals for the frozen Ridge model (method fixed in `EVALUATION.md`; do not retune on development coverage or on the holdout).
- [ ] Ridge coefficient and prediction-contribution explanations (method fixed in `EVALUATION.md`; not SHAP).
- [ ] Financial engine + unit tests.
- [ ] Streamlit MVP.
- [ ] Execute the written final-holdout protocol in `EVALUATION.md` only after the interval method, if coverage is to be scored with the price model. Do not open the holdout while implementing the steps above.

## Later / Deferred
- MLflow tracking. Deferred 2026-09-29. `mlruns/` is gitignored, and the development evidence is already in `EVALUATION.md`, `EXPERIMENTS.md`, and `DECISIONS.md`. Do not add MLflow as a new tuning loop.

## Later / Stretch
- [ ] Utility-specific tariff enrichment.
- [ ] Automated FERC/state regulatory extraction.
- [ ] EPA/brownfield map integration.
- [ ] Texas/ERCOT expansion.

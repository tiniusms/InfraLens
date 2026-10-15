# InfraLens Current Tasks

## Now
- [x] Scaffold Python package (`src/infralens`, tests, data dirs, feasibility-sprint deps).
- [x] Create GitHub repository and copy the onboarding pack into root.
- [x] Obtain/configure EIA API key.
- [x] Pull monthly commercial electricity price/sales history for PJM states.
- [x] Inventory archived/current PJM load-forecast files and document publication dates.
- [x] Build first data dictionary with source, unit, frequency, availability date, and leakage risk.
- [x] Availability-adjusted seasonal-naive baseline (not unavailable t-12).
- [x] Run first publication-lag-constrained current-vintage backtest.
- [x] Regularized linear EIA baseline (Ridge) on the same development backtest. Holdout still untouched. PJM not joined.
- [x] Histogram gradient-boosting EIA candidate on the same features and development backtest. Holdout still untouched.
- [x] Select Ridge on the 1,145-case development comparison and freeze that model class and feature set. Holdout still untouched.
- [x] State-specific 80% absolute-residual intervals for the frozen Ridge model. Development evaluation only. Holdout still untouched. Method not retuned.
- [x] Exact Ridge coefficient explanations for each development origin. Not SHAP. Holdout still untouched.
- [x] Implement and test the locked final-holdout runner.
- [x] Execute the one-shot final holdout from `ee5bcf6` on 2026-10-04. Primary criterion FAIL. Do not rerun it or retune from it.

## Next
- [x] PJM screening Slice 1: 2025 and 2026 Table B1 summer peak and 10-year decimal growth, with file-level availability. Not an EIA join.
- [x] PJM screening Slice 2: 2025 and 2026 Table B-9 and B-9b as separate MW series. Not data-center demand and not an EIA join.
- [x] PJM screening view: newest public vintage with complete B1, B-9, and B-9b for one zone and forecast year. No state join and no risk score.
- [ ] Later PJM slice: 2024 PDF Table B1 and B-9. Do not treat adjustment MW as data-center demand.
- [x] Financial engine: deterministic annual electricity cost from IT capacity, PUE, utilization, hours, and cents/kWh. Not a DCF, tariff engine, or risk score.
- [ ] Streamlit MVP.

## Later / Deferred
- MLflow tracking. Deferred 2026-09-29. `mlruns/` is gitignored, and the development evidence is already in `EVALUATION.md`, `EXPERIMENTS.md`, and `DECISIONS.md`. Do not add MLflow as a new tuning loop.

## Later / Stretch
- [ ] Utility-specific tariff enrichment.
- [ ] Automated FERC/state regulatory extraction.
- [ ] EPA/brownfield map integration.
- [ ] Texas/ERCOT expansion.

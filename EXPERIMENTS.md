# InfraLens Experiment Log

Human-readable record of completed EIA forecast runs. MLflow is not used. `mlruns/` is gitignored. The 2026-09-29 selection entry records that commit `4b92a5e` did not contain the Ridge or tree modules; those modules are in `2d4e162`. The numbers below are the development results already written in `EVALUATION.md`.

Final-holdout target months 2025-07 through 2026-06 are not in this log.

## 2026-09-14 - Seasonal-naive development backtest

- Stage: development
- Model: availability-adjusted seasonal naive
- Extract: `data/interim/eia_retail_sales_monthly_com_20260911T190524Z.parquet`
- Window: origins 2002-01-31 through 2024-06-30, excluding holdout targets
- Cases scored: 1,350
- MAE: 0.7793 ¢/kWh
- Entry point: `python -m infralens.evaluation.backtest`

## 2026-09-28 - Ridge development backtest

- Stage: development
- Model: Ridge
- Feature set: `eia_commercial_price_v1`
- Features: `price_latest`, `price_same_month`, `price_yoy_change`, `price_trail12_mean`, `sales_latest`, `sales_yoy_change`, `state_id`, `target_calendar_month`
- Penalty procedure: grid `0.01, 0.1, 1, 10, 100, 1000`; last 12 training origins for inner MAE; ties keep the larger penalty; refit on pre-origin rows
- Most common selected penalty: 100 (102 of 229 origins)
- Penalty at last development origin (2024-06-30): 100
- Common cases with the seasonal naive: 1,145
- Paired seasonal-naive MAE: 0.7997 ¢/kWh
- Ridge MAE: 0.7075 ¢/kWh
- Entry point: `python -m infralens.evaluation.linear`

## 2026-09-28 - Histogram gradient-boosting development backtest

- Stage: development
- Model: `HistGradientBoostingRegressor`
- Feature set: `eia_commercial_price_v1` (same rows as Ridge)
- Fixed settings: `max_iter=100`, `min_samples_leaf=20`, `max_leaf_nodes=31`, `l2_regularization=0`, `early_stopping=False`, `random_state=0`, loss `squared_error`
- Searched grid: `max_depth` in {2, 3, 6}, `learning_rate` in {0.05, 0.1}; ties keep the smaller depth, then the smaller learning rate
- Most common selected pair: depth 2, learning rate 0.05 (69 of 229 origins)
- Pair at last development origin: depth 6, learning rate 0.1
- Common cases: 1,145 (same cases as Ridge)
- Tree MAE: 0.7831 ¢/kWh
- Entry point: `python -m infralens.evaluation.tree`
- Role after 2026-09-29: negative evidence. Not the selected model.

## 2026-09-29 - Selection freeze

- Selected model: Ridge
- Feature set frozen: `eia_commercial_price_v1`
- Holdout stage: not run
- Decision: `DECISIONS.md`

## 2026-09-30 - Ridge absolute-residual intervals

- Stage: development
- Model point forecast: frozen Ridge (`eia_commercial_price_v1`), not refit
- Interval: state-specific empirical absolute residual, nominal 80% coverage
- Order statistic: `k = ceil((n + 1) * 4 / 5)`, no interpolation, minimum 24 residuals
- Ridge point check: MAE 0.7075 ¢/kWh on 1,145 cases (unchanged)
- Intervals emitted: 955
- `insufficient_residual_history`: 190
- Empirical coverage: 80.10% overall
- Mean width: 2.4046 ¢/kWh
- Median width: 1.7465 ¢/kWh
- First interval origin: 2008-08-31 for every state, with 24 residuals
- Residuals at 2024-06-30: 214 per state
- Coverage by state: MD 87.96%, NJ 85.86%, OH 77.49%, PA 67.54%, VA 81.68%
- Overall coverage is inside 75–85%. Maryland, New Jersey, and Pennsylvania are outside that range. The method was not changed.
- Newest scored target month: 2025-06
- Entry point: `python -m infralens.evaluation.intervals`
- Nominal 80% is the order statistic, not a guarantee of future coverage.

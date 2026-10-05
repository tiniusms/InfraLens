# InfraLens Experiment Log

Human-readable record of completed EIA forecast runs. MLflow is not used. `mlruns/` is gitignored. The 2026-09-29 selection entry records that commit `4b92a5e` did not contain the Ridge or tree modules; those modules are in `2d4e162`. Sections before 2026-10-04 are development results. The one-shot final holdout is the 2026-10-04 entry.

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

## 2026-09-30 - Ridge coefficient explanations

- Stage: development
- Point forecast: frozen Ridge, MAE 0.7075 ¢/kWh on 1,145 cases (unchanged)
- Identity: `prediction = intercept + sum(transformed_value * coefficient)`
- Maximum absolute reconstruction error: 3.553e-15 ¢/kWh
- Scored origins: 229
- Reference categories, constant across those origins: state `MD`, target month `01`
- These coefficients are origin-specific. The medians below are a stability summary, not one global model, and not causal effects.
- Numeric coefficients are on within-origin standardized features. State and month coefficients are contrasts against the dropped reference, not comparable to the numeric scale.
- Sign changes with a range larger than a small neighborhood of zero: `price_trail12_mean` (negative at 11/229), `sales_latest` (positive at 33/229), and the NJ, OH, and PA contrasts versus Maryland. Virginia's contrast stays negative. `price_latest`, `price_same_month`, `price_yoy_change`, and `sales_yoy_change` stay positive.
- Examples at 2024-06-30, target `2025-06`: MD 12.5808 (actual 14.82), NJ 14.2468 (actual 18.01), OH 11.1877 (actual 11.33), PA 11.2370 (actual 12.37), VA 8.1149 (actual 9.43). Maryland is the reference state on that origin.
- Newest explained target month: 2025-06
- Entry point: `python -m infralens.evaluation.explain`

## 2026-09-30 - Final holdout runner committed, not executed

- Stage: not run on this date
- Command: `python -m infralens.evaluation.final_holdout`
- The command accepts no options. On 2026-09-30 it had not been pointed at the EIA extract.
- The one-shot execution is the 2026-10-04 entry below, not this entry.
- Development uncertainty and Ridge explanations above were already committed. They are development results, not holdout results.

## 2026-10-04 - One-shot final holdout

- Stage: `final_holdout`
- Executed once. Not rerun.
- Runner commit: `ee5bcf6d541a1b15822f705e4099320f6f05dc32`
- Environment: `.venv-arm64`, Python 3.13.7, arm64
- Extract: `eia_retail_sales_monthly_com_20260911T190524Z.parquet`
- Feature set: `eia_commercial_price_v1`
- Attempted: 60
- Scored paired: 60
- Skips: `feature_gap` 0, `insufficient_train` 0, `missing_actual` 0, `no_analog` 0
- Ridge MAE: 2.638473 ¢/kWh
- Paired seasonal-naive MAE: 2.613667 ¢/kWh
- Difference, baseline minus Ridge: −0.024806 ¢/kWh
- Improvement: −0.9491%
- Threshold: at least +10%
- Primary result: FAIL
- State improvement, 12 paired cases each: MD +6.18%, NJ +14.23%, OH −10.59%, PA −0.10%, VA −31.90%
- Selected alpha: 100 on 2024-07-31 and 2025-06-30; 10 on the other 10 origins
- Intervals: 60
- Insufficient residual history: 0
- Empirical coverage: 0.0% overall and in MD, NJ, OH, PA, and VA
- Mean interval width: 2.1648 ¢/kWh
- Development comparator, not the holdout denominator: Ridge 0.7075, paired seasonal 0.7997, improvement 11.5%, 1,145 cases; interval coverage 80.10%, mean width 2.4046 ¢/kWh
- Local artifacts, gitignored: `data/processed/final_holdout/final_holdout_cases.parquet`, `data/processed/final_holdout/final_holdout_summary.json`
- Tracked copy: `docs/final_eia_holdout_oneshot.json`
- The 0% coverage is a diagnostic. The interval method was not changed. PJM was not in this model.
- Post-hoc description, not a new evaluation: `docs/final_eia_holdout_posthoc_analysis.md`. It does not revise this result.

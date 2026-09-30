# InfraLens Evaluation

This file locks the first forecasting evaluation convention. It does not change the project target (12-month-ahead commercial electricity price) or the primary metric (MAE).

## Evaluation name

**Publication-lag-constrained current-vintage backtest.**

This is **not** a true historical-vintage replay. The EIA API history is a **current vintage** and may already include later revisions. InfraLens only constrains *which observation months* may be used at a forecast origin; it does not reconstruct as-first-published EPM releases.

## Forecast origin

`forecast_origin` is the actual analyst decision date, implemented as month-end timestamps (`YYYY-MM-DD`).

Example: `2024-06-30`.

## Target

The primary target is commercial electricity price (`price_cents_per_kwh`) for the calendar month **12 months after** the forecast origin.

Example: origin `2024-06-30` → target month `2025-06`.

## Availability date

For EIA `period = m`, `assumed_available_at` is the **first day of month m+3**. This is an InfraLens evaluation assumption based on observed Electric Power Monthly timing, not an EIA-provided release timestamp.

## Leakage rule

At every forecast origin, every input must satisfy:

`assumed_available_at <= forecast_origin`

Example: origin `2024-06-30` → latest usable EIA month is `2024-03` (`assumed_available_at = 2024-06-01`). `2024-04` becomes available `2024-07-01` and is forbidden.

## Availability-adjusted seasonal-naive baseline

For each target month, use the **most recent observation of the same calendar month** that was actually available at the forecast origin.

Do **not** use an unavailable conventional t-12 analog, even as the official baseline.

Under the m+3 rule, the same calendar month one year before the target is still unpublished at a 12-month-ahead origin. The availability-adjusted seasonal baseline therefore uses the most recent *available* same-calendar-month observation, which is **t-24 relative to the target** in this setup (for example June 2023 to predict June 2025).

Example:

- origin `2024-06-30`
- latest available observation month `2024-03`
- target `2025-06`
- June 2024 (conventional t-12 vs the target) is not available
- prediction uses **June 2023** (t-24 vs the target)

## Windows

- **Development:** expanding month-end origins `2002-01-31` through `2024-06-30` (targets `2003-01` through `2025-06`).
- **Final holdout (written, not executed):** target months `2025-07` through `2026-06`. Model selection is closed. These months are still not scored.

## Development backtest results

Extract: `data/interim/eia_retail_sales_monthly_com_20260911T190524Z.parquet`.

- Forecasts attempted (development window): **1,350**
- Forecasts scored: **1,350**
- Skipped, no available seasonal analog: **0**
- Skipped, missing/NaN actual: **0**
- Leakage violations: **0**
- Overall MAE: **0.779 ¢/kWh**
- MAE by state (¢/kWh): MD **1.229**, NJ **0.956**, OH **0.507**, PA **0.610**, VA **0.594**

This development run had **zero skipped forecasts**. Future skipped cells must be disclosed in the backtest report (`n_attempted`, `n_scored`/`n_forecasts`, `n_skipped_no_analog`, `n_skipped_missing_actual`) rather than silently excluded. Holdout target months are not attempted cells; they are isolated from scoring.

Primary metric remains MAE in cents per kWh, overall and by state.

## Regularized linear candidate (Ridge)

Same extract, same month-end origins, same m+3 availability rule, and the same reserved holdout. Target months `2025-07` through `2026-06` are not fit, not used to choose the penalty, and not scored.

Reproduce with `python -m infralens.evaluation.linear`.

### Features

Each scored row uses only EIA commercial rows with `assumed_available_at <= forecast_origin`, plus calendar and state labels that are known at the origin:

- `price_latest` — price on the latest available month for that state.
- `price_same_month` — the availability-adjusted seasonal-naive analog (same definition as the baseline).
- `price_yoy_change` — latest price minus the price 12 months earlier. A missing lag skips the case.
- `price_trail12_mean` — mean price over the 12 consecutive months ending at the latest available month. A hole skips the case. The mean does not skip the hole or borrow a later month.
- `sales_latest` and `sales_yoy_change` — sales on those same two months.
- `state_id` and `target_calendar_month` — one-hot encoded inside the training fold. The target month is also the origin month, because the horizon is exactly 12 months.

`revenue_million_usd` is not a feature. EIA price is already the revenue/sales average. PJM fields are not inputs.

`StandardScaler` and the one-hot encoder are fit on that origin's training rows only, then applied to the scored origin. The penalty is chosen the same way: the last 12 training origins are an inner validation slice, the scaler and encoder for each candidate are fit on the earlier slice only, and the lowest inner MAE wins. Ties keep the larger penalty. The grid is `0.01, 0.1, 1, 10, 100, 1000`. After the penalty is chosen, scaler, encoder, and Ridge are refit on every training row whose label is already available. The scored origin is not in that refit.

A training label is eligible only when its own `assumed_available_at <= forecast_origin` and its target month is before `2025-07`.

### Development comparison

The comparison below uses the cases both models can score. Ridge cannot score the early origins, so those rows stay in the seasonal-naive backtest and drop out of the paired MAE.

| | Cases | MAE (¢/kWh) |
| --- | ---: | ---: |
| Seasonal-naive, full development window | 1,350 | 0.7793 |
| Seasonal-naive, paired cases only | 1,145 | 0.7997 |
| Ridge, paired cases only | 1,145 | 0.7075 |

Ridge MAE is **0.0922 ¢/kWh lower** than the seasonal-naive MAE on the same 1,145 cases (**11.5%**). The 205 unpaired early cases have seasonal-naive MAE **0.6656**, which is why the full-window baseline (0.7793) is lower than the paired baseline (0.7997). Comparing 0.7075 with 0.7793 mixes those sets.

Paired MAE by state, 229 cases each (¢/kWh):

| State | Ridge | Seasonal-naive | Difference | Percent |
| --- | ---: | ---: | ---: | ---: |
| MD | 1.0880 | 1.1873 | 0.0993 | 8.4% |
| NJ | 0.8942 | 0.9527 | 0.0584 | 6.1% |
| OH | 0.3861 | 0.5071 | 0.1210 | 23.9% |
| PA | 0.5322 | 0.6852 | 0.1530 | 22.3% |
| VA | 0.6369 | 0.6660 | 0.0291 | 4.4% |

Difference is seasonal-naive MAE minus Ridge MAE. Positive means Ridge is closer to the realized price.

Scored origins are `2005-06-30` through `2024-06-30` (targets `2006-06` through `2025-06`). At the last origin the selected penalty is **100**, fit on **1,260** training rows. The newest training target in that fit is `2024-03` (available `2024-06-01`). Across the 229 scored origins the selected penalties are: 0.01 (19), 0.1 (5), 1 (15), 10 (55), 100 (102), 1000 (33). **100** is the most common choice.

### Skips

Attempted development cells: **1,350** (same cells as the seasonal-naive backtest). Scored: **1,145**. Holdout origins are not attempted.

- Feature gap: **15**. Origins `2002-01-31`, `2002-02-28`, and `2002-03-31`, all five states. The 12-month price lag reaches before `2001-01`.
- Insufficient training history: **190**. Origins `2002-04-30` through `2005-05-31`, all five states. Fewer than 24 labeled origins (12 to fit, 12 to choose the penalty).
- Missing actual: **0**.

This is a development result. It does not score the final holdout and does not meet or fail the holdout success criterion.

## Histogram gradient-boosting candidate

Same extract, same feature builder, same month-end origins, same m+3 rule, and the same reserved holdout. Target months `2025-07` through `2026-06` are not fit, not used to choose hyperparameters, and not scored. No new predictors were added after this run.

Reproduce with `python -m infralens.evaluation.tree`.

The model is scikit-learn `HistGradientBoostingRegressor`. State and month are ordinal-encoded with `OrdinalEncoder` fit on that origin's training rows only. Unknown levels skip the case. They are not coded as missing. Numeric features are not standardized. The booster fits its own histogram edges on the training matrix. The loss is squared error. The metric below remains MAE.

Fixed settings, not searched: `max_iter=100`, `min_samples_leaf=20`, `max_leaf_nodes=31`, `l2_regularization=0`, `early_stopping=False`, `random_state=0`. Built-in early stopping is off because its internal split is random rather than time-ordered.

Searched grid, fixed before the run: `max_depth` in {2, 3, 6} and `learning_rate` in {0.05, 0.1}. At each origin the last 12 training origins are the inner validation slice. The encoder and each candidate are fit on the earlier slice only. The lowest inner MAE wins. Ties keep the smaller depth, then the smaller learning rate. The chosen pair is then refit on every training row whose label is already available. The scored origin is not in that refit.

### Development comparison

The tree model scores the same 1,145 cases as Ridge. Attempted cells remain 1,350. Skips match the Ridge run: 15 feature gaps, 190 origins with too little training history, and 0 missing actuals. Scored origins are `2005-06-30` through `2024-06-30` (targets `2006-06` through `2025-06`).

| | Cases | MAE (¢/kWh) |
| --- | ---: | ---: |
| Seasonal-naive, full development window | 1,350 | 0.7793 |
| Seasonal-naive, common cases | 1,145 | 0.7997 |
| Ridge, common cases | 1,145 | 0.7075 |
| Histogram gradient boosting, common cases | 1,145 | 0.7831 |

Against the seasonal naive on these 1,145 cases, the tree MAE is **0.0165 ¢/kWh lower (2.1%)**. Against Ridge on the same cases, the tree MAE is **0.0756 ¢/kWh higher (10.7%)**.

Common-case MAE by state, 229 cases each (¢/kWh):

| State | Tree | Ridge | Seasonal-naive |
| --- | ---: | ---: | ---: |
| MD | 1.2037 | 1.0880 | 1.1873 |
| NJ | 0.9822 | 0.8942 | 0.9527 |
| OH | 0.5199 | 0.3861 | 0.5071 |
| PA | 0.7264 | 0.5322 | 0.6852 |
| VA | 0.4834 | 0.6369 | 0.6660 |

Virginia is the state where the tree MAE is lower than both Ridge and the seasonal naive. In Maryland, New Jersey, Ohio, and Pennsylvania the tree MAE is higher than both.

At the last origin the selected pair is **max_depth 6, learning rate 0.1**, fit on **1,260** training rows. The newest training target in that fit is `2024-03`. Across the 229 scored origins the selected pairs are: depth 2 / 0.05 (69), depth 2 / 0.1 (28), depth 3 / 0.05 (20), depth 3 / 0.1 (34), depth 6 / 0.05 (31), depth 6 / 0.1 (47). Depth 2 with learning rate 0.05 is the most common choice.

This is a development result. It does not score the final holdout and does not meet or fail the holdout success criterion.

## Development selection freeze

On 2026-09-29 Ridge was selected as the EIA candidate. The tree result above is negative evidence, not an active candidate. The feature set and Ridge penalty procedure are frozen. See `DECISIONS.md`. Nothing in that decision scores target months `2025-07` through `2026-06`.

## Proposed uncertainty method (not implemented)

Do not fit a second probabilistic model. When intervals are implemented, use expanding-origin, state-specific absolute residual intervals around the frozen Ridge prediction. The horizon is already 12 months, so there is no separate horizon bucket. Do not pool states: development MAE is much larger in Maryland than in Ohio, and a pooled width would hide that. Do not use month-specific buckets: each state would then have about one residual per calendar month per year.

At forecast origin `T`, for state `s`, the calibration set is the Ridge cases for `s` whose forecast origin is strictly earlier than `T`, whose target month is before `2025-07`, and whose target `assumed_available_at <= T`. The case being scored is not in that set. The residual is `actual - ridge_prediction`. The interval uses the absolute residual.

Let `n` be the number of those absolute residuals, sorted ascending `e(1) <= ... <= e(n)`. The intended coverage is **80%** (`4/5`), matching the project success criterion. The order-statistic index is `k = ceil((n + 1) * 4 / 5)`, 1-based, with no interpolation. If `n < 24` or `k > n`, do not emit an interval. Count that skip as `insufficient_residual_history`. The point forecast is still produced. Twenty-four is two years of monthly residuals for one state; it was chosen so the 80% order statistic is defined with a small finite-sample correction, not by looking at development coverage.

If an interval is emitted, `q = e(k)` and the interval is `[ridge_prediction - q, ridge_prediction + q]` in ¢/kWh. `q` is symmetric around the Ridge prediction. Do not subtract the mean residual. That would change the selected point forecast.

Development coverage and width, once computed, are diagnostics. They must not change `k`, the minimum of 24, the feature set, or the penalty procedure. Holdout residuals are not an input to this rule. Under m+3, a holdout target is not yet available at any origin that is itself scored inside the holdout window, so a holdout residual cannot enter the calibration set for that window.

When intervals exist, evaluate only the cases that received one:

- Empirical coverage: the share of those cases whose actual lies inside the interval, overall and by state.
- Mean width: the mean of `2q`, in ¢/kWh, overall and by state.
- Also report how many point forecasts received no interval.

The holdout success range for an implemented 80% interval is 75–85% empirical coverage. That comparison happens only in the holdout protocol below, and only if this method has been implemented before that protocol is executed.

## Proposed Ridge explainability (not implemented)

Do not add SHAP for this linear model. The Ridge prediction is already an exact sum, and SHAP for a linear pipeline restates that sum.

At each origin the fitted pipeline is `StandardScaler` on the six numeric features and `OneHotEncoder(drop="first")` on `state_id` and `target_calendar_month`, then Ridge. After transform, `prediction = intercept + sum(transformed_value_j * coefficient_j)`.

Use three views:

- **Direction.** The sign of a numeric coefficient is the direction in the original feature, because the scaler's scale is positive when the training column varies.
- **Relative magnitude.** Compare absolute numeric coefficients with each other. They are in cents per kWh per training-fold standard deviation. Compare state-dummy coefficients only with other state dummies, and month-dummy coefficients only with other month dummies. A state dummy is cents per kWh versus the dropped reference level, not versus a standardized price feature.
- **Prediction-level contribution.** For one scored row, report the intercept and each `transformed_value_j * coefficient_j`. Those terms sum to the prediction. Inactive dummies contribute zero. The active state dummy and active month dummy each contribute their coefficient.

The dropped reference level is the first category in sorted order in that origin's training fold. On the development origins that Ridge scores, those references are Maryland and month `01`. Say the reference in the output rather than assuming it silently. Coefficient signs may be summarized across origins as a stability count. That count is not a single global model and it is not a causal effect.

## Final holdout protocol (do not execute in the selection freeze)

This protocol is the only authorized way to score target months `2025-07` through `2026-06`. It has not been run.

1. **Model.** Ridge, through the existing `run_ridge_backtest` procedure. No new estimator.
2. **Features.** Exactly `eia_commercial_price_v1`: `price_latest`, `price_same_month`, `price_yoy_change`, `price_trail12_mean`, `sales_latest`, `sales_yoy_change`, `state_id`, `target_calendar_month`.
3. **Penalty.** The frozen procedure in `DECISIONS.md` (grid `0.01, 0.1, 1, 10, 100, 1000`; last 12 training origins for inner MAE; at least 12 earlier origins to fit; ties keep the larger penalty; refit on eligible pre-origin rows). Do not replace that procedure with the development mode of 100.
4. **Origins.** Month-end origins `2024-07-31` through `2025-06-30`. Targets are `2025-07` through `2026-06`. Development origins stay in the training history when their labels are already available. The scored holdout origin is excluded from its own fit.
5. **Training guard.** A row whose target month is `2025-07` or later is never a training row and never an inner-validation row, including at later origins. The current m+3 lag already keeps those actuals unpublished throughout this origin window. Keep the code guard anyway.
6. **Benchmark.** Availability-adjusted seasonal naive, same definition as development. Primary comparison is paired: same state, same origin, same target month, on cases Ridge scores. Also print the already recorded full development seasonal-naive MAE (`0.7793` ¢/kWh, 1,350 cases) so it is not used as the holdout denominator.
7. **Metric.** MAE in ¢/kWh. Improvement = seasonal-naive MAE minus Ridge MAE on the paired holdout cases. Percent = `100 * improvement / seasonal-naive MAE`. The success threshold, set before modeling, is at least **10%** lower holdout MAE than that paired seasonal naive. Report overall MAE and MAE by state for both models, plus attempted, scored, and skip counts.
8. **Uncertainty.** If the residual method above is implemented before this protocol runs, apply it unchanged at each holdout origin and report empirical coverage and mean width, overall and by state. The coverage check is 75–85% for the intended 80% interval. If the method is not implemented before the protocol runs, skip the coverage check in that run. Do not invent a different interval after seeing holdout prices.
9. **Outputs.** One table of paired holdout MAE overall and by state; skip accounting; the penalty selected at each holdout origin and the count of each penalty; feature-set id `eia_commercial_price_v1`; the EIA extract filename; the stage label `final_holdout`. If intervals exist, a second table of coverage, mean width, and the number of cases without an interval.
10. **After the run.** Holdout results are descriptive. They do not add a model, drop a feature, retune a penalty, or refit state by state. The tree model is not re-scored on the holdout in order to reopen model selection.

## What this evaluation is not

- Not a true historical-vintage replay (current-vintage EIA history may include revisions).
- Not a tariff/PPA forecast.
- Not license to use `period` as an availability date.

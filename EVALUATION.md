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
- **Final holdout (executed once on 2026-10-04):** target months `2025-07` through `2026-06`. Model selection is closed. The one-shot result is recorded in “Final holdout protocol (executed once on 2026-10-04)” and “Final holdout result (one-shot, 2026-10-04).”

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

## State-specific empirical absolute-residual intervals

Implemented in `src/infralens/evaluation/intervals.py`. This is not a second probabilistic model. Each interval is built from the frozen Ridge rolling-origin point forecast. The horizon is already 12 months, so there is no separate horizon bucket. States are not pooled: development MAE is much larger in Maryland than in Ohio, and a pooled width would hide that. Calendar months are not separate buckets: each state would then have about one residual per calendar month per year.

At forecast origin `T`, for state `s`, the calibration set is the Ridge cases for `s` whose forecast origin is strictly earlier than `T`, whose target month is before `2025-07`, and whose target `assumed_available_at <= T`. Those cases are the out-of-sample predictions already stored by the Ridge backtest, not in-sample fitted values. The case being scored is not in that set. The residual is `actual - ridge_prediction`. The interval uses the absolute residual.

Let `n` be the number of those absolute residuals, sorted ascending `e(1) <= ... <= e(n)`. Nominal coverage is **80%** (`4/5`). The order-statistic index is `k = ceil((n + 1) * 4 / 5)`, 1-based, with no interpolation. If `n < 24` or `k > n`, do not emit an interval. Count that skip as `insufficient_residual_history`. The point forecast is still produced. Twenty-four is two years of monthly residuals for one state; it was chosen so the 80% order statistic is defined with a small finite-sample correction, not by looking at development coverage.

If an interval is emitted, `q = e(k)` and the interval is `[ridge_prediction - q, ridge_prediction + q]` in ¢/kWh. `q` is symmetric around the Ridge prediction. The mean residual is not subtracted. That would change the selected point forecast.

Nominal 80% coverage is the order statistic. It is not a guarantee that a future window, including the final holdout, will cover 80% of actuals.

Development coverage and width are diagnostics. They do not change `k`, the minimum of 24, the feature set, or the penalty procedure. Holdout residuals are not an input to this rule. Under m+3, a holdout target is not yet available at any origin that is itself scored inside the holdout window, so a holdout residual cannot enter the calibration set for that window.

### Development interval results

Entry point: `python -m infralens.evaluation.intervals`. Same extract and development Ridge point forecasts as the selection freeze. Ridge MAE on this run remained **0.7075 ¢/kWh on 1,145 cases**. The interval table's point column matched those predictions. The newest scored target month was `2025-06`.

| Quantity | Result |
| --- | --- |
| Ridge point forecasts | 1,145 |
| Intervals emitted | 955 |
| `insufficient_residual_history` | 190 |
| Nominal coverage | 80% |
| Empirical coverage | 80.10% |
| Mean width | 2.4046 ¢/kWh |
| Median width | 1.7465 ¢/kWh |

Empirical coverage and mean width by state, on the 955 interval cases (191 per state):

| State | Empirical coverage | Mean width (¢/kWh) |
| --- | --- | --- |
| MD | 87.96% | 4.1736 |
| NJ | 85.86% | 3.4185 |
| OH | 77.49% | 1.2517 |
| PA | 67.54% | 1.2953 |
| VA | 81.68% | 1.8839 |

The first origin that emits an interval is **2008-08-31** in every state, with **24** calibration residuals. At the last development origin, **2024-06-30**, each state has **214** calibration residuals. The 190 point forecasts without an interval are the origins before that first date.

Overall development coverage is inside the 75–85% check. That check is not a tuning target, and the method was not changed after seeing it. Three state slices are outside the same range: Maryland and New Jersey are above 85%, and Pennsylvania is below 75%. Ohio and Virginia are inside it. Maryland's mean width is about 4.17 ¢/kWh; Ohio's is about 1.25 ¢/kWh.

Mean width by origin year starts at 2.76 ¢/kWh in 2008, declines to 2.02 ¢/kWh in 2021, and is 2.18 ¢/kWh in 2024. That description is not a reason to change `k` or the minimum of 24.

The frozen holdout recorded 0.0% empirical interval coverage against the nominal 80% interval. The 75–85% range is a diagnostic, not the primary pass/fail gate. The interval procedure was not retuned from that holdout. The recorded result is in “Final holdout result (one-shot, 2026-10-04).”

## Ridge coefficient explanations

Implemented in `src/infralens/evaluation/explain.py`. SHAP is not used. Ridge is refit at every scored origin, so each coefficient vector belongs to that origin. The summaries below describe how those origin-specific coefficients behave. They are not one universal InfraLens coefficient vector, and they are not causal effects.

At a scored origin the fitted pipeline is `StandardScaler` on the six numeric features and `OneHotEncoder(drop="first")` on `state_id` and `target_calendar_month`, then Ridge with the penalty already selected for that origin. After transform:

`prediction = intercept + sum(transformed_value_j * coefficient_j)`.

Numeric coefficients are cents per kWh per training-fold standard deviation. Their magnitudes may be compared with other numeric coefficients from the same origin. State and month coefficients are contrasts against the category that origin's encoder dropped. A dropped reference is not a zero coefficient; its level is absorbed by the intercept and the other contrasts. Inactive one-hot columns do contribute zero, because the indicator is zero. That is a different statement from the missing reference column. An unseen state or month is not given a coefficient; the case is skipped, as in the Ridge backtest.

The reference categories were read from each fitted encoder. Across all **229** scored development origins they do not change: the dropped state is **MD**, and the dropped target month is **01**.

### Development coefficient summary

Entry point: `python -m infralens.evaluation.explain`. The Ridge point forecast on this run remained **0.7075 ¢/kWh on 1,145 cases**. Explanations cover those same 1,145 rows. The largest absolute gap between `intercept + sum(contributions)` and the stored Ridge prediction is **3.553e-15** ¢/kWh. The newest explained target month is `2025-06`.

Numeric coefficients across the 229 origins, and the coefficient at the final development origin `2024-06-30`:

| Feature | Median | Minimum | Maximum | Positive origins | Final origin |
| --- | --- | --- | --- | --- | --- |
| `price_latest` | 0.391784 | 0.012433 | 0.467539 | 229/229 | 0.399325 |
| `price_same_month` | 0.767132 | 0.373875 | 1.436008 | 229/229 | 0.681656 |
| `price_yoy_change` | 0.292053 | 0.060454 | 0.471632 | 229/229 | 0.289628 |
| `price_trail12_mean` | 0.464477 | -1.015240 | 0.825787 | 218/229 | 0.459074 |
| `sales_latest` | -0.158993 | -0.672176 | 0.340149 | 33/229 | -0.202147 |
| `sales_yoy_change` | 0.083314 | 0.002852 | 0.396247 | 229/229 | 0.126533 |

`price_latest`, `price_same_month`, `price_yoy_change`, and `sales_yoy_change` stay positive at every scored origin. `price_trail12_mean` is negative at 11 origins (range about -1.02 to 0.83). `sales_latest` is negative at 196 origins and positive at 33 (range about -0.67 to 0.34). Those sign changes are large relative to a tenth of a cent per standardized unit. They describe the rolling fits. They do not identify a cause.

State contrasts versus Maryland:

| Contrast | Median | Minimum | Maximum | Positive origins | Final origin |
| --- | --- | --- | --- | --- | --- |
| NJ | 0.311446 | -2.581915 | 3.328628 | 212/229 | 0.421063 |
| OH | -0.073394 | -2.670166 | 1.619723 | 1/229 | -0.029644 |
| PA | -0.111696 | -3.132442 | 2.687102 | 1/229 | -0.082345 |
| VA | -0.327488 | -2.097526 | -0.094490 | 0/229 | -0.330349 |

Virginia's contrast with Maryland stays negative. New Jersey is positive at 212 origins and negative at 17. Ohio and Pennsylvania are negative at 228 origins and positive at one origin each. Those ranges are wide. Do not compare these contrasts with the standardized numeric coefficients as if the units matched.

Month contrasts versus January also change sign for February, March, May, June, September, October, and November. March stays inside about -0.07 to 0.07. April, July, August, and December do not change sign: April and December stay negative; July and August stay positive. Full month ranges are in the command output.

### Examples at 2024-06-30

Target month `2025-06` for every state. Shared intercept **9.946799**. June's contrast with January contributes **0.089438** in every state. Maryland is the reference state, so it has no separate state coefficient. Reconstruction error on each row is within the 3.553e-15 maximum above.

| State | Prediction | Actual | Signed error | State term | Contribution |
| --- | --- | --- | --- | --- | --- |
| MD | 12.5808 | 14.82 | 2.2392 | reference MD | none |
| NJ | 14.2468 | 18.01 | 3.7632 | contrast vs MD | 0.421063 |
| OH | 11.1877 | 11.33 | 0.1423 | contrast vs MD | -0.029644 |
| PA | 11.2370 | 12.37 | 1.1330 | contrast vs MD | -0.082345 |
| VA | 8.1149 | 9.43 | 1.3151 | contrast vs MD | -0.330349 |

Numeric contributions at that same origin. The coefficient column is shared across states; the raw value, standardized value, and contribution are not.

| State | Feature | Raw | Standardized | Coefficient | Contribution |
| --- | --- | --- | --- | --- | --- |
| MD | `price_latest` | 12.680000 | 1.467203 | 0.399325 | 0.585891 |
| MD | `price_same_month` | 12.500000 | 1.455973 | 0.681656 | 0.992473 |
| MD | `price_yoy_change` | 0.160000 | -0.026005 | 0.289628 | -0.007532 |
| MD | `price_trail12_mean` | 12.565833 | 1.507690 | 0.459074 | 0.692141 |
| MD | `sales_latest` | 2132.559820 | -1.631016 | -0.202147 | 0.329705 |
| MD | `sales_yoy_change` | -59.914290 | -0.380321 | 0.126533 | -0.048123 |
| NJ | `price_latest` | 13.900000 | 2.069053 | 0.399325 | 0.826224 |
| NJ | `price_same_month` | 14.870000 | 2.632576 | 0.681656 | 1.794511 |
| NJ | `price_yoy_change` | 0.400000 | 0.311067 | 0.289628 | 0.090094 |
| NJ | `price_trail12_mean` | 13.990833 | 2.236718 | 0.459074 | 1.026819 |
| NJ | `sales_latest` | 3089.364950 | -0.386747 | -0.202147 | 0.078180 |
| NJ | `sales_yoy_change` | -15.894960 | -0.208370 | 0.126533 | -0.026366 |
| OH | `price_latest` | 11.200000 | 0.737090 | 0.399325 | 0.294338 |
| OH | `price_same_month` | 10.970000 | 0.696395 | 0.681656 | 0.474702 |
| OH | `price_yoy_change` | 0.840000 | 0.929032 | 0.289628 | 0.269074 |
| OH | `price_trail12_mean` | 10.870833 | 0.640530 | 0.459074 | 0.294051 |
| OH | `sales_latest` | 3870.375850 | 0.628911 | -0.202147 | -0.127132 |
| OH | `sales_yoy_change` | -10.980550 | -0.189173 | 0.126533 | -0.023937 |
| PA | `price_latest` | 11.270000 | 0.771622 | 0.399325 | 0.308128 |
| PA | `price_same_month` | 11.220000 | 0.820509 | 0.681656 | 0.559305 |
| PA | `price_yoy_change` | 0.120000 | -0.082184 | 0.289628 | -0.023803 |
| PA | `price_trail12_mean` | 11.092500 | 0.753934 | 0.459074 | 0.346112 |
| PA | `sales_latest` | 2949.637840 | -0.568454 | -0.202147 | 0.114911 |
| PA | `sales_yoy_change` | -6.189920 | -0.170459 | 0.126533 | -0.021569 |
| VA | `price_latest` | 8.720000 | -0.486343 | 0.399325 | -0.194209 |
| VA | `price_same_month` | 8.970000 | -0.296519 | 0.681656 | -0.202124 |
| VA | `price_yoy_change` | -0.470000 | -0.910819 | 0.289628 | -0.263799 |
| VA | `price_trail12_mean` | 8.821667 | -0.407820 | 0.459074 | -0.187220 |
| VA | `sales_latest` | 6082.920380 | 3.506195 | -0.202147 | -0.708767 |
| VA | `sales_yoy_change` | -33.100950 | -0.275581 | 0.126533 | -0.034870 |

## Final holdout protocol (executed once on 2026-10-04)

This protocol is the only authorized way to score target months `2025-07` through `2026-06`. The command is `python -m infralens.evaluation.final_holdout`. It accepts no options. It was executed once on 2026-10-04 from runner commit `ee5bcf6d541a1b15822f705e4099320f6f05dc32` in `.venv-arm64`. Do not execute it again. The result is below. The protocol itself was not changed after the score.

Development uncertainty (`333b754`) and Ridge explanations (`787ce42`) were run and committed before this runner. The 2026-09-29 decision says those methods were not executed *in that decision*. That sentence does not mean they were never run on the development window.

`run_ridge_backtest` still refuses to score holdout targets. The final command reuses `select_alpha`, `fit_ridge`, and `training_cases_for_origin` on the locked 60-cell grid, with training targets kept before `2025-07`. It does not define a second model. Holdout explanations are not part of the command; `explain_prediction` can explain a stored prediction afterward and does not affect the comparison.

1. **Model.** Ridge, through the frozen helpers above. No new estimator.
2. **Features.** Exactly `eia_commercial_price_v1`: `price_latest`, `price_same_month`, `price_yoy_change`, `price_trail12_mean`, `sales_latest`, `sales_yoy_change`, `state_id`, `target_calendar_month`.
3. **Penalty.** The frozen procedure in `DECISIONS.md` (grid `0.01, 0.1, 1, 10, 100, 1000`; last 12 training origins for inner MAE; at least 12 earlier origins to fit; ties keep the larger penalty; refit on eligible pre-origin rows). Do not replace that procedure with the development mode of 100.
4. **Origins.** Month-end origins `2024-07-31` through `2025-06-30`. Targets are `2025-07` through `2026-06`. Development origins stay in the training history when their labels are already available. The scored holdout origin is excluded from its own fit.
5. **Training guard.** A row whose target month is `2025-07` or later is never a training row and never an inner-validation row, including at later origins. The current m+3 lag already keeps those actuals unpublished throughout this origin window. Keep the code guard anyway.
6. **Benchmark.** Availability-adjusted seasonal naive, same definition as development. Primary comparison is paired: same state, same origin, same target month, on cases Ridge scores. Also print the already recorded full development seasonal-naive MAE (`0.7793` ¢/kWh, 1,350 cases) so it is not used as the holdout denominator.
7. **Metric.** MAE in ¢/kWh on the paired scored cases only. The primary ratio is `(paired baseline MAE - Ridge MAE) / paired baseline MAE`. The run passes only when that ratio is at least **0.10** (10% lower MAE). State MAE is reported and cannot change the pass/fail result. The full development seasonal-naive MAE is not the denominator.
8. **Uncertainty.** Apply the implemented residual method unchanged at each holdout origin and report empirical coverage and mean width, overall and by state. The coverage check is 75–85% for the nominal 80% interval. Do not change `k`, the minimum of 24, or the Ridge point forecast after seeing holdout prices. Development coverage, including state slices outside 75–85%, is not a reason to change the method.
9. **Outputs.** One table of paired holdout MAE overall and by state; skip accounting; the penalty selected at each holdout origin and the count of each penalty; feature-set id `eia_commercial_price_v1`; the EIA extract filename; the stage label `final_holdout`. If intervals exist, a second table of coverage, mean width, and the number of cases without an interval.
10. **After the run.** Holdout results are descriptive. They do not add a model, drop a feature, retune a penalty, or refit state by state. The tree model is not re-scored on the holdout in order to reopen model selection.

## Final holdout result (one-shot, 2026-10-04)

Primary criterion: **FAIL**. Ridge MAE 2.638473 ¢/kWh was slightly worse than the paired availability-adjusted seasonal-naive MAE 2.613667 ¢/kWh. Difference, baseline minus Ridge, −0.024806 ¢/kWh. Improvement −0.9491%, against a preregistered threshold of at least +10%. Attempted 60, scored 60, and every skip count is 0.

State results are descriptive and do not override the FAIL. Each state has 12 paired cases. Improvement is MD +6.18%, NJ +14.23%, OH −10.59%, PA −0.10%, VA −31.90%.

Selected alpha was 100 at origins 2024-07-31 and 2025-06-30, and 10 at the other 10 origins.

Intervals emitted: 60. Insufficient history: 0. Empirical coverage: 0.0% overall and in all five states. Mean width: 2.1648 ¢/kWh. Development coverage was 80.10% with mean width 2.4046 ¢/kWh. The holdout coverage is severe miscalibration for this period. It does not change the interval method, and nominal 80% coverage is not a guarantee.

Development common-case comparator, already frozen and not the holdout denominator: Ridge 0.7075, paired seasonal naive 0.7997, improvement 11.5%, 1,145 cases.

Extract: `eia_retail_sales_monthly_com_20260911T190524Z.parquet`. Feature set: `eia_commercial_price_v1`. Gitignored artifacts: `data/processed/final_holdout/final_holdout_cases.parquet` and `data/processed/final_holdout/final_holdout_summary.json`. Tracked copy of the generated summary: `docs/final_eia_holdout_oneshot.json`.

Development model selection stays closed. This holdout is not a tuning set. Later examination is post-hoc error analysis. A future predictive model needs a new evaluation design and new untouched data before a confirmatory claim. PJM was not in this model and is not an explanation of these errors.

## What this evaluation is not

- Not a true historical-vintage replay (current-vintage EIA history may include revisions).
- Not a tariff/PPA forecast.
- Not license to use `period` as an availability date.

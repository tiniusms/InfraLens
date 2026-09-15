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
- **Final holdout (untouched until model selection):** target months `2025-07` through `2026-06`. Not scored in this sprint.

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

## What this evaluation is not

- Not a true historical-vintage replay (current-vintage EIA history may include revisions).
- Not a tariff/PPA forecast.
- Not license to use `period` as an availability date.

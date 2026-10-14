# InfraLens Data Dictionary

First feasibility extract, plus the lagged fields the Ridge baseline builds at forecast time. Those fields are not stored as Parquet columns. Values below describe the live EIA pull retrieved `2026-09-10T03:59:06Z`.

**Dataset:** monthly commercial (COM) retail electricity sales to ultimate customers  
**Geography:** Maryland, New Jersey, Ohio, Pennsylvania, Virginia  
**Source system:** U.S. Energy Information Administration (EIA) API v2 route `/v2/electricity/retail-sales/data/`  
**Underlying surveys (EIA metadata):** Forms EIA-826, EIA-861, and EIA-861M  
**Raw artifact:** `data/raw/eia/retail_sales_monthly_com_<UTC-stamp>.json` (immutable; API key redacted)  
**Interim artifact:** `data/interim/eia_retail_sales_monthly_com_<UTC-stamp>.parquet`  
One ingest run writes one JSON and one Parquet that share the same stamp. There is no mutable “latest” Parquet file.  
Example extract used for the quality notes below: retrieved `2026-09-10T03:59:06Z`.  
**Grain:** one row per `state_id` × `period` × `sector_id`  
**Observed coverage:** 1,530 rows; 2001-01 through 2026-06; 306 months; 306 rows per state; complete monthly panel (no missing months)

Publication / availability timing for true EIA vintages remains unobserved in the API. InfraLens uses a **conservative evaluation assumption**: `assumed_available_at` is the first day of month *m+3* for observation month *m*. That date is not an EIA release timestamp. Historical API values are **current-vintage** and may include later revisions.

## Units verification (not from column names alone)

EIA API route metadata for `electricity/retail-sales` lists:

- `price`: average price of electricity to ultimate customers, **cents per kilowatthour**
- `sales`: megawatthours sold to ultimate customers, reported as **million kilowatthours**
- `revenue`: revenue from sales to ultimate customers, **million dollars**

Every observation in the raw JSON carries the same unit strings: `cents per kilowatt-hour`, `million kilowatt hours`, `million dollars`. EIA also states that published average retail prices are derived by dividing utility revenues (dollars) by retail sales (kilowatthours), and that the average includes generation, transmission, distribution, taxes, and fees—it is not a tariff or PPA rate.

**Identity check on this extract:**  
`100 × revenue_million_usd / sales_million_kwh` vs `price_cents_per_kwh`  
(million dollars / million kWh = dollars per kWh; ×100 = cents per kWh). Maximum absolute difference is 0.005 cents/kWh; all 1,530 rows are within 0.01 cents. Residuals match two-decimal rounding of EIA prices. The three measures are economically consistent after unit conversion.

A conflicting EIA API documentation example sometimes lists price in dollars per kWh and sales in kilowatthours. That example does not match the route metadata, the per-row unit fields, or the revenue/sales identity on this extract. InfraLens uses cents per kWh, million kWh, and million dollars.

## Variables

| Name | Source | Definition | Unit | Frequency | Role | Observation period | Publication / availability | Leakage risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `period` | EIA `period` | Calendar month of the retail-sales observation (`YYYY-MM`). | Month | Monthly | Time key | 2001-01 to 2026-06 | Not an availability date | Using `period` as if it were available on the first of that month would leak. |
| `period_start` | Derived from `period` | First day of `period`. Not an EIA publication date. | Date | Monthly | Time key convenience | Same as `period` | Not an availability date | Same as `period`. |
| `state_id` | EIA `stateid` | USPS state code. Feasibility slice: MD, NJ, OH, PA, VA. | Code | Monthly | Entity key; geography | All rows | n/a | None if used only as a known location identifier. |
| `state_name` | EIA `stateDescription` | State name. | Text | Monthly | Label | All rows | n/a | None. |
| `sector_id` | EIA `sectorid` | End-use sector. This extract is `COM` only. | Code | Monthly | Entity key; filter | All rows | n/a | Do not mix other sectors without a dated decision. |
| `sector_name` | EIA `sectorName` | Sector label (`commercial`). | Text | Monthly | Label | All rows | n/a | None. |
| `price_cents_per_kwh` | EIA `price` | Average commercial retail price to ultimate customers. EIA-derived average (revenue / kWh), not a data-center tariff. **Primary ML target proxy** (12-month-ahead). Lagged copies are Ridge inputs. | Cents per kWh | Monthly | Target at t+12; source of lagged price features | 2001-01 to 2026-06 | Assumed available on the first day of month m+3 | High if future months or post-revision vintages are used as features. Target at t+12 must not appear in features at origin t. |
| `sales_million_kwh` | EIA `sales` | Commercial electricity sold to ultimate customers. | Million kWh | Monthly | Lagged Ridge input (latest level and 12-month change) | 2001-01 to 2026-06 | Assumed available on the first day of month m+3 | High if contemporaneous or future sales are used to predict future price without a lag rule. |
| `revenue_million_usd` | EIA `revenue` | Revenue from commercial sales to ultimate customers. | Million USD | Monthly | Not a Ridge feature. Algebraically tied to price. | 2001-01 to 2026-06 | Assumed available on the first day of month m+3 | Same as sales. Do not add it beside lagged price and sales. |
| `price_units` | EIA `price-units` | Unit string supplied by the API. | Text | Monthly | Metadata | All rows | n/a | None. |
| `sales_units` | EIA `sales-units` | Unit string supplied by the API. | Text | Monthly | Metadata | All rows | n/a | None. |
| `revenue_units` | EIA `revenue-units` | Unit string supplied by the API. | Text | Monthly | Metadata | All rows | n/a | None. |
| `frequency` | EIA request / `frequency` | `monthly`. | Text | Constant | Metadata | All rows | n/a | None. |
| `retrieved_at` | InfraLens extract | UTC timestamp when this API payload was retrieved. | Timestamp | Extract-level | Lineage | 2026-09-10T03:59:06Z | Known (extract time only) | Does not make historical months point-in-time valid. |
| `assumed_available_at` | InfraLens evaluation assumption | First day of month *m+3* for `period` *m*. Conservative stand-in for EPM lag; **not** an EIA first-publication or revision timestamp. | Date | Monthly | Leakage control | Derived for every row | Assumed (m+3-01) | If ignored, future-of-origin information can leak into the baseline. |
| `source` | InfraLens | `U.S. Energy Information Administration`. | Text | Constant | Lineage | All rows | n/a | None. |
| `source_route` | InfraLens | `/v2/electricity/retail-sales/data/`. | Text | Constant | Lineage | All rows | n/a | None. |
| `source_url` | InfraLens | HTTPS endpoint used for retrieval (no key). | URL | Constant | Lineage | All rows | n/a | None. |

## Derived model features

Built in `src/infralens/evaluation/features.py` at each forecast origin. They are not columns in the interim Parquet. A source month is eligible only when `assumed_available_at <= forecast_origin`. If a required month is missing or null, the case is skipped. It is not filled from a later month.

| Feature | Definition | Point-in-time rule |
| --- | --- | --- |
| `price_latest` | Commercial price on the latest available month for that state. | That month's `assumed_available_at` is on or before the origin. |
| `price_same_month` | Availability-adjusted seasonal-naive price for the target calendar month. | Same function as the baseline. The conventional t-12 month is not used when it is still unpublished. |
| `price_yoy_change` | `price_latest` minus the price 12 months earlier. | Both months must already be available. |
| `price_trail12_mean` | Mean price over the 12 consecutive months ending at the latest available month. | A hole in that window skips the case. |
| `sales_latest` | Sales on the latest available month. | Same month as `price_latest`. |
| `sales_yoy_change` | Sales change versus 12 months earlier. | Same months as `price_yoy_change`. |
| `state_id` | State code. | Known geography. Ridge one-hot encodes it inside the training fold. The tree model ordinal-encodes it inside the training fold. |
| `target_calendar_month` | Calendar month of the 12-month-ahead target. | Known from the origin. It is not an EIA observation. Because the horizon is 12 months, it equals the origin month. Encoded the same way as `state_id`. |

`revenue_million_usd` is excluded because published price is the revenue/sales average. PJM zonal fields are not features in this model. Slice 1 screening columns are defined in the next section and are not added to `eia_commercial_price_v1`.

The histogram gradient-boosting candidate uses this same list. Its ordinal encoder is fit on that origin's training rows only. An unseen state or month skips the case. Numeric features are not standardized; the booster fits histogram bin edges on the training fold.

## Ridge interval audit columns

Built in `src/infralens/evaluation/intervals.py` from the frozen Ridge rolling-origin predictions. They are not columns in the interim Parquet, and they are not additional model features. Nominal coverage is 80%. That label is the order statistic, not a claim that a future window will cover 80% of actuals.

| Column | Definition |
| --- | --- |
| `state_id` | State of the scored Ridge forecast. Calibration uses that state only. |
| `forecast_origin` | Month-end origin of the scored forecast. |
| `target_period` | Target month, 12 months after the origin. Development output stops before `2025-07`. |
| `ridge_prediction_cents_per_kwh` | Frozen Ridge point forecast, copied unchanged. |
| `actual_cents_per_kwh` | Realized target price, when the development case has one. |
| `n_calibration_residuals` | Count of earlier same-state Ridge residuals whose target was available at this origin and whose target month is before `2025-07`. |
| `k` | `ceil((n + 1) * 4 / 5)`, 1-based. No interpolation. |
| `half_width_cents_per_kwh` | Order statistic `e(k)` when an interval is emitted. Empty when history is insufficient. |
| `lower_cents_per_kwh` | Point forecast minus the half-width. |
| `upper_cents_per_kwh` | Point forecast plus the half-width. |
| `interval_status` | `interval`, or `insufficient_residual_history` when `n < 24` or `k > n`. |
| `covered` | Whether the actual lies inside the closed interval. Empty when no interval was emitted. |

## Ridge explanation columns

Built in `src/infralens/evaluation/explain.py` from the Ridge pipeline fitted at that forecast origin. They are not columns in the interim Parquet, not additional model features, and not causal effects. Ridge is refit at every origin, so a coefficient from one origin is not the InfraLens model. Numeric values are the raw feature and the within-origin standardized value. State and month terms are one-hot contrasts against the category dropped by that origin's encoder. On the scored development origins those references are Maryland and month `01`. A dropped reference has no coefficient column.

| Column | Definition |
| --- | --- |
| `transformed_feature_name` | Pipeline column, such as `num__price_latest` or `cat__state_id_NJ`. |
| `feature_group` | `numeric`, `state`, or `month`. Compare magnitudes only inside a group. |
| `category` | One-hot level for a state or month term. Empty for a numeric term. |
| `raw_numeric_value` | Feature value before standardization. Empty for a categorical term. |
| `transformed_value` | Standardized numeric value, or 0/1 for a one-hot column. |
| `coefficient` | Ridge coefficient on that transformed column at this origin. |
| `contribution` | `transformed_value * coefficient`, in ¢/kWh. |
| `scaler_mean` / `scaler_scale` | Training-fold scaler parameters for a numeric term. |
| `reference_state` / `reference_month` | Categories dropped by this origin's encoder. |

## PJM zonal screening, Slice 1

Separate from the EIA price model. Grain is one row per `pjm_zone` × `ltlf_vintage_year` × `forecast_year` from PJM Table B1. Implemented vintages are the 2025 and 2026 Tables workbooks only. There is no join to `state_id`. The display-only zone/state notes live in `docs/pjm_screening_schema.md`.

A row may be used only when `vintage_available_at <= as_of_date`. Missing dates fail closed. The 2026 Tables workbook is available on 2026-02-06 even though its original LAS listing is 2026-01-14. The 2026-01-14 report PDF is a different file and is not this table.

| Name | Source | Definition | Unit | Role |
| --- | --- | --- | --- | --- |
| `pjm_zone` | Table B1 column A | Transmission-owner zone code. The 22 verified codes are AE, BGE, DPL, JCPL, METED, PECO, PENLC, PEPCO, PL, PS, RECO, UGI, AEP, APS, ATSI, COMED, DAYTON, DEOK, DLCO, EKPC, OVEC, DOM. RTO, regional, diversity, `FE-EAST`, and `PLGRP` rows are not zones. | Code | Entity key |
| `ltlf_vintage_year` | InfraLens manifest | 2025 or 2026. The product year, not the publication date. | Year | Entity key |
| `original_release_date` | LAS listing | 2025-01-24 or 2026-01-14. | Date | Provenance |
| `revision_date` | Stored Tables file | Null for 2025. 2026-02-06 for the 2026 Tables workbook. | Date or null | Provenance |
| `vintage_available_at` | File-level rule | Revision date when the stored file is a revision, otherwise the original release. | Date | Point-in-time gate |
| `forecast_year` | Table B1 year header | Horizon year. `Metered` and `Unrestricted` prior-year columns are excluded. | Year | Entity key |
| `summer_peak_mw` | Table B1 forecast-year cell | Published summer peak. Stored in MW with no rescale. | MW | Screening measure |
| `summer_peak_10yr_cagr` | Table B1 `Annual Growth Rate (10 yr)` | Official decimal growth rate on the zone row, repeated for each forecast year of that vintage. AE in 2026 is approximately 0.0007776089. | Decimal per year | Screening measure |
| `source_url` | InfraLens manifest | Official PJM URL of the Tables workbook. | URL | Lineage |
| `source_file` | InfraLens manifest | Gitignored local workbook name. | Text | Lineage |
| `retrieved_at` | Caller | Retrieval timestamp when supplied. | Timestamp or null | Lineage |

Not in Slice 1, and not filled with zero: 2024 Table B1. The revised PDF is the structured source for that vintage. The 2024 Data workbook is monthly peak and energy. Slice 2, below, replaces the unused single column `large_load_adjustment_mw` with two measures. `has_data_center_adjustment` is still not written.

## PJM zonal screening, Slice 2

Same Tables workbooks and the same file-level dates as Slice 1. Grain is one row per `pjm_zone` × `ltlf_vintage_year` × `forecast_year` × `adjustment_measure`. There is no join to `state_id` and no risk score.

B-9, `above_embedded_mw`, is “Adjustments Above Embedded to Summer Peak Load (MW)”. B-9b, `total_associated_mw`, is “Total Load Associated with Adjustments to Summer Peak Load (MW)”. Both are MW. Published zeros stay zero. Published negatives stay negative. A blank cell is an error. The two measures are not added. Neither is data-center demand: these sheets do not say that, and the 2024 PDF note that mentions data centers also lists other adjustments in the same kind of MW column.

Horizons read from the year headers: 2025–2045 and 2026–2046, 21 years each, 22 zones, 1,848 rows. The `PJM RTO` row on each sheet is not emitted. AEP forecast year 2026 is 1,913 MW on B-9 and 2,699 MW on B-9b.

| Name | Source | Definition | Unit | Role |
| --- | --- | --- | --- | --- |
| `adjustment_measure` | Sheet identity | `above_embedded_mw` or `total_associated_mw`. | Code | Entity key |
| `adjustment_mw` | B-9 or B-9b year cell | Published adjustment for that measure. | MW | Screening measure |
| `source_table` | Sheet identity | `B-9` or `B-9b`. | Text | Lineage |
| `forecast_year` | Year header on that sheet | Horizon year. Not taken from Table B1. | Year | Entity key |

`pjm_zone`, vintage, `original_release_date`, `revision_date`, `vintage_available_at`, `source_url`, `source_file`, and `retrieved_at` mean the same thing as in Slice 1. `retrieved_at` is required on the Slice 2 production load and is not invented.

## PJM screening view

`screen_zone_year` selects one vintage for one zone and forecast year. The vintage must have `vintage_available_at <= as_of_date` and one B1 row, one B-9 row, and one B-9b row for that exact zone and year. Newer public vintages win. Fields are not mixed across vintages. `compare_zone_year_vintages` lists those complete public vintages separately.

`available=False` means no covering vintage was public. Measures are null in that case only. The newest public vintage with a missing series, a duplicate key, or disagreeing dates raises rather than falling back. An older incomplete vintage does not block that newer result. The comparison function raises if any public vintage it would list is incomplete. Published zeros and negatives pass through. There is no risk score and no data-center label.

`source_urls` and `retrieved_at` are ordered Table B1, B-9, B-9b. The 2024 vintage is not implemented, so an as-of date before 2025-01-24 has no row when the caller passes only the 2025 and 2026 extracts. AEP forecast year 2026 on 2025-06-30 uses the 2025 vintage: summer peak 25,788 MW, 10-year decimal 0.0547154909, B-9 3,621 MW, B-9b 3,936 MW. The same query on 2026-02-06 uses the 2026 vintage: 24,635 MW, 0.0525293343, 1,913 MW, and 2,699 MW.

ATSI overlaps both Ohio and Pennsylvania (Penn Power). That overlap is a display qualification. It is not a key and not a weight on `summer_peak_mw`.

## Quality notes (observed, not edited)

- Missing values: none in the interim Parquet. Duplicates on `state_id` × `period` × `sector_id`: none.
- Prices rose from a 2001 mean of about 7.7 ¢/kWh to about 13.5 ¢/kWh in 2025–2026. That is a trend, not a processing error.
- Largest month-to-month price move: Maryland 2014-09 jumped to 16.32 ¢/kWh from 10.35 in 2014-08, then 10.25 in 2014-10. Revenue rose while sales fell that month; the price identity still holds. Other notable moves include NJ summer 2008 and VA 2026-02 (13.01 ¢/kWh) then 2026-03 (10.16). Rows were not removed or altered.
- This series remains a **public commercial-price proxy**. It is not parcel-level, interconnection, or PPA pricing.

## References

- EIA, API documentation, `electricity/retail-sales` metadata (units and forms EIA-826 / EIA-861 / EIA-861M).
- EIA FAQ, “Does EIA publish electricity sales and price data by state and by utility?” (average price = revenue / kWh; delivered costs including T&D, taxes, and fees).
- EIA Electric Power Monthly Table 5.6.A (cents per kilowatthour; current release lag example only).

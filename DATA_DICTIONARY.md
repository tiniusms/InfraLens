# InfraLens Data Dictionary

First feasibility extract only. No feature engineering or modeling. Values below describe the live EIA pull retrieved `2026-09-10T03:59:06Z`.

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
| `price_cents_per_kwh` | EIA `price` | Average commercial retail price to ultimate customers. EIA-derived average (revenue / kWh), not a data-center tariff. **Primary ML target proxy** (12-month-ahead). | Cents per kWh | Monthly | Target (current value); not yet lagged | 2001-01 to 2026-06 | TBD | High if future months or post-revision vintages are used as features. Target at t+12 must not appear in features at origin t. |
| `sales_million_kwh` | EIA `sales` | Commercial electricity sold to ultimate customers. | Million kWh | Monthly | Supporting measure (not a feature yet) | 2001-01 to 2026-06 | TBD | High if contemporaneous or future sales are used to predict future price without a lag rule. |
| `revenue_million_usd` | EIA `revenue` | Revenue from commercial sales to ultimate customers. | Million USD | Monthly | Supporting measure (not a feature yet) | 2001-01 to 2026-06 | TBD | Same as sales. Algebraically tied to price. |
| `price_units` | EIA `price-units` | Unit string supplied by the API. | Text | Monthly | Metadata | All rows | n/a | None. |
| `sales_units` | EIA `sales-units` | Unit string supplied by the API. | Text | Monthly | Metadata | All rows | n/a | None. |
| `revenue_units` | EIA `revenue-units` | Unit string supplied by the API. | Text | Monthly | Metadata | All rows | n/a | None. |
| `frequency` | EIA request / `frequency` | `monthly`. | Text | Constant | Metadata | All rows | n/a | None. |
| `retrieved_at` | InfraLens extract | UTC timestamp when this API payload was retrieved. | Timestamp | Extract-level | Lineage | 2026-09-10T03:59:06Z | Known (extract time only) | Does not make historical months point-in-time valid. |
| `assumed_available_at` | InfraLens evaluation assumption | First day of month *m+3* for `period` *m*. Conservative stand-in for EPM lag; **not** an EIA first-publication or revision timestamp. | Date | Monthly | Leakage control | Derived for every row | Assumed (m+3-01) | If ignored, future-of-origin information can leak into the baseline. |
| `source` | InfraLens | `U.S. Energy Information Administration`. | Text | Constant | Lineage | All rows | n/a | None. |
| `source_route` | InfraLens | `/v2/electricity/retail-sales/data/`. | Text | Constant | Lineage | All rows | n/a | None. |
| `source_url` | InfraLens | HTTPS endpoint used for retrieval (no key). | URL | Constant | Lineage | All rows | n/a | None. |

## Quality notes (observed, not edited)

- Missing values: none in the interim Parquet. Duplicates on `state_id` × `period` × `sector_id`: none.
- Prices rose from a 2001 mean of about 7.7 ¢/kWh to about 13.5 ¢/kWh in 2025–2026. That is a trend, not a processing error.
- Largest month-to-month price move: Maryland 2014-09 jumped to 16.32 ¢/kWh from 10.35 in 2014-08, then 10.25 in 2014-10. Revenue rose while sales fell that month; the price identity still holds. Other notable moves include NJ summer 2008 and VA 2026-02 (13.01 ¢/kWh) then 2026-03 (10.16). Rows were not removed or altered.
- This series remains a **public commercial-price proxy**. It is not parcel-level, interconnection, or PPA pricing.

## References

- EIA, API documentation, `electricity/retail-sales` metadata (units and forms EIA-826 / EIA-861 / EIA-861M).
- EIA FAQ, “Does EIA publish electricity sales and price data by state and by utility?” (average price = revenue / kWh; delivered costs including T&D, taxes, and fees).
- EIA Electric Power Monthly Table 5.6.A (cents per kilowatthour; current release lag example only).

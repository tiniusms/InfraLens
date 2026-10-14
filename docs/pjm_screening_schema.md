# PJM zonal screening schema

**Status:** Slice 1 is implemented for 2025 and 2026 Table B1 only (`src/infralens/screening/`). Not an ML feature spec. No risk score and no investment ranking.

Version 1 keeps EIA as the **state-level monthly price-forecasting layer**. This schema is a **separate zonal screening layer**. Do not join these columns onto the EIA model matrix. Do not aggregate zones to VA/PA/OH/MD/NJ for modeling.

Reserved EIA holdout (target months 2025-07 through 2026-06) is untouched.

## Availability rule

For the artifact InfraLens stores:

```
vintage_available_at = revision_date if revision_date is not null else original_release_date
```

Dashboard and any later point-in-time view may show a vintage only when `vintage_available_at <= as_of_date`. Using the revised 2024 library PDF/XLS requires `vintage_available_at = 2024-02-01`, even though LAS lists the original 2024 report at 2023-12-27.

## Grain

One row per **`pjm_zone` × `ltlf_vintage_year` × `forecast_year`**.

Vintage-level attributes (`summer_peak_10yr_cagr`, dates, source) repeat across forecast years of that vintage. That is intentional for a single small table. `has_data_center_adjustment` is not populated in Slice 1.

TO **zone** grain (AE, AEP, APS, …), not sub-zone (APP, PED, …), unless a vintage’s Tables/Data file only publishes sub-zones for a field. Sub-zones belong in overlap notes, not as extra ML keys.

## Minimum columns

| Column | Type | Definition |
| --- | --- | --- |
| `pjm_zone` | text | Slice 1. PJM transmission-owner zone code from Table B1. Verified 2025 and 2026 codes, in sheet order: AE, BGE, DPL, JCPL, METED, PECO, PENLC, PEPCO, PL, PS, RECO, UGI, AEP, APS, ATSI, COMED, DAYTON, DEOK, DLCO, EKPC, OVEC, DOM. |
| `ltlf_vintage_year` | int | Slice 1. Forecast product year. Implemented vintages are 2025 and 2026. Not the availability date. |
| `original_release_date` | date | Slice 1. First LAS listing of that vintage. 2025-01-24 or 2026-01-14. |
| `revision_date` | date or null | Slice 1. Later stamp on the stored Tables file. Null for the 2025 workbook. 2026-02-06 for the 2026 Tables workbook. |
| `vintage_available_at` | date | Slice 1. Date the stored file may be used. 2025-01-24, or 2026-02-06 for the 2026 Tables workbook. |
| `forecast_year` | int | Slice 1. Calendar year on a Table B1 forecast header. Prior-year `Metered` and `Unrestricted` columns are not forecast years. |
| `summer_peak_mw` | float | Slice 1. Summer peak from that forecast-year column, in MW, unmodified. |
| `summer_peak_10yr_cagr` | float | Slice 1. Official `Annual Growth Rate (10 yr)` decimal on the zone row. Repeated across `forecast_year`. Not the percent text on the following row. |
| `source_url` | text | Slice 1. Official PJM URL for the Tables workbook. |
| `source_file` | text | Slice 1. Local gitignored filename. |
| `retrieved_at` | timestamp or null | Slice 1. UTC retrieval time when the caller supplies one. Null on a fixture that was not downloaded. |

Deferred columns, not written by Slice 1:

| Column | Why it stays empty |
| --- | --- |
| `large_load_adjustment_mw` | Table B-9 and Table B-9b are different series. They must be separate future fields. Slice 1 does not choose one or fill the other with zero. |
| `has_data_center_adjustment` | Adjustment MW is not data-center demand. The 2024 B-9 note mixes data-center growth with peak shaving, port electrification, a chip-processing plant, and behind-the-meter generation moving to demand response. The 2025 and 2026 Tables workbooks do not label B-9 as data-center load. |

Optional later: winter peak, net energy, LDA/RTO rows, the separate B-9 and B-9b fields, 2024 PDF Table B1, mid-year vintage flag. The 2026-07-24 mid-year workbook stays out.

## What this is not

- Not a state-month panel and not an EIA feature.
- Not Data Miner.
- Not a license to use 2026 LTLF at a 2024-06-30 EIA origin (`vintage_available_at` would fail).
- Not a claim that zonal peak growth causes commercial retail price.

## Slice 1 vintages

Code parses the **2025 and 2026 Tables workbooks, Table B1 only**. The 2024 row remains a documented source and is not parsed. `load_slice1_tables` requires a caller-supplied `retrieved_at` and then checks the parsed rows: unique zone-vintage-forecast-year keys, the verified 22 zone codes, a complete forecast-year grid, finite numeric peak and growth values, and source URL, filename, and file-level dates taken from the manifest. It does not read publication dates out of the workbook and does not fill a missing cell with zero.

| Vintage | `original_release_date` | `revision_date` on current library file | `vintage_available_at` |
| --- | --- | --- | --- |
| 2024 | 2023-12-27 | 2024-02-01 | 2024-02-01 |
| 2025 | 2025-01-24 | null. The 2025 Tables workbook has no revision string. | 2025-01-24 |
| 2026 | 2026-01-14 | 2026-02-06 on the stored Tables workbook | 2026-02-06 |

The 2026 in-file note dated 2026-02-06 is on Table B-9 (“updated 2/6/2026 to correct for an error calculating embedded”). Slice 1 still dates the whole stored Tables workbook as available on 2026-02-06. It does not assign Table B1 an earlier date, and it does not claim that B1 itself changed on that day. A 2026-01-14 view can see the report PDF’s original listing and still cannot use this Tables file.

2024 has no Tables workbook on the LAS page. Its Data workbook is monthly `PEAK_MW` and `ENERGY_GWH`, not Table B1. Parsing 2024 summer peak still requires the revised PDF. That parser is not in Slice 1.

## Recorded ambiguities

- Forecast-year headers are the year alone. The word `Unrestricted` labels the prior-year history column. Slice 1 stores the forecast-year summer peak in MW and does not copy that history column into `forecast_year`.
- The 10-year rate is the published decimal. AE in the 2026 workbook is about `0.0007776089`, which is 0.0778 percent per year. Slice 1 does not multiply by 100.
- Published zeros and published negative rates stay as published. A blank cell is an error.
- B-9 and B-9b differ (105 cells in each of the 2025 and 2026 workbooks, including AEP). They are not interchangeable names for one adjustment.
- Data-workbook sheet names such as `DAY`, `JCPL_FE_EAST`, and `PN_FE_EAST` are not Table B1 zone codes. Table B1 uses `DAYTON`, `JCPL`, and `PENLC`.

## Display-only zone/state reference (not an ML join)

Many-to-many overlap of 2026 TO zones with user-facing states. Extra states in the same zone are listed so a state page never implies the zone is that state alone.

**Label: display / screening only. Do not use as a modeling join or to allocate MW to EIA `state_id`.**

| `pjm_zone` | `state_id` | `overlap_note` |
| --- | --- | --- |
| AE | NJ | Southern New Jersey (Atlantic Electric). |
| AEP | OH | Ohio Power / Columbus Southern and other AEP Ohio territory; zone also includes VA, WV, KY, IN, MI. |
| AEP | VA | Appalachian Power sub-zone (APP) in Virginia; zone is multi-state. |
| APS | MD | Potomac Edison (PED) in Maryland; zone also includes WV, VA, PA. |
| APS | VA | PED / APS territory in Virginia; zone is multi-state. |
| APS | PA | West Penn Power (WP) in Pennsylvania; zone is multi-state. |
| ATSI | OH | Northern Ohio utilities in this zone include CEI, Ohio Edison, and Toledo Edison. The zone also includes Pennsylvania, so this row is not an Ohio-only peak. |
| ATSI | PA | Penn Power in western Pennsylvania. The 2026 total-load-adjustments workbook labels an ATSI area `PP` beside an `OHIO` area. Display qualification only: do not allocate ATSI MW to Pennsylvania, Ohio, or an EIA `state_id`. |
| BGE | MD | Baltimore Gas & Electric; Maryland-aligned. |
| DAYTON | OH | Dayton Power & Light; Ohio-aligned. |
| DEOK | OH | Duke Ohio/Kentucky; also Kentucky. Not “Ohio only.” |
| DLCO | PA | Duquesne; Pittsburgh area. |
| DOM | VA | Dominion Virginia Power; also North Carolina. Not a Virginia-only peak. |
| DPL | MD | Delmarva; also Delaware and Virginia Eastern Shore. Not New Jersey. |
| DPL | VA | Delmarva Eastern Shore Virginia; also DE and MD. |
| JCPL | NJ | Jersey Central Power & Light. |
| METED | PA | Metropolitan Edison. |
| OVEC | OH | Ohio Valley Electric Corporation; also KY/IN. |
| PECO | PA | PECO Energy; southeastern Pennsylvania. |
| PENLC | PA | Pennsylvania Electric (Penelec). |
| PEPCO | MD | Potomac Electric Power; Maryland **and District of Columbia**. |
| PL | PA | PPL Electric Utilities. Table B1 publishes PL as its own zone row. |
| PS | NJ | Public Service Electric & Gas. |
| RECO | NJ | Rockland Electric East; also New York. |
| UGI | PA | UGI. The 2025 and 2026 Table B1 sheets publish UGI as its own zone row. `PLGRP` is an aggregate elsewhere on the sheet, not a second copy of PL or UGI. |

Do not map DPL to NJ. New Jersey zones are AE, JCPL, PS, and RECO only.

Zones in the 2026 report that do **not** belong on VA/PA/OH/MD/NJ screening pages: **COMED**, **EKPC**, and any other zone with no overlap. They may still appear in an all-zone extract but must not be shown as if they were those five states.

## Storage and licensing

- Raw PDF/XLS: `data/raw/pjm/`, gitignored, immutable once downloaded.
- Derived Slice 1 table: Parquet under `data/processed/pjm/`, gitignored with the rest of `data/processed/`. Do not commit raw workbooks or generated binaries.
- Record `source_url`, `source_file`, and `retrieved_at` on every row.

Implemented fields are in `DATA_DICTIONARY.md`. Deferred B-9 fields are described there and are not EIA features.

# PJM zonal screening schema (proposal only)

**Status:** Design for the next implementation task. Not ingested. Not an ML feature spec.

Version 1 keeps EIA as the **state-level monthly price-forecasting layer**. This schema is a **separate zonal screening / risk layer**. Do not join these columns onto the EIA model matrix. Do not aggregate zones to VA/PA/OH/MD/NJ for modeling.

Reserved EIA holdout (target months 2025-07 through 2026-06) is untouched.

## Availability rule

For the artifact InfraLens stores:

```
vintage_available_at = revision_date if revision_date is not null else original_release_date
```

Dashboard and any later point-in-time view may show a vintage only when `vintage_available_at <= as_of_date`. Using the revised 2024 library PDF/XLS requires `vintage_available_at = 2024-02-01`, even though LAS lists the original 2024 report at 2023-12-27.

## Grain

One row per **`pjm_zone` × `ltlf_vintage_year` × `forecast_year`**.

Vintage-level attributes (`summer_peak_10yr_cagr`, `has_data_center_adjustment`, dates, source) repeat across forecast years of that vintage. That is intentional for a single small table.

TO **zone** grain (AE, AEP, APS, …), not sub-zone (APP, PED, …), unless a vintage’s Tables/Data file only publishes sub-zones for a field. Sub-zones belong in overlap notes, not as extra ML keys.

## Minimum columns

| Column | Type | Definition |
| --- | --- | --- |
| `pjm_zone` | text | PJM transmission-owner zone code as in that vintage’s tables (2026 report list: AE, AEP, APS, ATSI, BGE, COMED, DAYTON, DEOK, DLCO, DOM, DPL, EKPC, JCPL, METED, OVEC, PECO, PENLC, PEPCO, PL, PS, RECO, UGI). Confirm exact codes per vintage on ingest. |
| `ltlf_vintage_year` | int | Forecast product year (2024, 2025, 2026). Not the availability date. |
| `original_release_date` | date | First LAS/library posting of that vintage (2024 = 2023-12-27). |
| `revision_date` | date or null | Later revision of the stored artifact (2024 revised PDF = 2024-02-01). Null if no revision evidence. |
| `vintage_available_at` | date | Conservative date the stored bytes could be used at an origin. |
| `forecast_year` | int | Calendar year of the forecasted summer peak (the horizon year inside the vintage). |
| `summer_peak_mw` | float | Unrestricted summer peak (MW) for that zone, vintage, and forecast year. |
| `summer_peak_10yr_cagr` | float | Annualized 10-year summer-peak growth rate for that zone and vintage (repeated across `forecast_year`). |
| `large_load_adjustment_mw` | float or null | Table B-9 / B-9b (or vintage equivalent) large-load / data-center adjustment MW. Null if the vintage has no table. |
| `has_data_center_adjustment` | bool | True if that vintage lists a data-center (or equivalent large-load) adjustment for the zone. |
| `source_url` | text | Official PJM URL for the file used. |
| `source_file` | text | Local gitignored filename (PDF/XLS). |
| `retrieved_at` | timestamp | UTC time InfraLens downloaded the file. |

Optional later (not MVP): winter peak, net energy, LDA/RTO rows, B-9 vs B-9b split, mid-year vintage flag.

## What this is not

- Not a state-month panel and not an EIA feature.
- Not Data Miner.
- Not a license to use 2026 LTLF at a 2024-06-30 EIA origin (`vintage_available_at` would fail).
- Not a claim that zonal peak growth causes commercial retail price.

## MVP vintages

Parse **2024, 2025, and 2026** only.

| Vintage | `original_release_date` | `revision_date` on current library file | `vintage_available_at` |
| --- | --- | --- | --- |
| 2024 | 2023-12-27 | 2024-02-01 | 2024-02-01 |
| 2025 | 2025-01-24 | null unless ingest finds one | 2025-01-24 |
| 2026 | 2026-01-14 | 2026-02-06 if the stored Tables/Data XLS is the 2.6.2026 post; else null | later of those dates for the stored file |

2024 has no Tables XLS on Reports & Notices; implementation may read Data XLS or PDF tables. That is a parser difference, not a reason to pull 2020–2023 now.

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
| ATSI | OH | Northern Ohio (CEI, Ohio Edison, Penn Power, Toledo Edison sub-zones). |
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
| PL | PA | PPL; UGI is a PLGroup sub-zone also in PA. |
| PS | NJ | Public Service Electric & Gas. |
| RECO | NJ | Rockland Electric East; also New York. |
| UGI | PA | UGI; listed separately if the vintage publishes UGI as its own table row. |

Do not map DPL to NJ. New Jersey zones are AE, JCPL, PS, and RECO only.

Zones in the 2026 report that do **not** belong on VA/PA/OH/MD/NJ screening pages: **COMED**, **EKPC**, and any other zone with no overlap. They may still appear in an all-zone extract but must not be shown as if they were those five states.

## Storage and licensing

- Raw PDF/XLS: `data/raw/pjm/`, gitignored, immutable once downloaded.
- Derived screening table: small Parquet/CSV under `data/processed/` may be committed only if still compatible with PJM public-report terms; otherwise gitignore derived binaries too and commit a tiny CSV extract plus source URLs.
- Record `source_url`, `source_file`, `retrieved_at` on every row.

Dictionary rows for these columns belong in `DATA_DICTIONARY.md` **when ingest lands**, not before.

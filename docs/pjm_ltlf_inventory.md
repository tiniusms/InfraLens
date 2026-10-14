# PJM Long-Term Load Forecast inventory (research only)

Research snapshot: **2026-09-28**. Official PJM pages and report headers only.

Slice 1 code, added 2026-10-14, parses Table B1 from the 2025 and 2026 Tables workbooks only. It does not parse the 2024 PDF, the Data workbooks, Table B-9, or Table B-9b.

This note corrects the earlier inventory on **original release vs later revision**. Forecast year in a filename is not an availability date.

## Date rules

| Field | Meaning |
| --- | --- |
| `original_release_date` | First public posting of that vintage, from the [Load Analysis Subcommittee](https://www.pjm.com/committees-and-groups/subcommittees/las) Load Forecast Reports table when listed. |
| `revision_date` | Later in-document revision stamp or a later process-page post of the **same** artifact. |
| `vintage_available_at` | Date an InfraLens origin may use **the file InfraLens actually stores**. If that file is a revision, this is the revision date, not the original release. |

`vintage_available_at = revision_date` if a revision applies to the stored artifact, else `original_release_date`.

Do not treat Inside Lines news dates, LAS preliminary decks, or “January YYYY” cover titles as availability for a revised spreadsheet or PDF.

## Vintage calendar (candidate sources)

| LTLF vintage | LAS original listing | In-document / later stamp | Conservative `vintage_available_at` if using the currently posted library file | Tables XLS on Reports & Notices? | Data XLS? |
| --- | --- | --- | --- | --- | --- |
| 2026 | **2026-01-14** ([LAS](https://www.pjm.com/committees-and-groups/subcommittees/las); PDF Posted Date January 14, 2026) | Process page also lists **2026-02-06** for the 2026 bundle (Tables/Data/ZIP/supplement/adjustment breakdown). No “Revised” banner on the 2026 report PDF. | **2026-01-14** for the report PDF. **2026-02-06** for any XLS whose process-page date is 2.6.2026 until ingest confirms the file was unchanged on 1.14.2026. | Yes | Yes |
| 2025 | **2025-01-24** (LAS) | Prior header check: Posted Date January 24, 2025. No revision stamp found. | **2025-01-24** unless ingest finds a later banner. | Yes | Yes |
| 2024 | **2023-12-27** (LAS: “2024 PDF \| 12.27.2023”) | PDF marked **Revised 2/1/2024**. Cover still says January 2024. [Inside Lines](https://insidelines.pjm.com/pjm-publishes-2024-long-term-load-forecast/) news post **2024-01-08** is a public announcement, not the LAS original listing and not the revision. | **2024-02-01** for the revised PDF/XLS now on the library. Do **not** use 2023-12-27 or 2024-01-08 as availability for that revised artifact. | Not listed (PDF + Data XLS only) | Yes |
| 2023 | **2023-05-22** (LAS) | Cover historically “January 2023”; LAS date is months later, so treat 2023-05-22 as the conservative availability of the **currently posted** PDF until a revision banner is confirmed. | **2023-05-22** if using the posted file. Not in MVP ingest. | Not listed | Yes |
| 2022 | **2021-12-30** (LAS) | No revision evidence collected. | **2021-12-30** pending ingest header check. Not in MVP ingest. | Not listed | Yes |
| 2021 | **2020-12-30** (LAS) | No revision evidence collected. | **2020-12-30** pending ingest header check. Not in MVP ingest. | Not listed | Yes |
| 2020 | **2019-12-30** (LAS) | No revision evidence collected. | **2019-12-30** pending ingest header check. Not in MVP ingest. | Not listed | Yes |

2024 Inside Lines peak figures differ from the revised PDF (example: 2034 summer peak 178,895 MW in the 2024-01-08 article vs 176,822 MW in the revised report). That is evidence the February revision changed numbers. Using the current 2024 file at a 2023-12-27 origin would leak the revision.

## Source inventory

### 1. Load Analysis Subcommittee — Load Forecast Reports
- **URL:** https://www.pjm.com/committees-and-groups/subcommittees/las
- **File type:** HTML index
- **Publication dates:** LAS table (2026-01-14, 2025-01-24, 2024 listed 2023-12-27, 2023 listed 2023-05-22, 2022–2020 listed 12-30 of the prior year)
- **Forecast/reference period:** Catalog of annual LTLF vintages
- **Geography:** n/a
- **Useful fields:** Original-release calendar; links to Report PDF / Tables XLS
- **Point-in-time suitability:** Yes, for `original_release_date`
- **Revision/vintage risk:** The linked file may later be replaced; LAS date is original listing, not a guarantee the current bytes match that day
- **Redistribution:** Public committee page; not Data Miner
- **Recommendation:** **USE** (authoritative original-release dates)

### 2. Load Forecast Development Process
- **URL:** https://www.pjm.com/planning/resource-adequacy-planning/load-forecast-dev-process
- **File type:** HTML index
- **Publication dates listed:** 2026 LTLF **2026-02-06** and **2026-01-14**; Mid-Year Update **2026-07-24**; Load Adjustment Breakdown **2026-02-06**; Data Center Accuracy **2026-05-29**
- **Forecast/reference period:** Current vintage plus Previous Reports ZIP
- **Geography:** n/a
- **Useful fields:** File-level post dates that can be later than LAS original release
- **Point-in-time suitability:** Yes, as a check on `revision_date` / file update
- **Revision/vintage risk:** Bundle dates mix PDF and XLS; assign dates per file on ingest
- **Redistribution:** Public planning page; not Data Miner
- **Recommendation:** **USE**

### 3. Reports & Notices — Load Forecast archive
- **URL:** https://www.pjm.com/library/reports-notices
- **File type:** HTML archive
- **Years:** 2026–2016 still listed. 2026–2025: Report PDF + Tables XLS + Data XLS. 2024–2016: Report PDF + Data XLS (no Tables XLS in that listing)
- **Forecast/reference period:** One long-term vintage per year
- **Geography:** n/a
- **Useful fields:** Stable library URLs
- **Point-in-time suitability:** Yes if each year’s files remain archived
- **Revision/vintage risk:** Same URL can hold a revised file (2024)
- **Redistribution:** Public library documents, PJM copyright
- **Recommendation:** **USE**

### 4. 2026 Long-Term Load Forecast — Report PDF
- **URL:** https://www.pjm.com/-/media/DotCom/library/reports-notices/load-forecast/2026-load-report.pdf
- **File type:** PDF (“For Public Use”); Posted Date January 14, 2026
- **Forecast/reference period:** 20-year zonal / LDA / RTO peaks, net energy, load management, DG solar, EVs, storage
- **Geography:** TO zone and sub-zone, LDA, RTO — **not state**
- **Useful fields:** Zonal summer/winter unrestricted peaks; 10-/20-year growth; data-center / large-load adjustment narrative; zone abbreviation list
- **Point-in-time suitability:** After 2026-01-14
- **Revision/vintage risk:** Mid-year informational XLS exists (2026-07-24); do not back-apply it
- **Redistribution:** Public report, PJM ©; cite URL; do not commit the PDF
- **Recommendation:** **USE** (documentation + zone list)

### 5. 2026 LTLF Tables XLS
- **URL:** Linked from LAS and the process page as “Tables XLS”
- **File type:** XLS
- **Dates:** LAS **2026-01-14**; process page also **2026-02-06**
- **Forecast/reference period / geography:** Same 20-year zonal/LDA/RTO tables; report states tables live in Excel, including **B-9** and **B-9b**
- **Useful fields:** Structured zonal peaks, growth rates, large-load / data-center adjustment MW
- **Point-in-time suitability:** Yes; conservative availability **2026-02-06** until ingest proves the LAS 1.14.2026 bytes
- **Revision/vintage risk:** Same-URL overwrite
- **Redistribution:** Public planning file; gitignore raw XLS
- **Recommendation:** **USE** (primary 2026 structured source)

### 6. 2026 LTLF Data XLS
- **URL:** “Data XLS” on process page and Reports & Notices
- **File type:** XLS
- **Date:** Process page **2026-01-14** (bundle also shows 2.6.2026)
- **Useful fields:** Supporting model/weather/end-use detail
- **Point-in-time suitability:** 2026 vintage after the file’s own post date
- **Revision/vintage risk:** Same-URL overwrite
- **Redistribution:** Same as Tables XLS
- **Recommendation:** **USE WITH CAUTION** (not required for the smallest dashboard MVP)

### 7. Previous Reports ZIP
- **URL:** Process page “Previous Reports ZIP”
- **File type:** ZIP of prior LTLF vintages
- **Date:** Listed with 2026 materials (1.14.2026 / 2.6.2026)
- **Point-in-time suitability:** Snapshot of historical files as of that post
- **Revision/vintage risk:** Contents are whatever PJM packed on that date
- **Recommendation:** **USE** as an archive fallback; do not commit the ZIP. Not needed if 2024–2026 library links still resolve.

### 8. 2025 LTLF Report PDF + Tables XLS + Data XLS
- **URLs:** Library `.../load-forecast/2025-load-report.pdf` plus Tables/Data XLS from LAS / Reports & Notices
- **Dates:** LAS **2025-01-24**
- **Geography / fields:** Same zonal 15–20 year framework as 2026
- **Point-in-time suitability:** After 2025-01-24 if no later revision is found
- **Revision/vintage risk:** Confirm header on ingest
- **Recommendation:** **USE** (MVP vintage)

### 9. 2024 LTLF Report PDF + Data XLS
- **URL (PDF):** https://www.pjm.com/-/media/DotCom/library/reports-notices/load-forecast/2024-load-report.pdf
- **Dates:** LAS original **2023-12-27**; Inside Lines announcement **2024-01-08**; PDF **Revised 2024-02-01**
- **Forecast/reference period:** January 2024 long-term vintage (15-year peaks in this report)
- **Geography:** Zone / LDA / RTO
- **Useful fields:** Zonal peaks and growth; 2024-era large-load / data-center adjustments (AEP, APS, DOM, PS among others)
- **Point-in-time suitability:** Original vintage was public 2023-12-27, but **InfraLens does not hold that unrevised file**. Using the library artifact → **`vintage_available_at = 2024-02-01`**
- **Revision/vintage risk:** **High.** Numbers changed between announcement and revised PDF. No Tables XLS in the Reports & Notices listing; parsing may need Data XLS or PDF tables
- **Recommendation:** **USE** as the third MVP vintage, with the February 1 availability rule

### 10. 2020–2023 LTLF PDFs + Data XLS
- **URLs:** `YYYY-load-report.pdf` on Reports & Notices
- **LAS dates:** 2023-05-22; 2021-12-30; 2020-12-30; 2019-12-30
- **Point-in-time suitability:** Reconstructible in principle; 2023 needs original-vs-revision care
- **Recommendation:** **USE WITH CAUTION** for later point-in-time proofs. **Do not ingest for dashboard MVP.** Coverage is still far shorter than the EIA development window (origins from 2002).

### 11. 2026 Load Adjustment Breakdown for Capacity Obligations
- **URL:** Process page XLS, **2026-02-06**
- **Recommendation:** **USE WITH CAUTION** (capacity-obligation view; not needed for MVP)

### 12. 2026 Mid-Year Update (informational)
- **URL:** Process page XLS, **2026-07-24**
- **Point-in-time suitability:** Only origins ≥ 2026-07-24
- **Recommendation:** **DO NOT USE** in Version 1 dashboard MVP or any EIA backtest

### 13. 2026 Data Center Accuracy Report + Data XLS
- **URL (PDF):** https://www.pjm.com/-/media/DotCom/planning/res-adeq/load-forecast/2026-load-forecast-accuracy-report.pdf
- **Posted:** **2026-05-29**
- **Geography:** Zone / EDC / LSE dashboards
- **Useful fields:** Forecast vs operational large-load; not a substitute for 2024–2025 LTLF files
- **Point-in-time suitability:** After 2026-05-29 only
- **Recommendation:** **USE WITH CAUTION** as later screening narrative. **Not in MVP ingest.**

### 14. PJM zone map
- **URL:** https://www.pjm.com/-/media/DotCom/about-pjm/pjm-zones.pdf
- **File type:** PDF (map dated 2023-05-11)
- **Recommendation:** **USE** for geography documentation only

### 15. Data Miner 2
- **URL:** https://www.pjm.com/markets-and-operations/etools/data-miner-2
- **Terms:** Internal use; redistribution of data or derivatives prohibited without membership / redistribution license
- **Recommendation:** **DO NOT USE**

## Geographic compatibility (unchanged)

LTLF grain is **zone / LDA / RTO**, not state. AEP, APS, DOM, DPL, PEPCO, DEOK, RECO, and OVEC cross the five user-facing states or include territory outside them. Direct state join of zonal MW is misleading. Display mapping lives in `docs/pjm_screening_schema.md` and is **not** an ML join.

## Licensing

| Channel | Public GitHub portfolio |
| --- | --- |
| Library / LAS LTLF PDF and XLS (“For Public Use”, PJM ©) | Cite official URLs. Keep raw files gitignored. Commit only small derived tables if licensing still permits after ingest review. |
| Data Miner | Do not use and do not commit extracts. |

## MVP ingest recommendation

Ingest **2024, 2025, and 2026** public LTLF files only. That is the smallest set that (1) shows vintage change in data-center-driven peaks, (2) includes a documented revision (2024), and (3) still fits a dashboard MVP. Older years improve point-in-time proofs but do not cover the EIA 2002–2024 origin window and are not required to screen candidates now.

# EIA vintage research memo (Phase 2 criterion 5)

- **Date:** 2026-11-23 (US Eastern). Retrievals are recorded in UTC and fall on 2026-11-24.
- **Decision this supports:** `DECISIONS.md`, 2026-11-23, "EIA vintage policy and forward archive" (PR #24).
- **Design:** `docs/proposals/phase2_criterion5_options.md`, Option D.
- **Scope:** first-print values for VA, PA, OH, MD, and NJ, commercial sector, reference months 2012-05 to 2024-06. No reference month from 2024-07 on was parsed. The final holdout was not run or opened.

## 1. Findings

1. **First-print values can be rebuilt from 2012-05.** All 730 values (146 months x 5 states) were parsed from the issue two months after each reference month, with 0 gaps.
2. **A full as-of panel cannot be rebuilt.** Each issue shows only the reference month and the same month a year earlier.
3. **Revisions are material.** 90% of first prints differ from the frozen extract. The mean absolute change is 0.093 cents/kWh (0.90%).
4. **The m+3 rule holds for month-end origins only.** The earliest public file was never after the end of month m+3 in 171 issues. Day 1 of m+3 is not a publication date, and mid-month origins fail in at least 1 and at most 3 issues.
5. **The year-ago column often differs from first print.** It matches in 259 of 670 comparisons (38.7%). The cause of all 411 differences is not established (section 7.2).

## 2. Sources

EIA pages were read on 2026-11-24 between 03:14 and 03:21 UTC unless noted.

| Source | What it establishes |
| --- | --- |
| [EPM back issues](https://www.eia.gov/electricity/monthly/backissues.php) | Archive of monthly issues. All 171 issue ZIPs in scope exist |
| [Electric Power Monthly](https://www.eia.gov/electricity/monthly/) | Current issue: data for August 2026, released October 23, 2026, next release November 24, 2026 |
| [EPM Technical Notes, Appendix C](https://www.eia.gov/electricity/monthly/pdf/technotes.pdf), PDF page 3 | Monthly data are first released as preliminary and revised after the prior year's data are finalized. Later revisions are considered at a 1 percent national threshold |
| [Form EIA-861M instructions](https://www.eia.gov/survey/form/eia_861m/instructions.pdf) | Monthly data are due by the last day of the month after the reporting period |
| [EIA release schedule](https://www.eia.gov/reports/upcoming.cfm) | EPM is scheduled for the last week of the month |
| [EIA API documentation](https://www.eia.gov/opendata/documentation.php) | The page describes no vintage or as-of parameter, and lists the APIv1 update query as not supported |

Each ZIP's URL, server file date, retrieval time, SHA-256, and inner table name and timestamps are in `data/epm_backissue_sources.json`. The 171 ZIPs (413 MB) were retrieved from 2026-11-24T03:14:08Z to 2026-11-24T03:18:59Z and are stored local-only under `data/raw/eia/epm_backissues/`.

## 3. How far vintages can be rebuilt

| Evidence | Coverage | Status |
| --- | --- | --- |
| First print, Table 5.6.A in `.xlsx` issues | Reference months 2012-05 to 2024-06 | **Rebuilt:** 730 of 730 values |
| One later value per month, the year-ago column | Reference months 2012-05 to 2023-06 | Read for checking only. Not a vintage series |
| Reference months from 2024-07 | Not parsed | Waits for the Phase 3 preregistration |
| `.xls` ZIP issues before 2012-05 | Not parsed | Out of scope. The lockfile has no `.xls` reader |
| EPM PDFs from 1996 | Not examined | Unverified |

All 146 parsed issues state their reference month in the table header, and the parser refuses a mismatch. For the 25 later issues, used for timing only, the worksheet was not opened, so their reference month comes from the issue-month naming pattern.

## 4. What cannot be rebuilt

- A complete as-of panel at any past date.
- Values between first print and later revision, other than the single year-ago value.
- Exact historical release dates. EIA's archive gives file dates, not a release log.
- The full API panel of the 2026-09-24 release, which was not saved. **This gap stays open** and is recorded in `data/eia_vintage_ledger.json`.
- The 2026-10-23 panel as served on its release date. Snapshot `20261124T023746Z` preserved it about one month later and counts only from its `retrieved_at`.

No value was synthesized, back-filled, or corrected.

## 5. Revision statistics

First print compared with the frozen extract retrieved 2026-09-11, reference months 2012-05 to 2024-06. Later rows are filtered out when the extract is read.

| State | Values | Mean abs change (cents/kWh) | 95th percentile | Max | Mean abs % |
| --- | --- | --- | --- | --- | --- |
| VA | 146 | 0.089 | 0.315 | 0.53 | 1.03% |
| PA | 146 | 0.046 | 0.140 | 0.59 | 0.46% |
| OH | 146 | 0.084 | 0.197 | 0.24 | 0.84% |
| MD | 146 | 0.141 | 0.562 | 5.56 | 1.35% |
| NJ | 146 | 0.105 | 0.420 | 0.97 | 0.80% |
| **All** | 730 | 0.093 | 0.285 | 5.56 | 0.90% |
| All, without the two MD outliers | 728 | 0.080 | 0.276 | 0.97 | 0.76% |

10.0% of values are unchanged, 75.9% are within 0.10 cents/kWh, and the mean signed change is -0.018 cents/kWh. Ohio's 95th percentile (0.197) and mean percentage (0.84%) differ from the proposal's rounded 0.198 and 0.85% in the last digit. All other figures reproduce it.

## 6. Publication timing

`data/epm_publication_timing.csv` holds all 171 issues at release level, dates only. Timing is measured per release because one EPM issue carries all states.

**Every date is a proxy.** A table's internal timestamp shows when it was built, so publication cannot be earlier. A server file date is an upper bound on first publication, because files can be re-uploaded. True publication lies between the two.

| Measure | Result |
| --- | --- |
| Days from month-end to ZIP file date | Min 48, median 55, 75th percentile 57, max 97 |
| ZIP date on or after day 1 of m+3 | 19 of 171 |
| Table built on or after day 1 of m+3 | 9, up to 17 days later |
| Earliest public file after day 1 of m+3 | 13, up to 22 days later |

| Forecast origin | Issues where month m may not have been public | Result |
| --- | --- | --- |
| **Month-end of m+3** | **0 of 171** | **m+3 confirmed** |
| Mid-month (day 15 of m+3) | At least 1 (2015-11), at most 3 (2015-11, 2016-08, 2019-02) | **Not valid** |
| Day 1 of m+3 | At least 6, at most 13 | **Not a publication date** |

Issues with the table built on or after day 1 (days after day 1): 2014-06 (8), 2014-07 (6), 2014-08 (2), 2015-02 (3), 2015-11 (17), 2016-03 (0), 2017-11 (0), 2022-06 (0), 2026-05 (1).

Issues with the earliest public file after day 1 (days after day 1): 2014-06 (9), 2014-07 (7), 2014-08 (2), 2015-02 (3), 2015-11 (17), 2016-08 (22), 2019-02 (17), 2019-03 (10), 2019-09 (2), 2020-03 (1), 2021-10 (14), 2022-06 (5), 2026-05 (1).

## 7. Checks

### 7.1 Hand check of parsed values

16 values were opened directly in the source workbook's raw XML, using a separate reader that shares no code with the parser. They cover all 5 states, 2012 to 2024, and all three archive layouts (top level, `XLS/`, and `february2019/`). **All 16 match.**

| State | Reference | Issue | Table | Cell | Column | Source value | Parsed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| VA | 2012-05 | 2012-07 | `Table_5_06_A.xlsx` | D38 | Commercial / May 2012 | 8.3800000000000008 | 8.38 |
| VA | 2018-03 | 2018-05 | `Table_5_06_A.xlsx` | D38 | Commercial / March 2018 | 8.33 | 8.33 |
| VA | 2024-06 | 2024-08 | `Table_5_06_A.xlsx` | D38 | Commercial / June 2024 | 9.5399999999999991 | 9.54 |
| PA | 2012-11 | 2013-01 | `Table_5_06_A.xlsx` | D15 | Commercial / November 2012 | 9.48 | 9.48 |
| PA | 2016-04 | 2016-06 | `XLS/Table_5_06_A.xlsx` | D15 | Commercial / April 2016 | 9.52 | 9.52 |
| PA | 2023-02 | 2023-04 | `Table_5_06_A.xlsx` | D15 | Commercial / February 2023 | 11.79 | 11.79 |
| OH | 2013-08 | 2013-10 | `Table_5_06_A.xlsx` | D20 | Commercial / August 2013 | 9.4600000000000009 | 9.46 |
| OH | 2016-12 | 2017-02 | `Table_5_06_A.xlsx` | D20 | Commercial / December 2016 | 9.89 | 9.89 |
| OH | 2018-12 | 2019-02 | `february2019/Table_5_06_A.xlsx` | D20 | Commercial / December 2018 | 9.67 | 9.67 |
| OH | 2024-01 | 2024-03 | `Table_5_06_A.xlsx` | D20 | Commercial / January 2024 | 10.51 | 10.51 |
| MD | 2014-09 | 2014-11 | `Table_5_06_A.xlsx` | D35 | Commercial / September 2014 | 10.76 | 10.76 |
| MD | 2019-07 | 2019-09 | `Table_5_06_A.xlsx` | D35 | Commercial / July 2019 | 9.4700000000000006 | 9.47 |
| MD | 2022-08 | 2022-10 | `Table_5_06_A.xlsx` | D35 | Commercial / August 2022 | 8.83 | 8.83 |
| NJ | 2012-08 | 2012-10 | `Table_5_06_A.xlsx` | D13 | Commercial / August 2012 | 13.47 | 13.47 |
| NJ | 2017-06 | 2017-08 | `Table_5_06_A.xlsx` | D13 | Commercial / June 2017 | 13.34 | 13.34 |
| NJ | 2024-05 | 2024-07 | `Table_5_06_A.xlsx` | D13 | Commercial / May 2024 | 14.83 | 14.83 |

Source values such as 8.3800000000000008 are how Excel stores two-decimal numbers. The parser keeps the raw text and rounds to two decimals only when the difference is below 0.000001.

### 7.2 Year-ago column

Each issue's year-ago value was compared with the first print from 12 issues earlier, where both exist.

- **Match rate: 259 of 670 (38.7%). Mismatches: 411.**
- Among mismatches, the median absolute difference is 0.03 cents/kWh, the maximum is 5.56, 74 exceed 0.10, and 10 exceed 0.50.
- Every difference is listed in `data/epm_year_ago_differences.csv`, which holds differences and no price levels.
- 216 of the 411 differing year-ago values already equal the frozen extract. The other 195 equal neither first print nor the frozen extract.

| State | Compared | Match | Differ |
| --- | --- | --- | --- |
| VA | 134 | 72 | 62 |
| PA | 134 | 48 | 86 |
| OH | 134 | 44 | 90 |
| MD | 134 | 51 | 83 |
| NJ | 134 | 44 | 90 |

| Year of the compared month | Compared | Match | Differ |
| --- | --- | --- | --- |
| 2012 | 40 | 17 | 23 |
| 2013 | 60 | 51 | 9 |
| 2014 | 60 | 21 | 39 |
| 2015 | 60 | 20 | 40 |
| 2016 | 60 | 30 | 30 |
| 2017 | 60 | 16 | 44 |
| 2018 | 60 | 20 | 40 |
| 2019 | 60 | 21 | 39 |
| 2020 | 60 | 22 | 38 |
| 2021 | 60 | 18 | 42 |
| 2022 | 60 | 14 | 46 |
| 2023 | 30 | 9 | 21 |

**Interpretation.** The ten largest differences were opened on both sides, and all ten agree with the parser, so they are differences in EIA's published tables rather than parsing errors at those cells. Revision is the likely explanation, but it is **not proven for all 411**. A single annual revision step would make whole issues match or differ, yet 98 of 134 issues are mixed across the five states (11 match on all five, 25 on none). This check therefore does not independently validate first-print values. The hand check does that for the values it covers.

| State | Month | First print (issue, cell) | Value | Year-ago (issue, cell) | Value | Difference |
| --- | --- | --- | --- | --- | --- | --- |
| MD | 2014-09 | 2014-11 D35 | 10.76 | 2015-11 E35 | 16.32 | +5.56 |
| MD | 2022-08 | 2022-10 D35 | 8.83 | 2023-10 E35 | 13.10 | +4.27 |
| NJ | 2015-11 | 2016-01 D13 | 13.01 | 2017-01 E13 | 12.04 | -0.97 |
| NJ | 2015-10 | 2015-12 D13 | 13.07 | 2016-12 E13 | 12.11 | -0.96 |
| NJ | 2021-05 | 2021-07 D13 | 12.37 | 2022-07 E13 | 13.08 | +0.71 |
| MD | 2014-10 | 2014-12 D35 | 10.85 | 2015-12 E35 | 10.25 | -0.60 |
| MD | 2014-11 | 2015-01 D35 | 10.87 | 2016-01 E35 | 10.30 | -0.57 |
| PA | 2021-05 | 2021-07 D15 | 8.10 | 2022-07 E15 | 8.67 | +0.57 |
| VA | 2023-05 | 2023-07 D38 | 9.05 | 2024-07 E38 | 9.61 | +0.56 |
| MD | 2014-12 | 2015-02 D35 | 10.89 | 2016-02 E35 | 10.37 | -0.52 |

### 7.3 Maryland outliers, reported unchanged

| Month | First print (issue, cell) | Value | Year-ago column 12 issues later | Frozen extract | First prints, 2 months either side | Frozen extract, 2 months either side |
| --- | --- | --- | --- | --- | --- | --- |
| MD 2014-09 | 2014-11 D35 | 10.76 | 2015-11 E35: 16.32 | 16.32 | 11.05, 10.93, 10.85, 10.87 | 10.48, 10.35, 10.25, 10.30 |
| MD 2022-08 | 2022-10 D35 | 8.83 | 2023-10 E35: 13.10 | 13.10 | 12.75, 12.82, 13.26, 13.60 | 12.81, 12.84, 13.12, 13.59 |

- **2014-09:** the first print fits its neighbours. The later value of 16.32 looks anomalous, and it was already in the year-ago column by the 2015-11 issue.
- **2022-08:** the first print of 8.83 looks anomalous. The later value of 13.10 fits its neighbours.

Neither first print nor the current value is always the better number. Both values stay as published.

## 8. Use in Phase 3

- Tier 2 values are **reconstructed first prints**. Do not call them an as-of panel.
- They cover periods Version 1 saw in revised form, so they are **not untouched data**. Untouched data starts with Tier 1 snapshots from 2026-11-24.
- Use m+3 only with month-end origins.
- The Phase 3 preregistration must name the tier for training, features, and evaluation targets, and say how the two MD outliers are handled before any result is seen.
- `DECISIONS.md` lists a failed hand or consistency check as a revisit trigger. The hand check passed. The year-ago check had no preset pass threshold, so whether its 38.7% match rate triggers a revisit is the owner's call.

## 9. Reproduce

These commands are owner-run and never run in CI. `fetch` needs network access and refuses to overwrite a ZIP.

```bash
python scripts/eia_first_print.py fetch
python scripts/eia_first_print.py build
python scripts/eia_first_print.py timing
python scripts/eia_first_print.py checks
```

Parsed values and check details stay local-only under `data/processed/eia_first_print/`.

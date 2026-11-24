# Phase 2 criterion 4: data-distribution policy options

- **Status:** the owner approved Option C on 2026-11-23. This is the proposal as reviewed. At implementation the owner directed that R6 and R7 historical text stay unchanged, which replaces that part of draft criterion 10. See `DECISIONS.md`, 2026-11-23.
- **Prepared:** 2026-11-23, on `main` at `fa81386` (PR #21).
- **Legal status:** this is an engineering reading of published terms, not legal advice.

## Recommendation

Choose **Option C**: keep every cache out of git and enforce that policy in CI.

- It meets criterion 4 without relying on any right PJM has not granted.
- It changes no test assertion and adds no data file.
- CI stays at **14 skipped**, but every skip becomes a named, machine-checked exception.
- It does not add CI coverage of the real data. That limit stays open and is recorded in R7 and TD-04.

Option B (committing the EIA extract) is legally the strongest way to reduce skips later, and can be a separate decision.

## 1. Criterion and governing text

Phase 2 criterion 4, verbatim from `TASKS.md:10`:

> 4. **Machine-enforced data-distribution policy (TD-04).** From EIA's and PJM's published terms, each dataset is classified as committed, reproducibly fetched, local-only (not distributed), or unavailable, recorded in a dated decision with sources. A CI check enforces it (for example, no local-only file is tracked). Report the resulting CI skip count, with a reason for each remaining skip.

Constraints from existing records:

- `DECISIONS.md`, 2026-11-20 (Phase 2 scope, PR #15): no change to Version 1 data, model, holdout, or results. Each item needs its own branch, evidence, and review.
- `DECISIONS.md`, 2026-10-19 and 2026-10-20: the four local artifacts were not published, and their redistribution rights were left undecided until "a rights review allows a specific derived dataset".
- `RISK_REGISTER.md` R6: leave a missing cache unavailable. Do not fabricate replacement series, download automatically, or regenerate the holdout.
- `RISK_REGISTER.md` R7: a green clean-clone run does not mean cache-dependent behavior was validated.
- TD-04: 14 tests depend on four gitignored caches, and any change needs a data-rights and provenance decision.

## 2. Preflight results

| Check | Expected | Found | Status |
| --- | --- | --- | --- |
| PR #21 merged | Merge commit | Merged 2026-11-24T01:32:52Z as `fa81386`, with **one parent** (`bcd146b`) | **Mismatch: squash merge.** Its tree equals PR head `0001160` |
| Push CI on `main` | Green | [Run 45305835777](https://github.com/tiniusms/InfraLens/actions/runs/45305835777) succeeded | OK |
| Python | 207 passed, 14 skipped, 0 failed | Same | OK |
| Frontend | 41 passed | **53 passed** | **Mismatch in the expectation.** PR #20 added tests |
| Criterion 3 tick | Cites PR #21 | Cites PR #21, but still says "pending owner review" | **Needs a housekeeping edit after this review** |
| Working tree | Clean | One uncommitted `TASKS.md` edit, kept by owner decision | It changes the status line back to "criteria 1 and 2" and was carried to `main` unchanged |

## 3. The 14 skipped tests

Every test below currently skips in CI. "Smallest slice" is what its assertions and loaders need. It is measured from the local files, read-only.

| # | Test | Skip reason | Cache | Smallest slice that can pass |
| --- | --- | --- | --- | --- |
| 1 | `test_api_contract.py::test_observed_history_uses_the_loader_roles` | Frozen EIA price history is not on this machine. | EIA interim Parquet | All 1,530 rows (asserts `extract_row_count == 1530`). File: 51,067 bytes |
| 2 | `test_demo_eia_views.py::test_local_price_history_matches_the_frozen_extract` | local EIA parquet is not on this machine | EIA interim Parquet | 310 rows: one state from 2001-01 to 2026-06, plus the last month for 4 states. 4 columns are read by the validator |
| 3 | `test_api_contract.py::test_holdout_series_keeps_origins_in_provenance` | Frozen holdout cases are not on this machine. | Holdout cases | All 60 rows. File: 15,335 bytes |
| 4 | `test_api_contract.py::test_holdout_ridge_price_comes_from_the_case_file` | Frozen holdout cases are not on this machine. | Holdout cases | 1 scored row by its assertions |
| 5 | `test_demo_eia_views.py::test_local_holdout_file_matches_the_closed_window` | local holdout cases are not on this machine | Holdout cases | All 60 rows |
| 6 | `test_api_contract.py::test_pjm_published_and_unpublished_boundaries_match_the_workbooks` | Official PJM Tables workbooks are not in data/raw/pjm. | Both PJM workbooks | **Exact files**, because the loader requires the manifest SHA-256 (781,418 bytes) |
| 7 | `test_demo_pjm_screen.py::test_aep_cutoffs_match_the_cached_workbooks` | Same | Both PJM workbooks | **Exact files**, same reason |
| 8 | `test_demo_pjm_screen.py::test_date_before_the_2025_release_is_unpublished` | Same | Both PJM workbooks | **Exact files**, same reason |
| 9 | `test_pjm_screening.py::test_official_workbooks_match_published_b1_cells` | Same | Both PJM workbooks | Table B1 in both: 924 parsed rows; sheet XML 22,419 bytes compressed, plus shared strings |
| 10 | `test_pjm_screening.py::test_official_ingest_rejects_corrupt_workbooks` | Same | 2026 workbook | Table B1 only: 73 rows, 11,304 bytes compressed |
| 11 | `test_pjm_screening.py::test_official_rows_reject_duplicate_keys_and_invented_dates` | Same | Both PJM workbooks | Table B1 in both |
| 12 | `test_pjm_adjustments.py::test_official_adjustment_workbooks` | Same | Both PJM workbooks | Tables B9 and B9b in both: 1,848 parsed rows; sheet XML 15,402 bytes compressed, plus shared strings |
| 13 | `test_pjm_adjustments.py::test_official_b9_workbook_rejects_corrupt_cells` | Same | 2026 workbook | Table B9 only: 3,697 bytes compressed |
| 14 | `test_pjm_view.py::test_official_aep_2026_view_matches_workbook_columns` | Same | Both PJM workbooks | Tables B1, B9, and B9b in both |

Totals: EIA history 2, holdout cases 3, PJM workbooks 9.

Three findings shape the options:

- **Real values are the point of these tests.** They assert official figures such as AEP 24,635 MW. Synthetic data with the same assertions would fail, and changing the assertions would weaken the tests.
- **PJM excerpts cannot satisfy tests 6-8.** Since criterion 2, the loader refuses a file whose SHA-256 differs from the manifest.
- **Parser logic already has synthetic coverage.** The PJM test files and `tests/test_pjm_retrieval_manifest.py` already run the parsers on synthetic workbooks on Linux. What CI lacks is a check against the real files.

## 4. Data rights (primary sources, retrieved 2026-11-23)

### EIA

| Source | What the terms say |
| --- | --- |
| [Copyrights and Reuse](https://www.eia.gov/about/copyrights_reuse.php), "Public domain and use of EIA content" | "U.S. government publications are in the public domain and are not subject to copyright protection." EIA permits use and distribution of its data, files, databases, and reports. Users "should use an acknowledgment, which includes the publication date." |
| Same page, "Protected materials" | Third-party material, photographs, and the EIA logo are restricted. State-level electricity data is not listed as an exception. |
| [Open Data](https://www.eia.gov/opendata/) | "EIA data is provided free of charge and should be used in compliance with our Copyrights and Reuse Policy." |
| [API Terms of Service](https://www.eia.gov/opendata/terms-of-service.php) | Name EIA as the source, and do not imply endorsement. "You may not modify or falsely represent content accessed through the API and still claim the source is the EIA." The terms do not address storing, caching, or redistributing retrieved data. |

**Interpretation:** redistribution of the raw EIA values appears permitted with attribution and a date. The normalized Parquet has changed the form of the data, so it should be labelled as InfraLens-normalized from EIA data, not as an EIA file. The API terms' silence on redistribution is covered by the broader reuse policy, but that is a reading, not an express API clause.

### PJM

| Source | What the terms say |
| --- | --- |
| [PJM Legal](https://www.pjm.com/m/About-PJM/Legal) | Site access "does not confer any license or ownership interest" in the site's form or content, and PJM reserves those rights. |
| [Load forecast page](https://www.pjm.com/planning/resource-adequacy-planning/load-forecast-dev-process) | Lists the report and Tables files. It has a site copyright footer and no reuse condition or permission for them. |
| [2026 Load Forecast Report](https://www.pjm.com/-/media/DotCom/library/reports-notices/load-forecast/2026-load-report.pdf) | Each page is marked as PJM copyright 2026 and "For Public Use". It states no reuse licence. |
| The two workbooks in `data/manifest.json` | A scan of their shared strings found no copyright, reuse, or redistribution text. |
| [Data Miner 2 terms](https://www.pjm.com/-/media/DotCom/etools/edatafeed/data-license-agreement-edata-feed-data-miner-2.ashx) | These govern Data Miner 2 and its content. Their section 1 prohibits republication by non-members. |

**Interpretation:**

- The Data Miner terms do not, on their face, cover these workbooks, because the workbooks came from the public load-forecast page. They do show how PJM treats republication of its data.
- "For Public Use" reads as an information-handling label. It is **not** a licence to redistribute.
- **Redistribution of the workbooks, or excerpts of them, is unclear and should not be assumed.** Treat it as not permitted without written permission from PJM.
- Citing a PJM value with its source is a different question from committing PJM's files. This proposal does not change how the app displays or cites values.

Site note: PJM's footer "Legal and Privacy" link (`/about-pjm/legal.aspx`) returned "Page Not Found" on 2026-11-23. The live text was at `/m/About-PJM/Legal`. Neither page showed an effective date.

## 5. Proposed classification

| Dataset (manifest entry) | Class | Reason |
| --- | --- | --- |
| EIA raw JSON `…20260911T190524Z` | Local-only | Rights appear to allow distribution, but nothing needs it in git. A re-fetch returns EIA's current vintage, so it is **not** reproducibly fetched |
| EIA interim Parquet | Local-only | Same. It is also a normalized derivative |
| PJM 2025 workbook | Local-only (not distributed) | No redistribution grant. Each user obtains it from PJM and verifies the manifest SHA-256 |
| PJM 2026 workbook | Local-only (not distributed) | Same. PJM can replace the file at the same URL, so it is not guaranteed reproducible |
| Holdout cases Parquet | Local-only | Frozen evaluation artifact; existing decisions did not publish it |
| Local holdout summary JSON | Local-only | Its summary is already committed |
| `docs/final_eia_holdout_oneshot.json` | Committed | Already tracked and hash-pinned |
| `tests/fixtures/eia_retail_sales_sample.json` | Committed | Synthetic |

No listed dataset is classified as "reproducibly fetched" or "unavailable". The unlisted files in TD-27 are covered by the path rule in Option C.

## 6. Options

| | A: Synthetic fixtures | B: EIA-only real excerpts | **C: Enforced policy (recommended)** |
| --- | --- | --- | --- |
| **What it does** | Generates fake EIA, holdout, and PJM files from schemas | Commits the EIA extract, and optionally the holdout cases, with manifest SHA-256 and citation. PJM stays local | Keeps caches out of git. Adds a policy file, tracking test, and named-skip check |
| **Skips removed** | **0 valid.** Removing skips would need changed values or assertions | **2** (EIA only) or **5** (EIA plus holdout). 9 PJM skips remain | **0.** All 14 become named exceptions |
| **Data-rights risk** | None | Low for EIA with attribution. Holdout needs its own decision | Lowest: nothing is distributed |
| **Provenance** | Weak for this purpose: proves shape, not official values, and R6 warns against replacement series | Strong: exact bytes match the manifest | Strong: manifest hashes remain the check wherever files exist |
| **CI changes** | New fixtures and tests | Tracked data, a `.gitignore` exception, and full-data mode changes for some views | One policy test and one skip-check step |
| **Effort** | M to L | M | S to M |
| **Changes a test assertion?** | Yes, if it is used to remove skips | No, if files stay at their default paths | **No** |
| **Main drawback** | False confidence | Reverses earlier non-publication decisions, and committed files change what a clean clone shows | CI still cannot test real data |

## 7. Recommended design (Option C, not implemented)

1. Add `data/distribution_policy.json`, separate from `data/manifest.json`. The manifest stays unchanged because its schema test allows only an exact set of keys.
2. Add a test that fails when:
   - a manifest entry has no valid class;
   - a local-only path is tracked;
   - any file under `data/raw/`, `data/interim/`, or `data/processed/` other than `.gitkeep` is tracked;
   - any `*.parquet` or `*.xlsx` is tracked.
3. Add a CI step that reads a pytest JUnit XML report and compares its skips with a named allowlist of the 14 tests, each with its required cache and exact reason. Test names are used instead of line numbers, which move.

### Draft acceptance criteria

1. A dated `DECISIONS.md` entry classifies all 8 manifest entries as committed, reproducibly fetched, local-only, or unavailable, and cites the EIA and PJM sources with retrieval dates.
2. The policy test fails on a missing or invalid class, and on each tracked-file case above. Each failure mode is demonstrated by a negative test.
3. The test does not skip. If `git ls-files` cannot run, it fails.
4. CI fails on any skip outside the allowlist, any changed reason, or any listed test that no longer skips until the allowlist is updated.
5. CI reports exactly **14 skipped**: EIA history 2, holdout cases 3, PJM workbooks 9, each with a named reason.
6. Python CI has 0 failures, with passes equal to 207 plus the new tests. Local full-data runs have 0 failures and 0 skips.
7. No existing test assertion changes, and no test is deleted, skipped, or xfailed.
8. `data/manifest.json`, all data files, the holdout artifacts, historical files, and earlier `DECISIONS.md` entries are byte-identical. `tests/test_final_holdout.py` is not run.
9. No new dependency or paid service is added.
10. R6, R7, TD-04, and `TASKS.md` state that CI enforces the policy but does not validate real cached data.

## 8. Open decisions for the owner

1. Approve Option C, or choose another option.
2. Optional and separate: ask PJM in writing for permission to redistribute a small excerpt. Until PJM answers, the workbooks stay local-only.
3. Housekeeping after this review: update the criterion 3 tick from "pending owner review", and decide what to do with the uncommitted `TASKS.md` edit.

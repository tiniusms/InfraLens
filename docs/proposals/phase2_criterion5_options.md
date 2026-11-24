# Phase 2 criterion 5: EIA vintages and publication timing options

- **Status:** the owner approved Option D on 2026-11-23, with the additions below. This is the proposal as reviewed. PR A implements the forward archive and vintage policy. PR B implements the first-print rebuild, timing table, and research memo, and ticks criterion 5.
- **Prepared:** 2026-11-23, on `main` at `f5a4352` (PR #23).
- **Scope of checks:** no file was written to `data/`, the manifest is unchanged, no holdout artifact was opened, and `tests/test_final_holdout.py` was not run. No EIA API call was made and no API key was read.

## Updates after review (2026-11-23)

- **Snapshot taken.** Snapshot `20261124T023746Z` was saved before EIA's next update: 1,540 rows through 2026-08, following the 2026-10-23 release.
- **Correction on the October panel.** This proposal said the 2026-10-23 full panel was already missed. More precisely, it was **not captured at release**, but the snapshot above preserved the panel still being served about one month later, with the bulk ELEC timestamp unchanged since 2026-10-22. The ledger records this as a `not_captured_at_release` gap. The 2026-09-24 full panel was not saved and cannot be recovered.
- **Untouched data.** Reconstructed first-print history from 2012-05 to 2024-06 covers periods Version 1 saw in revised form and is not untouched data. Untouched data for Phase 3 starts with Tier 1 snapshots, from 2026-11-24.
- **Owner additions.** Draft criteria 12 and 13 below.

## Recommendation

Choose **Option D**, three clearly labelled evidence tiers:

1. **Observed real-time:** a forward archive of each EIA release, starting now.
2. **Reconstructed first-print:** first-published values rebuilt from archived Electric Power Monthly (EPM) tables, from reference month 2012-05.
3. **Current-vintage, lag-constrained:** today's method, explicitly labelled retrospective.

**Time-sensitive:** EIA's next EPM release is **2026-11-24**. The API has no vintages, so the full panel now being served will be lost when it updates. The September and October 2026 full panels were already missed. A one-time raw snapshot before the update needs owner approval (section 8).

## 1. Key findings

| Question | Finding |
| --- | --- |
| When does a month first appear? | In the EPM issue two calendar months later. All 171 parsed issues (reference months 2012-05 to 2026-07) follow this pattern. The median file date is 55 days after month-end |
| Is the m+3 rule safe? | **Yes for month-end forecast origins, no as a calendar date.** The earliest public file was never after the end of month m+3. But in 9 of 171 issues the price table itself was built on or after day 1 of m+3, by up to 17 days |
| Are values revised? | Yes. Across 730 state-months, **90% of values differ** from first print. Mean absolute change is 0.093 ¢/kWh (0.90%), the 95th percentile is 0.285 ¢/kWh, and the largest is 5.56 ¢/kWh |
| Can history be rebuilt? | **Partly.** First-print values can be rebuilt. A complete as-of panel for each past date cannot |
| Do the local pulls show revisions? | No. The four pulls span only 39 hours and have identical payloads, so they say nothing about revision size |
| Does DuckDB earn its place? | No. The recommended store is small and needs no query engine |

## 2. Preflight

| Check | Result |
| --- | --- |
| PR #23 (`f5a4352`) | **Squash merge: one parent** (`fb2e2b3`). Its tree equals PR head `f9d8835` |
| Local `main` | Synced at `f5a4352`; tree was clean before this file |
| Push CI on `main` | [Run 45311481531](https://github.com/tiniusms/InfraLens/actions/runs/45311481531) succeeded |
| `TASKS.md` | Phase 2 criteria 1–4 are ticked; criteria 5–7 are open |
| `stash@{0}` | Untouched |

## 3. Governing text and current implementation

Phase 2 criterion 5, verbatim from `TASKS.md`:

> 5. **EIA vintages and publication timing (TD-25).** A research memo, citing authoritative sources, determines how far historical EIA vintages can be reconstructed. Where reconstruction is impossible or incomplete, the limitation is documented, and no vintage is synthesized or back-filled. A forward archive stores each new release as an immutable, fingerprinted snapshot. Publication timing is measured at the level the source actually varies (release or dataset level unless state-level differences are evidenced), confirming or replacing the assumed m+3 lag. A dated decision sets the vintage policy Phase 3 will use.

Related records:

- **Phase 2 scope (`DECISIONS.md`, 2026-11-20, PR #15):** criterion 5 needs its own dated entry. Phase 3 was deferred because "the EIA vintage policy is undefined". Version 1 is unchanged.
- **TD-25:** the EIA history is current-vintage with an assumed m+3 lag. This criterion covers it.
- **TD-26:** the 2024 PJM PDF. **Criterion 5 does not cover it.** It is deferred backlog outside Phase 2 completion.
- **TD-01:** says "Phase 2 vintage archival decides whether DuckDB is used; drop whatever stays unused". Section 7 answers this for criterion 6.
- **R4:** the m+3 lag does not reconstruct historical vintages, and revisions can already sit in the frozen extract.
- **R5:** concerns PJM boundaries and is unaffected.

EIA data currently used (`src/infralens/data/__init__.py`, `eia_client.py`, and `data/manifest.json`):

| Item | Value |
| --- | --- |
| API route | `https://api.eia.gov/v2/electricity/retail-sales/data/` |
| Series | `price`, `sales`, `revenue` |
| States | VA, PA, OH, MD, NJ |
| Sector | `COM` (commercial) |
| Frequency | Monthly, from 2001-01 |
| Frozen extract | Retrieved 2026-09-11T19:05:24.708930Z; 1,530 rows, 2001-01 to 2026-06 |
| Lag rule | `assumed_available_at` is day 1 of month m+3 (`src/infralens/data/availability.py`) |

## 4. EIA primary-source findings (retrieved 2026-11-23)

### Publication timing

- The [EPM page](https://www.eia.gov/electricity/monthly/) shows "Data for August 2026", release date October 23, 2026, and next release November 24, 2026.
- EIA's [release schedule](https://www.eia.gov/reports/upcoming.cfm) lists EPM for "The last week of the month" and says dates "are approximate and may shift".
- [Form EIA-861M instructions](https://www.eia.gov/survey/form/eia_861m/instructions.pdf): monthly data are due by the last day of the month following the reporting period.
- [EIA bulk files](https://www.eia.gov/opendata/bulkfiles.php) update twice daily. The [bulk manifest](https://www.eia.gov/opendata/bulk/manifest.txt) showed ELEC `last_updated` of 2026-10-22T18:26:13-04:00, the evening before the October release, and it was unchanged at 21:32 ET on 2026-11-23.
- Timing varies by **release**, not by state: one EPM issue carries all states. No state-level release difference is documented.

### Revision behaviour

From [EPM Appendix C, Technical Notes](https://www.eia.gov/electricity/monthly/pdf/technotes.pdf):

- "All monthly survey data are first disseminated as preliminary."
- They "are revised after the prior year's data are finalized and are disseminated as revised preliminary."
- Monthly state and sector values are adjusted using the ratio of final annual Form EIA-861 totals to monthly totals.
- After data are final, further revisions are considered if they make "a difference of 1 percent or greater at the national level".

Other sources:

- [Form EIA-861M](https://www.eia.gov/electricity/data/eia861m/) is a statistically chosen sample. [Form EIA-861](https://www.eia.gov/electricity/data/eia861/) is an annual census.
- The 861M page showed final annual 2024 data released on October 27, 2025. The 861 page showed a final-data release date of October 7, 2026.
- [EPM Table 5.6.A](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_5_6_a) marks 2025 values as final and 2026 as preliminary, by year rather than by cell.
- [EPM Table C.2](https://www.eia.gov/electricity/monthly/xls/table_c_2.xlsx) gives the US commercial average price mean absolute preliminary-to-final change: **1.19% (2023), 1.03% (2024), 0.44% (2025)**. The EPM landing page still labels this table "2017 Through 2019", while the file says 2023 through 2025.

### Historical vintages

| Source | What exists | Use |
| --- | --- | --- |
| [API v2](https://www.eia.gov/opendata/documentation.php) | Current values only. No vintage, as-of, or release-date field. APIv1's update query is listed as "Not supported" | **Cannot rebuild history** |
| [EPM back issues](https://www.eia.gov/electricity/monthly/backissues.php), ZIP with `.xlsx` | Parsed for 171 issues, reference months 2012-05 to 2026-07 | First-print rebuild, **verified** |
| EPM ZIP with `.xls` | ZIP issues from 2003, with `.xls` tables in sampled 2004, 2010, and 2011 issues | Likely usable, **not verified**. Parsing needs a tool the lockfile does not have |
| EPM PDFs | Linked from June 1996 | Whether they hold the needed state table was not verified |

**What cannot be rebuilt:**

- A complete as-of panel at a past date. Table 5.6.A shows only the reference month and the same month a year earlier.
- Values between first print and later revision, except that year-ago column.
- The exact historical release date. EIA's archive provides file timestamps, not a release log.
- The full API panels from the 2026-09-24 and 2026-10-23 releases, which were not saved.

No value should be synthesized or back-filled for any of these.

## 5. Read-only measurements (retrospective)

### Local pulls

The four local raw pulls, retrieved from 2026-09-10T03:59Z to 2026-09-11T19:05Z, have 1,530 rows each, 0 changed values, and one identical payload hash. They fall between EPM releases, so they cannot show revisions.

### Publication timing, 171 EPM issues

Timestamps are proxies. A server file date is an upper bound on first publication, because files can be re-uploaded. A table's timestamp inside the ZIP shows it was built by then, so publication cannot be earlier. This timing check uses dates only.

| Measure | Result |
| --- | --- |
| Issue month minus reference month | 2 months in all 171 |
| Days from month-end to ZIP file date | Min 48, median 55, 75th percentile 57, max 97 |
| ZIP date on or after day 1 of m+3 | 19 of 171 |
| Of those, price table built on or after day 1 of m+3 | **9**, up to 17 days later |
| Earliest public file after day 1 of m+3 | 13, up to 22 days later |
| Earliest public file after the **end** of m+3 | **0** |

**Conclusion:** keep m+3 for month-end origins, because a month treated as available at the end of m+3 was public by then in all 171 issues. Do not describe day 1 of m+3 as a publication date, and do not use it for mid-month origins.

### First print versus the frozen extract

Compared EPM Table 5.6.A first-print commercial prices with the frozen extract for reference months **2012-05 to 2024-06**: 146 months × 5 states = 730 values. **The window stops before the first holdout origin (2024-07-31)**, so no holdout-period price was compared.

| State | Mean abs change (¢/kWh) | 95th percentile | Max | Mean abs % |
| --- | --- | --- | --- | --- |
| MD | 0.141 | 0.562 | 5.56 | 1.35% |
| NJ | 0.105 | 0.420 | 0.97 | 0.80% |
| VA | 0.089 | 0.315 | 0.53 | 1.03% |
| OH | 0.084 | 0.198 | 0.24 | 0.85% |
| PA | 0.046 | 0.140 | 0.59 | 0.46% |
| **All** | **0.093** | **0.285** | **5.56** | **0.90%** |

- 10.0% of values are unchanged, and 75.9% are within 0.10 ¢/kWh.
- The mean signed change is −0.018 ¢/kWh.
- Without the two outliers below, the mean absolute change is 0.080 ¢/kWh and the maximum is 0.97.

**Two data-quality outliers, both in Maryland:**

- **2014-09:** first print 10.76, current **16.32**, while neighbouring months are about 10.3 to 10.5. The current frozen value looks anomalous.
- **2022-08:** first print **8.83**, current 13.10, while neighbouring months are about 12.8 to 13.1. The first print looks anomalous.

So neither first print nor the current value is always the better number. These values are reported only. Nothing should be corrected.

## 6. Options

| | A: Forward archive | B: First-print rebuild | C: Lag rule on current values | **D: A + B + C, labelled (recommended)** |
| --- | --- | --- | --- | --- |
| **What it does** | Saves each release from now on | Parses archived EPM tables | Keeps the current extract and documents m+3 | Three separate evidence tiers |
| **Phase 3 can claim** | Real-time results for origins after archiving starts | Results using first-published values, from 2012-05 | Publication-lag-constrained, current-vintage results | Each claim tied to its tier |
| **Phase 3 cannot claim** | Anything before the first snapshot | A full as-of panel, or real-time revised history | Real-time or first-release performance | Real-time performance before the first snapshot |
| **Leakage risk** | Lowest | Low for the target month. Older feature months at an origin may be first prints rather than what was then current | **Highest:** revised values remain inside the history | Controlled and visible |
| **Storage** | Raw JSON, about 700 KB per release (about 8.4 MB a year) | Extracted `.xlsx` tables with SHA-256 | None new | Both; Parquet at most for derived tables |
| **Distribution class** | Local-only | Local-only | Unchanged | Local-only; metadata ledger committed |
| **Effort** | S to M | M | S | M to L |
| **Test impact** | New tests only | New synthetic parser tests | None | New tests only, 14 skips unchanged |
| **Meets criterion 5 alone?** | No: lacks the reconstruction memo and timing | No: no forward archive | No | **Yes** |

## 7. Recommended design (Option D, not implemented)

### Vintage policy for Phase 3

- **Tier 1, observed real-time:** values from an archived snapshot, available from its recorded `retrieved_at`.
- **Tier 2, reconstructed first-print:** the value in the first EPM issue for that month. Label it reconstructed, and do not call it an as-of panel.
- **Tier 3, current-vintage:** keep m+3 with month-end origins, labelled retrospective.
- Phase 3's preregistration must name the tier used for training, features, and evaluation targets.

### Storage and tooling

- **Snapshots:** raw API JSON under `data/raw/eia/vintages/`, already covered by the `data/raw/eia/*` ignore rule.
- **Do not reuse the current ingest command for snapshots.** It also writes to `data/interim/`, and `latest_eia_parquet` (`src/infralens/evaluation/backtest.py:52`) selects the newest file there, so a new snapshot would silently change backtest input.
- **Metadata:** a separate committed ledger, for example `data/eia_vintage_ledger.json`, with path, retrieval time, SHA-256, size, payload hash, latest period, and the EPM release it follows. Using `data/manifest.json` would break hard-coded counts in `tests/test_data_distribution_policy.py:39` and `:50`, and would force an assertion change.
- **Distribution:** snapshots are local-only under criterion 4. EIA terms appear to allow distribution, but nothing needs these files in git.
- **DuckDB:** not needed. Each snapshot has 1,530 rows, about 18,000 a year, which pandas and PyArrow handle directly. Criterion 6 can remove it, subject to approval of the lockfile change.
- **No secrets in CI:** the repository has none, so API snapshots remain an owner-run command.

### Draft acceptance criteria

1. A research memo cites EIA sources with retrieval dates and states how far vintages can be rebuilt and what cannot be.
2. No value is synthesized, back-filled, or corrected. Gaps stay recorded as gaps.
3. A snapshot command writes one immutable raw file, refuses to overwrite, never records the API key, and writes nothing to `data/interim/`. A test proves `latest_eia_parquet` is unaffected.
4. The ledger records each snapshot. A test checks its schema and verifies the SHA-256 of any snapshot present.
5. Every EPM release after adoption has a snapshot or a recorded gap with a reason.
6. A first-print table covers reference months 2012-05 to 2024-06 for 5 states (730 values), with source issue and table SHA-256. Months from 2024-07 are not added until the Phase 3 preregistration defines their use.
7. A timing table covers all parsed EPM issues at release level, labels file dates as proxies, and reports the m+3 result.
8. A dated `DECISIONS.md` entry sets the three-tier policy.
9. CI has 0 failures and the same 14 allowlisted skips. No existing assertion changes.
10. `data/manifest.json`, the frozen extract, holdout artifacts, historical files, and earlier `DECISIONS.md` entries are byte-identical. `tests/test_final_holdout.py` is not run.
11. No new dependency is added without approval. Parsing `.xls` issues before 2012-05 is out of scope.
12. A recorded hand check compares at least 10 parsed first-print values with their source tables, spread across all 5 states, multiple reference years, and the file formats and archive layouts in scope. Each record names the issue, table, cell, parsed value, and source value.
13. A year-ago-column consistency check compares each first-print table's year-ago column with the corresponding earlier and current values, and reports every difference. It reports differences and corrects nothing.

## 8. Decisions for the owner

1. **Urgent, before the 2026-11-24 release:** approve one raw API snapshot of the current panel, saved only to `data/raw/eia/vintages/`, using the local `EIA_API_KEY`. It would write nothing to `data/interim/`, the manifest, or git. If it is not taken before the update, this panel cannot be recovered.
2. Approve Option D, or choose another option.
3. Confirm that the first-print rebuild stops at 2024-06 until Phase 3 is preregistered.

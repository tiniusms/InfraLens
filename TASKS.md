# InfraLens Current Tasks

## Version 2 Phase 1 — Engineering foundation (authorized 2026-11-05)
Governance: `docs/version_2_charter.md` and `DECISIONS.md`, 2026-11-05, merged into `main` as `77575d5` (pull request #9). Each implementation task below still needs its own scoped branch, validation evidence, and owner review before merging. Phase 1 authorization does not approve every proposed engineering change.

Milestone acceptance criteria. Phase 1 is complete only when all eight hold:
- [x] 1. **Python CI.** A GitHub Actions workflow runs `python -m pytest tests --ignore=tests/test_final_holdout.py` on every pull request to `main` and on every push to `main`, and the run reports 0 failures and 0 errors. It never runs `tests/test_final_holdout.py` or `python -m infralens.evaluation.final_holdout`. Met 2026-11-18 (owner review): the `pull_request` run on `024f1ef` (https://github.com/tiniusms/InfraLens/actions/runs/43917146533) and the `push` run on `3f88fa2` (https://github.com/tiniusms/InfraLens/actions/runs/43921652102) passed. The push run reported 190 passed, 14 skipped, 0 failed, and did not collect `tests/test_final_holdout.py`.
- [x] 2. **Frontend CI.** The same automation runs `npm ci`, `npm test`, `npm run lint`, and `npm run build` in `frontend/` on the same triggers, and all four exit with status 0. Met 2026-11-18 (owner review): the frontend job passed in both runs listed under criterion 1. The push run reported 41 passed, and lint and build passed.
- [x] 3. **Regression preservation.** No currently passing test is deleted, weakened, marked skip, or marked xfail to make CI pass. On a machine with the four gitignored caches, the non-holdout suite still reports at least 203 passed and 0 failed, and `npm test` at least 41 passed. In CI without those caches, any skip must be one of the existing missing-cache skips, with its reason shown (`RISK_REGISTER.md`, R7). Met 2026-11-18 (owner review): Phase 1A deleted, skipped, and xfailed no test (see "Phase 1A" below). Local full-data run on `024f1ef` (`.venv-arm64` with the four caches, reported in the pull request #10 comment): 204 passed, 0 failed, 1 warning; `npm test` 41 passed. All 14 skips in the push run listed under criterion 1 have missing-cache reasons.
- [x] 4. **Native Apple Silicon setup.** `README.md` documents creating an arm64 Python 3.11+ virtual environment, checking that `python -c "import platform; print(platform.machine())"` prints `arm64`, installing `.[dev,demo,api]`, and running the checks in criteria 1–2. A fresh environment built only from those steps passes them. The x86_64 `.venv` problem found on 2026-11-04 is either fixed or documented. Met 2026-11-20 (pending owner review): `README.md`, "Native Apple Silicon setup", including "Troubleshooting: an x86_64 `.venv`". Followed step by step on an Apple M5 (`uname -m` arm64, not translated), python.org Python 3.13.7 arm64, Node.js v24.21.0 arm64, installing with `-c requirements-api.txt`, `pip check` clean. A new environment in this checkout with the four caches: 204 passed, 1 warning. A fresh clone of `482a710` without the caches: 190 passed, 14 skipped (all missing-cache reasons), 1 warning. In both, `npm test` 41 passed, and lint and build exited 0. Both verification environments were deleted afterwards; the existing `.venv` and `.venv-arm64` were not changed.
- [x] 5. **Consistent governance and development docs.** `CLAUDE.md`, `AGENTS.md`, `PROJECT_CONTEXT.md`, `README.md`, `TASKS.md`, and `DECISIONS.md` agree on the Version 2 status, phase gates, and local commands. No current-guidance file describes a retired host as live or Cursor as required. Met 2026-11-20 (pending owner review): pull request #11 (merged as `5743439`) aligned the Version 2 status and phase gates. A cross-file check of setup, test, lint, build, and run commands in these files, `README_ONBOARDING.md`, `ARCHITECTURE.md`, `docs/demo_walkthrough.md`, and `.github/workflows/ci.yml` found seven mismatches, fixed in the same change as criterion 4: install lines without `-c requirements-api.txt` in `README.md` (two), `ARCHITECTURE.md` (three), and `docs/demo_walkthrough.md` (one), each keeping its existing extras, and a bare `pytest` in `README.md`, which also collects `tests/test_final_holdout.py`. After those fixes the commands agree. `DECISIONS.md` entries and `docs/infrastructure_decommission_2026_11_03.md` are historical and unchanged.
- [ ] 6. **Historical evidence unchanged.** Compared with the ratification merge commit, there is no diff in `docs/final_eia_holdout_oneshot.json` (SHA-256 `5b116d9d0eaba5269f5afab71f60c826f4553174fb330e6e8fe80dfb6eba1393`), `docs/public_release_validation.md`, `docs/infrastructure_decommission_2026_11_03.md`, the recorded results in `EVALUATION.md` and `EXPERIMENTS.md`, or any `DECISIONS.md` entry dated before the change. The final holdout is not rerun and local holdout artifacts are not regenerated.
- [ ] 7. **No hosted or paid services.** Phase 1 adds no deployment workflow, hosting-provider secret, paid runner, public endpoint, or domain. CI uses only GitHub-hosted Actions within the plan's included usage. Any expected cost beyond that needs owner approval first.
- [ ] 8. **Technical-debt assessment.** `docs/technical_debt_assessment_v2.md` lists known technical debt as a table. Each item has an ID, location (file or module), description, evidence (command output or `file:line`), category, impact, proposed phase (1–5 or "accept"), and rough effort (S/M/L). Categories are: dependencies, tests, documentation drift, architecture, data provenance, and portability. At minimum it covers: declared-but-unused dependencies (DuckDB, Matplotlib); unpinned dependencies and the `annotated-doc` drift; the Linux `st_birthtime` limitation (R9); cache-dependent test skips (R6, R7); the Starlette `httpx` test-client deprecation; the Vite chunk-size warning; the `npm` deprecation warning for `eslint@9.39.5`; the stale branch reference in `ARCHITECTURE.md`; the undocumented `stash@{0}`; the undocumented dependency between workflow files and `tests/test_portable_deploy.py`; and `.venv-arm64` and other venv names are not in `.gitignore` (ignored only through the venv's own internal `.gitignore`). The assessment changes no code, dependencies, tests or data, and adds no new tools. Fixing anything it finds needs its own approved task. Phase 1 closes when every item is either assigned a phase or accepted, not when every item is fixed.

### Phase 1A — Continuous integration (implementation status, 2026-11-13)
Branch `feat/v2-phase1-ci`, merged into `main` as `3f88fa2` (pull request #10, 2026-11-16). Adds `.github/workflows/ci.yml` ("CI") on pull requests to `main` and pushes to `main`, with `contents: read` only, no secrets, and no deployment step. The existing "Portable image" workflow is unchanged. Criteria 1–2 require both triggers: a passing pull request run verifies only the `pull_request` trigger, and a separate successful run on `main` after merge is needed to verify the `push` trigger. Criteria 1–3 stayed unchecked until both runs passed and the owner reviewed them; that review was on 2026-11-18.
- [x] Python job: Ubuntu, Python 3.13, `pip install -e ".[dev,demo,api]" -c requirements-api.txt`, then `python -m pytest tests --ignore=tests/test_final_holdout.py -rs`. The skip reasons and final count go to the job summary.
- [x] Frontend job: Ubuntu, Node.js 24, `npm ci`, `npm test` (`vitest run`, non-interactive), `npm run lint`, `npm run build` in `frontend/`.
- [x] Local clean-clone simulation (fresh clone without the four caches, fresh Python 3.13.7 arm64 environment, same commands): 189 passed, 14 skipped, 1 warning. All 14 skips are the existing missing-cache skips (EIA history, holdout cases, PJM workbooks). They are in six files: the five skip-point files listed in `RISK_REGISTER.md` R7, plus `tests/test_api_contract.py`, whose four missing-cache skips (EIA history 1, holdout cases 2, PJM workbooks 1) were added on 2026-10-19, after the R7 audit. R7 is a historical record and is not rewritten here. Frontend: 41 passed; lint and build passed.
- [x] Local full-data run (`.venv-arm64`, all four caches): 203 passed, 1 warning. 189 + 14 = 203, so CI runs the same tests and skips only the cache-dependent ones. CI was expected to report 189 passed and 14 skipped, not 203 (superseded by the macOS/Linux fix below).
- [x] First GitHub-hosted run on pull request #10 (2026-11-13, Python 3.13.18 on Linux x86_64): 2 failed, 187 passed, 14 skipped, 1 warning. Frontend and "Portable image" passed. Both failures were in `tests/test_demo_pjm_screen.py` (`test_missing_or_malformed_workbook_does_not_invent_a_vintage`, `test_file_identity_uses_size_and_creation_time`). They assumed macOS: `local_workbook_retrieved_at` reads the file-creation time `st_birthtime`, which Python on Linux does not report, and it then refuses by design with `RETRIEVAL_UNAVAILABLE` rather than inventing a retrieval time.
- [x] Fix approved by the owner on 2026-11-16 (option A, test-only): the two tests now set the creation time explicitly with a `Path.stat` test double, so the real retrieval code runs the same on macOS and Linux. The assertions are kept and the file-identity test now also checks the later-of-two creation times and both recorded times. A new test, `test_missing_creation_time_is_reported_not_invented`, covers the no-creation-time refusal, which macOS runs never exercised. No application code changed and no skip was added. Local results: full-data 204 passed, 1 warning; clean clone 190 passed, 14 skipped on macOS and with the creation time hidden as on Linux. CI is now expected to report 190 passed and 14 skipped.
- Known limitation (not changed in Phase 1A): on Linux the PJM screening tab cannot show numbers even when both workbooks are present, because no file-creation time is available and none is invented. The portable Linux image does not ship the workbooks, so current behavior is unaffected. Any change to the retrieval-time rule on Linux, such as another timestamp source, needs its own decision.
- [x] Install finding: an unconstrained fresh install resolved `annotated-doc` 0.0.6, and `tests/test_portable_deploy.py::test_pinned_runtime_metadata_has_no_missing_requirement` failed against the 0.0.5 pin in `requirements-api.txt`. CI uses that file as a pip constraints file; the test is unchanged. A fresh local install from the current README steps can still hit this drift until Phase 1 criterion 4 documents the setup.
- [x] GitHub-hosted run of both CI jobs passes on the pull request (`pull_request` trigger; owner review). Pull request #10 at `024f1ef`: https://github.com/tiniusms/InfraLens/actions/runs/43917146533. Both jobs passed.
- [x] GitHub-hosted run of both CI jobs passes on `main` after merge (`push` trigger; owner review). `main` at `3f88fa2`: https://github.com/tiniusms/InfraLens/actions/runs/43921652102. Both jobs passed: Python 190 passed, 14 skipped (all missing-cache reasons), 0 failed, `tests/test_final_holdout.py` not collected; frontend 41 passed, lint and build passed.
- Known warnings: one Starlette `httpx` test-client deprecation warning in pytest, and the existing Vite chunk-size warning (about 756 kB) in the build. Neither fails a job.

## Version 2 phase roadmap (charter section 8)
Phase descriptions are quoted from `docs/version_2_charter.md`. Phases 2–5 are not yet scoped and require owner approval: each needs a dated scope decision with measurable acceptance criteria before work starts. Phases may overlap only where dependencies are satisfied and owner-approved milestones are defined.

### Phase 2 — Data reliability
EIA vintage archival, provenance, availability timing, and PJM-source improvements. Not yet scoped; requires owner approval.

### Phase 3 — Forecasting development
Preregistered experimental design, candidate modeling, baseline comparison, uncertainty and robustness evaluation. Not yet scoped; requires owner approval and the preregistration gate below.

### Phase 4 — Analytical expansion
Multi-year financial scenarios, sensitivity analysis, improved screening, and explainable outputs. Not yet scoped; requires owner approval and, for discounted scenarios, the financial-assumptions gate below.

### Phase 5 — Product refinement
User experience, integration quality, documentation, and readiness assessment for optional future deployment. Not yet scoped; requires owner approval. A readiness assessment is not a deployment.

## Version 2 gates that need a separate dated decision
- [ ] Phase 3 forecasting preregistration: target, data, forecast origin, feature availability, baseline comparisons (seasonal-naive and regularized-linear remain required), evaluation windows, metrics, numeric thresholds, and untouched evaluation data. No performance claim before it is approved. The 2026-10-04 holdout stays closed.
- [ ] Financial assumptions decision for discounted multi-year scenarios (discount rate, horizon, escalation, units) before any implementation.
- [ ] Any new geographic coverage, including Texas/ERCOT (see "Later / Stretch"), needs a scope decision and data-validity review.
- [ ] Any public deployment or paid infrastructure.

## Claude Code development handoff (2026-11-04)
- [x] Fast-forward local `main` to `origin/main` at `44f45a8` (pull request #7) and confirm its tree matches the retirement branch.
- [x] Run the local checks with Claude Code in `.venv-arm64`: 203 Python tests passed with the final holdout excluded, 41 frontend tests passed, and lint and build passed.
- [x] Record the completed capstone, Claude Code as primary agent, and the Version 2 approval gate in `DECISIONS.md`, `AGENTS.md`, `CLAUDE.md`, `PROJECT_CONTEXT.md`, and `README.md`.
- [x] Approve Version 2 scope in a dated `DECISIONS.md` entry before Version 2 feature work. Done by the 2026-11-05 charter ratification. Evaluation criteria are still gated (see "Version 2 gates").
- [ ] Preregister a new Version 2 forecasting evaluation before any performance claim. The 2026-10-04 holdout stays closed. Tracked as the Phase 3 gate above.

## Hosting retirement and Claude Code preparation (2026-11-03)
- [x] Record the November 3, 2026 public-hosting retirement without altering the October 20, 2026 validation merged in pull request #6.
- [x] Confirm local API and frontend defaults do not call the retired Vercel, Render, or Cloudflare hosts.
- [x] Keep `Dockerfile`, `render.yaml`, `frontend/vercel.json`, and `deploy/` as retired deployment examples.
- [x] Leave `AGENTS.md` and `CLAUDE.md` usable by a standalone coding agent. Cursor project rules remain; they are not required to run the local app.
- [ ] Redeploy only after a new approval and the prerequisites in `docs/infrastructure_decommission_2026_11_03.md`. Registry release of `infralensenergy.com` is still unverified.
- [ ] Version 2 feature work is outside this retirement.

## Now
- [x] Scaffold Python package (`src/infralens`, tests, data dirs, feasibility-sprint deps).
- [x] Create GitHub repository and copy the onboarding pack into root.
- [x] Obtain/configure EIA API key.
- [x] Pull monthly commercial electricity price/sales history for PJM states.
- [x] Inventory archived/current PJM load-forecast files and document publication dates.
- [x] Build first data dictionary with source, unit, frequency, availability date, and leakage risk.
- [x] Availability-adjusted seasonal-naive baseline (not unavailable t-12).
- [x] Run first publication-lag-constrained current-vintage backtest.
- [x] Regularized linear EIA baseline (Ridge) on the same development backtest. Holdout still untouched. PJM not joined.
- [x] Histogram gradient-boosting EIA candidate on the same features and development backtest. Holdout still untouched.
- [x] Select Ridge on the 1,145-case development comparison and freeze that model class and feature set. Holdout still untouched.
- [x] State-specific 80% absolute-residual intervals for the frozen Ridge model. Development evaluation only. Holdout still untouched. Method not retuned.
- [x] Exact Ridge coefficient explanations for each development origin. Not SHAP. Holdout still untouched.
- [x] Implement and test the locked final-holdout runner.
- [x] Execute the one-shot final holdout from `ee5bcf6` on 2026-10-04. Primary criterion FAIL. Do not rerun it or retune from it.

## Next
- [x] PJM screening Slice 1: 2025 and 2026 Table B1 summer peak and 10-year decimal growth, with file-level availability. Not an EIA join.
- [x] PJM screening Slice 2: 2025 and 2026 Table B-9 and B-9b as separate MW series. Not data-center demand and not an EIA join.
- [x] PJM screening view: newest public vintage with complete B1, B-9, and B-9b for one zone and forecast year. No state join and no risk score.
- [ ] Later PJM slice: 2024 PDF Table B1 and B-9. Do not treat adjustment MW as data-center demand.
- [x] Financial engine: deterministic annual electricity cost from IT capacity, PUE, utilization, hours, and cents/kWh. Not a DCF, tariff engine, or risk score.
- [x] Streamlit MVP.
  - [x] Foundation page: committed FAIL banner, portable vs local file check, and the annual cost form. A holdout Ridge price sets `model_derived_eia_price` automatically.
  - [x] Historical price chart and closed-holdout comparison chart. The FAIL banner stays above the tabs. A missing parquet file leaves that chart unavailable.
  - [x] PJM screening tab: one public vintage for a zone and forecast year, with B1, B-9, and B-9b kept separate. No state join and no risk score.

## Later / Deferred
- MLflow tracking. Deferred 2026-09-29. `mlruns/` is gitignored, and the development evidence is already in `EVALUATION.md`, `EXPERIMENTS.md`, and `DECISIONS.md`. Do not add MLflow as a new tuning loop.
- Discounted multi-year electricity cost. Charter workstream C, Phase 4. Needs its own dated financial-assumptions decision before implementation. The current calculator stays an annual energy-charge identity.

## Later / Stretch
- [ ] Utility-specific tariff enrichment.
- [ ] Automated FERC/state regulatory extraction.
- [ ] EPA/brownfield map integration.
- [ ] Texas/ERCOT expansion. Unapproved future scope: needs a separate scope decision and data-validity review (`docs/version_2_charter.md`, section 4).

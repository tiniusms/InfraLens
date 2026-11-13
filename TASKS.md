# InfraLens Current Tasks

## Version 2 Phase 1 — Engineering foundation (authorized 2026-11-05)
Governance: `docs/version_2_charter.md` and `DECISIONS.md`, 2026-11-05. Phase 1 work starts only after that ratification is merged into `main`. Each implementation task below still needs its own scoped branch, validation evidence, and owner review before merging. Phase 1 authorization does not approve every proposed engineering change.

Milestone acceptance criteria. Phase 1 is complete only when all seven hold:
- [ ] 1. **Python CI.** A GitHub Actions workflow runs `python -m pytest tests --ignore=tests/test_final_holdout.py` on every pull request to `main` and on every push to `main`, and the run reports 0 failures and 0 errors. It never runs `tests/test_final_holdout.py` or `python -m infralens.evaluation.final_holdout`.
- [ ] 2. **Frontend CI.** The same automation runs `npm ci`, `npm test`, `npm run lint`, and `npm run build` in `frontend/` on the same triggers, and all four exit with status 0.
- [ ] 3. **Regression preservation.** No currently passing test is deleted, weakened, marked skip, or marked xfail to make CI pass. On a machine with the four gitignored caches, the non-holdout suite still reports at least 203 passed and 0 failed, and `npm test` at least 41 passed. In CI without those caches, any skip must be one of the existing missing-cache skips, with its reason shown (`RISK_REGISTER.md`, R7).
- [ ] 4. **Native Apple Silicon setup.** `README.md` documents creating an arm64 Python 3.11+ virtual environment, checking that `python -c "import platform; print(platform.machine())"` prints `arm64`, installing `.[dev,demo,api]`, and running the checks in criteria 1–2. A fresh environment built only from those steps passes them. The x86_64 `.venv` problem found on 2026-11-04 is either fixed or documented.
- [ ] 5. **Consistent governance and development docs.** `CLAUDE.md`, `AGENTS.md`, `PROJECT_CONTEXT.md`, `README.md`, `TASKS.md`, and `DECISIONS.md` agree on the Version 2 status, phase gates, and local commands. No current-guidance file describes a retired host as live or Cursor as required.
- [ ] 6. **Historical evidence unchanged.** Compared with the ratification merge commit, there is no diff in `docs/final_eia_holdout_oneshot.json` (SHA-256 `5b116d9d0eaba5269f5afab71f60c826f4553174fb330e6e8fe80dfb6eba1393`), `docs/public_release_validation.md`, `docs/infrastructure_decommission_2026_11_03.md`, the recorded results in `EVALUATION.md` and `EXPERIMENTS.md`, or any `DECISIONS.md` entry dated before the change. The final holdout is not rerun and local holdout artifacts are not regenerated.
- [ ] 7. **No hosted or paid services.** Phase 1 adds no deployment workflow, hosting-provider secret, paid runner, public endpoint, or domain. CI uses only GitHub-hosted Actions within the plan's included usage. Any expected cost beyond that needs owner approval first.

### Phase 1A — Continuous integration (implementation status, 2026-11-13)
Branch `feat/v2-phase1-ci`. Adds `.github/workflows/ci.yml` ("CI") on pull requests to `main` and pushes to `main`, with `contents: read` only, no secrets, and no deployment step. The existing "Portable image" workflow is unchanged. Criteria 1–3 stay unchecked until the GitHub-hosted checks pass on the pull request and the owner reviews them.
- [x] Python job: Ubuntu, Python 3.13, `pip install -e ".[dev,demo,api]" -c requirements-api.txt`, then `python -m pytest tests --ignore=tests/test_final_holdout.py -rs`. The skip reasons and final count go to the job summary.
- [x] Frontend job: Ubuntu, Node.js 24, `npm ci`, `npm test` (`vitest run`, non-interactive), `npm run lint`, `npm run build` in `frontend/`.
- [x] Local clean-clone simulation (fresh clone without the four caches, fresh Python 3.13.7 arm64 environment, same commands): 189 passed, 14 skipped, 1 warning. All 14 skips are the existing missing-cache skips (EIA history, holdout cases, PJM workbooks). Frontend: 41 passed; lint and build passed.
- [x] Local full-data run (`.venv-arm64`, all four caches): 203 passed, 1 warning. 189 + 14 = 203, so CI runs the same tests and skips only the cache-dependent ones. CI is expected to report 189 passed and 14 skipped, not 203.
- [x] Install finding: an unconstrained fresh install resolved `annotated-doc` 0.0.6, and `tests/test_portable_deploy.py::test_pinned_runtime_metadata_has_no_missing_requirement` failed against the 0.0.5 pin in `requirements-api.txt`. CI uses that file as a pip constraints file; the test is unchanged. A fresh local install from the current README steps can still hit this drift until Phase 1 criterion 4 documents the setup.
- [ ] GitHub-hosted run of both CI jobs passes on the pull request (owner review).
- Known warnings: one Starlette `httpx` test-client deprecation warning in pytest, and the existing Vite chunk-size warning (about 756 kB) in the build. Neither fails a job.

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

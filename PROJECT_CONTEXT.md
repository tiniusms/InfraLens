# InfraLens - Project Context and AI Tool Onboarding

## 1. Project status
**Status update (2026-11-05):** The Version 2 charter, `docs/version_2_charter.md`, is ratified in the 2026-11-05 entry of `DECISIONS.md`. Version 2 balances electricity-price forecasting, PJM infrastructure screening, financial decision support, and product engineering for VA, PA, OH, MD, and NJ, with local-only development. Phase 1 (engineering foundation) is complete (2026-11-20, see `DECISIONS.md`), Phase 2 (data reliability) is complete (2026-11-25, see `DECISIONS.md`), and Phases 3–5 need owner-approved scope before work starts. Phase 3 also needs its own preregistration decision, which must name the tier it uses under the three-tier EIA vintage policy (`DECISIONS.md`, 2026-11-23). Phase 3 forecasting claims, material financial assumptions, new geography, public deployment, and paid infrastructure need separate dated decisions. Sections 2–12 below remain the original capstone brief and do not define Version 2 scope.

**Status update (2026-11-04):** The academic capstone is complete. Its final evaluation is closed and recorded in `EVALUATION.md` and in the 2026-10-04 entry of `DECISIONS.md`. InfraLens continues as an independently developed AI infrastructure-analysis product, developed locally with Claude Code as the primary development agent. Public deployment remains retired. The rest of this file is the original capstone brief. Only the tool roles in section 9 and rule 10 in section 10 were updated on 2026-11-04.

**Primary capstone:** InfraLens - Explainable AI for Power-Cost Forecasting and Capital-Risk Screening of Data Center Locations.

**Fallback:** RateLens - Explainable bank net-interest-margin forecasting using FDIC/FRED data.

**Current decision:** Proceed with InfraLens through a short public-data feasibility gate. If the core forecast cannot be supported with credible data and temporal evaluation, pivot quickly to RateLens rather than weakening the project with synthetic data.

## 2. Intended user and decision
**Primary user:** Corporate-development, infrastructure-investment, or project-finance analyst evaluating data-center expansion.

**Decision supported:** Which candidate regions deserve deeper diligence, and how could future electricity-cost and infrastructure risk change the financial attractiveness of a project?

InfraLens is a **screening and decision-support tool**, not an engineering interconnection study, utility tariff engine, or final investment recommendation.

## 3. Version 1 scope
- Geography: PJM state footprint for model training; user-facing comparison initially emphasizes VA, PA, OH, MD, and NJ.
- Primary ML target: 12-month-ahead commercial electricity price (public-data proxy) by state.
- Core data: EIA retail electricity prices/sales; PJM load forecasts and data-center forecast material.
- Secondary structured risk indicators: selected PJM, FERC, and EPA information only where reproducible and stable.
- Finance layer: annual electricity expense, discounted multi-year power cost, base/upside/downside scenarios, and sensitivity to price/delay assumptions.
- Explainability: SHAP or equivalent feature-attribution method; explain model behavior, not causal effects.
- Uncertainty: quantile/conformal or other calibrated prediction intervals.
- UI: Streamlit.
- Packaging: Docker + GitHub.

## 4. Non-goals for Version 1
- Do not claim parcel-level optimal siting across the United States.
- Do not claim exact data-center electricity tariff or PPA pricing from general EIA commercial prices.
- Do not predict permit approval or community opposition as a validated label.
- Do not allow an LLM to calculate financial outputs.
- Do not use synthetic data when real public data are available.
- Do not use proprietary Morgan Stanley/JPMorgan research as public project data.

## 5. Provisional research questions
1. Can ML reduce 12-month-ahead electricity-price MAE relative to seasonal-naive and regularized linear baselines?
2. Can the model produce calibrated uncertainty intervals useful for investment screening?
3. Which variables drive forecast power-cost risk and can those drivers be explained clearly to an analyst?
4. Does uncertainty-adjusted financial translation change candidate prioritization relative to current price alone?

## 6. Success criteria set before modeling
- >=10% lower holdout MAE than a seasonal-naive baseline.
- Beat a regularized linear baseline, or document that additional complexity is not justified.
- Intended 80% prediction intervals achieve 75-85% empirical coverage on the final temporal holdout.
- 100% traceability from dashboard output to model version, data date, and assumptions.
- Cached candidate analysis returns in <5 seconds on a standard laptop.

Clarified 2026-09-30, before any final-holdout score:

The primary pass/fail rule is: at least 10% lower MAE for frozen Ridge than the availability-adjusted seasonal-naive baseline on identical paired final-holdout cases (target months 2025-07 through 2026-06). State-level MAE is descriptive only.

The regularized-linear criterion was resolved in development on 2026-09-29, when Ridge had lower development MAE than the histogram-gradient-boosting candidate. That comparison is closed and is not a second final-holdout gate.

The 75–85% interval-coverage range is a diagnostic calibration check. It is not the primary model pass/fail gate and it is not a reason to retune.

## 7. Engineering stack
Python -> EIA/PJM/FERC/EPA -> Parquet -> pandas/polars as needed -> scikit-learn + XGBoost/HistGradientBoosting -> MLflow -> SHAP -> Streamlit -> Docker -> GitHub.

DuckDB was dropped from the stack in Phase 2 (TD-01, PR #27): it was declared but never used, and vintage archival does not need it.

Prefer open-source and local-first tooling. Avoid unnecessary vendor lock-in.

## 8. Repository source-of-truth files
- `README.md` - what the project is and how to run it.
- `PROJECT_CONTEXT.md` - this file; stable scope and intent.
- `AGENTS.md` - instructions every AI coding/review tool must follow.
- `DECISIONS.md` - dated architecture/model/scope decisions and rationale.
- `DATA_DICTIONARY.md` - every variable, source, unit, frequency, availability date, and leakage risk.
- `ARCHITECTURE.md` - components and data flow.
- `EXPERIMENTS.md` - human-readable experiment log; MLflow stores run metadata.
- `EVALUATION.md` - splits, metrics, baselines, success thresholds, and failure tests.
- `RISK_REGISTER.md` - project and model risks.
- `LITERATURE.md` - annotated research notes and APA references.
- `TASKS.md` - current sprint backlog.

Platform-specific files (`CLAUDE.md`, Cursor rules) should point back to `AGENTS.md`/`PROJECT_CONTEXT.md` rather than duplicating the project description.

## 9. AI tool roles
### ChatGPT
Project management, scope control, domain learning, research synthesis, statistics/evaluation design, financial-analysis explanation, APA drafting, and final defense preparation.

### Cursor
Primary implementation environment during the capstone. No longer required as of 2026-11-04. `.cursor/rules/infralens.mdc` stays as an optional pointer to `AGENTS.md`.

### Claude / Claude Code
Primary implementation, testing, and Git development agent as of 2026-11-04. Read `AGENTS.md`, `PROJECT_CONTEXT.md`, and `DECISIONS.md` before major changes. Use it for implementation, debugging, refactoring, tests, branch and commit work, and adversarial review. It works on dedicated branches and does not push, open pull requests, merge, or deploy without the project owner's approval. It should not silently redefine scope or metrics. Public hosting was retired on 2026-11-03. Develop with the local commands in `README.md`, and do not call retired production hosts.

### Perplexity
Rapid discovery of recent academic/industry sources. Treat it as a discovery engine; verify important claims against original papers, agencies, or primary documentation before use.

### Gemini / Kimi
Optional secondary long-context review for large reports, documentation consistency, or alternative critique. Use only where it adds value.

### GitHub
The actual source of truth. Chat histories are not authoritative project state. GitHub `main` is the authoritative committed baseline; local uncommitted work must be inspected and protected rather than overwritten (2026-11-05).

## 10. Rules for all AI collaborators
1. Never change the target, scope, success metrics, or evaluation split without recording the change in `DECISIONS.md`.
2. Never use future information in features. Respect data publication dates, not just observation dates.
3. Never claim causality from SHAP/feature importance.
4. Never fabricate data to make the demo look complete.
5. Never hide negative experiments.
6. Keep financial calculations deterministic and testable.
7. Prefer the simplest model that wins out-of-sample.
8. Every modeling claim must point to a reproducible experiment.
9. Every dashboard output must show data date, model version, and assumptions.
10. If an AI assistant proposes a major new feature, first ask whether it improves the intended analyst decision and whether it fits scope approved in `DECISIONS.md`. (Capstone wording: "feasible before Oct. 25.")

## 11. Data feasibility gate
Before committing to full InfraLens implementation, verify:
- EIA monthly state commercial-price history can be acquired reliably and covers the target period.
- PJM state/zonal planning data can be joined at a defensible geographic/time level or used as transparent external indicators.
- Publication/availability dates can be tracked to prevent look-ahead leakage.
- A baseline can be built without special/proprietary data.

If these conditions fail materially, pivot to RateLens immediately.

## 12. Definition of a finished capstone
A finished project is not just a notebook. It includes:
- reproducible data ingestion,
- documented raw/intermediate/feature data,
- baseline and candidate models,
- temporal backtesting,
- uncertainty and explainability,
- financial translation,
- failure/robustness analysis,
- working Streamlit demo,
- Dockerized or otherwise reproducible environment,
- GitHub documentation,
- APA research portfolio,
- and a live defense that can replay a historical prediction using only information available at that time.

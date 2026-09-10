# InfraLens Decision Log

Use one entry for every material change in scope, data, model, evaluation, architecture, or financial assumptions.

## 2026-09-09 - Python repository scaffold (no scope change)
**Decision:** Use a `src/infralens` installable package with `data/raw|interim|processed`, `tests`, `docs`, and `notebooks`. Feasibility-sprint dependencies only (pandas, pyarrow, duckdb, httpx, scikit-learn, matplotlib, python-dotenv, pytest, jupyter).
**Evidence:** Matches locked engineering stack for ingestion and a seasonal-naive baseline; defers XGBoost, SHAP, MLflow, Streamlit, and Docker until those tasks start.
**Alternatives considered:** Flat (non-src) layout; adding full modeling/UI dependencies now.
**Impact:** No change to target, geography, success criteria, or evaluation split.
**Revisit trigger:** Data feasibility fails, or a later sprint requires additional packages.

## 2026-09-08 - Initial project lock
**Decision:** InfraLens is the primary capstone; RateLens is fallback.
**Scope:** PJM-first, 12-month commercial electricity-price forecasting as the core ML task, with financial translation and transparent infrastructure-risk indicators.
**Reason:** Strong intersection of AI, financial analysis, energy, corporate relevance, real public data, and portfolio value.
**Revisit trigger:** Core public-data feasibility fails during the initial data sprint.

## Template
### YYYY-MM-DD - Short decision name
**Decision:**
**Evidence:**
**Alternatives considered:**
**Impact:**
**Revisit trigger:**

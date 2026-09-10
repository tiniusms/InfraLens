# InfraLens Decision Log

Use one entry for every material change in scope, data, model, evaluation, architecture, or financial assumptions.

## 2026-09-09 - EIA v2 retail-sales feasibility ingest
**Decision:** Ingest monthly commercial (COM) EIA API v2 `electricity/retail-sales` price, sales, and revenue for VA, PA, OH, MD, and NJ from 2001-01, with retrieval split from normalization, immutable key-redacted raw JSON, and interim Parquet.
**Evidence:** EIA documents this series from 2001-01 on monthly `YYYY-MM` periods; it is the public commercial-price proxy locked in project context.
**Alternatives considered:** EIA-861 annual files only; including residential/industrial sectors in v1.
**Impact:** No change to target, geography, success criteria, or evaluation split. No feature engineering or modeling.
**Revisit trigger:** API coverage or publication-lag documentation is insufficient for point-in-time evaluation.

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

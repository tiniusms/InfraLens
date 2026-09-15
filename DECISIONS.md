# InfraLens Decision Log

Use one entry for every material change in scope, data, model, evaluation, architecture, or financial assumptions.

## 2026-09-14 - Publication-lag-constrained current-vintage evaluation
**Decision:** For EIA month *m*, set `assumed_available_at` to the first day of month *m+3*. Forecast origin is the analyst decision date. The primary target is commercial price in the calendar month 12 months after that origin. Every input at an origin must satisfy `assumed_available_at <= forecast_origin`. The baseline is availability-adjusted seasonal-naive: the most recent same-calendar-month observation that was available at the origin—not an unavailable t-12. This backtest is a **publication-lag-constrained current-vintage** evaluation: API history may already include later revisions and is not a real-time vintage replay.
**Evidence:** EIA API rows have no publication/revision timestamp. EPM Table 5.6.A currently lags the data month by about two months (e.g. June 2026 released 2026-08-26). Form EIA-861M/826 data are due at the end of the following month. A three-month lag to the *first day of m+3* is conservative relative to that schedule.
**Alternatives considered:** Use `period` as availability (rejected: leakage). Use a two-month lag (less conservative). Wait for a full historical vintage calendar before any baseline (blocks the capstone). Pure t-12 on observation time (would use June 2024 at a 2024-06-30 origin).
**Impact:** Locks the first evaluation convention. Does not change the ML target (12-month-ahead commercial price), geography, or success metric (MAE vs this baseline). Reserves target months 2025-07 through 2026-06 as the final holdout until model selection.
**Revisit trigger:** An official month-by-month EPM/API release calendar or vintage file shows that m+3 is too strict or too loose.

## 2026-09-11 - EIA observation period is not a point-in-time availability date
**Decision:** Current EIA retail-sales extracts remain suitable for feasibility and descriptive analysis. They must not be used as if each row were available during its observation month. Publication lag and historical revision/vintage behavior must be resolved before temporal baselines or forecasting features are finalized.
**Evidence:** The API payload records `period` (calendar month of the statistic) and InfraLens records `retrieved_at` (extract time). It does not provide the date EIA first published or last revised each month. Point-in-time availability is still TBD in `DATA_DICTIONARY.md`.
**Alternatives considered:** Treat `period` as the forecast-origin availability date; delay all EIA use until a vintage calendar exists.
**Impact:** Open evaluation constraint only. No change to target, geography, success criteria, or evaluation split. No modeling or feature engineering in this change.
**Revisit trigger:** A documented publication-lag / revision calendar exists that can be applied at forecast origin.

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

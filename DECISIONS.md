# InfraLens Decision Log

Use one entry for every material change in scope, data, model, evaluation, architecture, or financial assumptions.

## 2026-09-29 - Ridge is the development-selected EIA candidate; model class and features are frozen
**Decision:** Predictive model-class selection for the EIA commercial-price forecast is closed. **Ridge is the development-selected candidate.** Histogram gradient boosting is retained only as negative evidence. The feature set and the Ridge penalty procedure below are frozen before any final-holdout evaluation. Do not add another predictive model. Do not add or remove predictive features from these development results. Do not retune Ridge from the aggregate development MAE. Do not fit state-specific model classes. Do not put PJM fields in the EIA model. Do not open target months 2025-07 through 2026-06 in this decision.
**Evidence:** Identical common cases: **1,145**. Paired seasonal-naive MAE **0.7997 ¢/kWh**. Ridge MAE **0.7075 ¢/kWh**. HistGradientBoostingRegressor MAE **0.7831 ¢/kWh**. Ridge is **0.0922 ¢/kWh / 11.5%** lower than the paired seasonal naive. The tree is **2.1%** lower than that seasonal naive and **10.7%** higher than Ridge. Ridge MAE is lower than the seasonal naive in all five states (MD, NJ, OH, PA, VA). The tree MAE is lower than Ridge only in Virginia. Full-window seasonal-naive MAE remains **0.7793 ¢/kWh on 1,350 cases** and is not the paired denominator. Extract: `data/interim/eia_retail_sales_monthly_com_20260911T190524Z.parquet`. Detail: `EVALUATION.md`.
**Frozen feature set** (`eia_commercial_price_v1`): `price_latest`, `price_same_month`, `price_yoy_change`, `price_trail12_mean`, `sales_latest`, `sales_yoy_change`, `state_id`, `target_calendar_month`. Revenue and PJM fields are not features.
**Frozen Ridge procedure:** At each origin, training rows are earlier origins whose target price is already available (`assumed_available_at <= forecast_origin`), whose target month is before 2025-07, and whose actual is present. The scored origin is excluded. The last 12 training origins are an inner validation slice; at least 12 earlier origins are required to fit. `StandardScaler` (numeric features) and `OneHotEncoder(drop="first")` (state and month) are fit on that earlier slice for each penalty in `(0.01, 0.1, 1, 10, 100, 1000)`. The lowest inner MAE wins. Ties at 0.000001 ¢/kWh keep the larger penalty. Scaler, encoder, and Ridge (`solver="cholesky"`) are then refit on all eligible pre-origin rows. This procedure stays in force for a future holdout run. The development mode (penalty 100 at the 2024-06-30 origin) is not a new fixed penalty.
**What this decision does not do:** It does not measure final-holdout performance and does not satisfy or fail the project success criterion. That criterion is a holdout comparison and remains unrun.
**Alternatives considered:** Select the tree because it is nonlinear (rejected: higher development MAE than Ridge on the common cases). Keep searching penalties or features (rejected: selection is closed). Use MLflow as the selection record (rejected in the same entry: the tracking directory is gitignored, and `HEAD` `4b92a5e` does not contain the model modules, so a run sha would not identify this evidence).
**Impact:** Model class and features are frozen. Holdout target months stay untouched. The written holdout protocol, the proposed residual-interval method, and the proposed Ridge explanation method are in `EVALUATION.md`. None of those three is executed here.
**Revisit trigger:** A later decision, made before looking at holdout scores, changes the forecast definition itself. A disappointing holdout score is not a revisit trigger for a new model class or a new feature set.

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

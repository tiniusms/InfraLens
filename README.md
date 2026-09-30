# InfraLens

Explainable AI for power-cost forecasting and capital-risk screening of data-center locations.

InfraLens is a **screening and decision-support tool** for corporate-development, infrastructure-investment, or project-finance analysts. It forecasts 12-month-ahead commercial electricity prices (public-data proxy) for PJM states, translates those forecasts into electricity-cost scenarios, and surfaces transparent infrastructure-risk indicators. It is not an interconnection study, tariff engine, or final investment recommendation.

## Status

Python package plus EIA monthly commercial retail-sales ingest for VA, PA, OH, MD, and NJ. The development-selected price model is Ridge. State-specific nominal-80% absolute-residual intervals and origin-specific Ridge explanations were run on the development window and committed before the holdout. The final holdout, target months 2025-07 through 2026-06, has not been scored. The Streamlit demo is not implemented yet.

Primary geography: PJM state footprint (user-facing comparison initially VA, PA, OH, MD, NJ).  
Due: 25 October 2026. Fallback project: RateLens (FDIC/FRED NIM forecasting) if public-data feasibility fails.

## Repository source of truth

| File | Role |
| --- | --- |
| `PROJECT_CONTEXT.md` | Stable scope, user, metrics, and non-goals |
| `AGENTS.md` | Rules for every AI coding/review tool |
| `DECISIONS.md` | Dated scope/data/model/evaluation changes |
| `TASKS.md` | Current sprint backlog |
| `CLAUDE.md` / `.cursor/rules/` | Thin adapters that point back to the files above |

GitHub is authoritative. Chat histories are not.

## Setup

Python 3.11+ is required.

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env        # then add an EIA API key: https://www.eia.gov/opendata/register.php
pytest
python -m infralens.data.eia_ingest
python -m infralens.evaluation.backtest
python -m infralens.evaluation.linear
python -m infralens.evaluation.tree
python -m infralens.evaluation.intervals
python -m infralens.evaluation.explain
```

HTTP client for this sprint is `httpx` (not `requests`). XGBoost, SHAP, MLflow, Streamlit, and Docker are not installed. MLflow stays deferred (`DECISIONS.md`, 2026-09-29). The selected EIA model is Ridge with feature set `eia_commercial_price_v1`. Its development uncertainty layer is a state-specific empirical absolute-residual interval with nominal 80% coverage. That nominal rate is not a guarantee of future coverage, and 75–85% holdout coverage is a diagnostic, not the primary pass/fail rule. Explanations are the origin-specific linear identity, intercept plus contributions, not SHAP and not causal effects.

The locked final comparison, not yet run, is at least 10% lower Ridge MAE than the availability-adjusted seasonal-naive baseline on the same holdout cases. The only command for that run is `python -m infralens.evaluation.final_holdout`. It accepts no options. Do not run it until the runner commit has been reviewed.

Raw EIA JSON is written under `data/raw/eia/` and the matching interim Parquet under `data/interim/`. Both filenames share the same UTC retrieval timestamp. There is no mutable “latest” Parquet alias. API keys are never logged; echoed `api_key` fields are redacted before the raw file is saved.

## Intended stack

Python → EIA/PJM/FERC/EPA → Parquet → DuckDB → scikit-learn + XGBoost/HistGradientBoosting → MLflow → SHAP → Streamlit → Docker.

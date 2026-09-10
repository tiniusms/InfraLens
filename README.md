# InfraLens

Explainable AI for power-cost forecasting and capital-risk screening of data-center locations.

InfraLens is a **screening and decision-support tool** for corporate-development, infrastructure-investment, or project-finance analysts. It forecasts 12-month-ahead commercial electricity prices (public-data proxy) for PJM states, translates those forecasts into electricity-cost scenarios, and surfaces transparent infrastructure-risk indicators. It is not an interconnection study, tariff engine, or final investment recommendation.

## Status

Python package scaffold for the public-data feasibility sprint. Data ingestion, baselines, and the Streamlit demo are not implemented yet.

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
```

HTTP client for this sprint is `httpx` (not `requests`). Later stack pieces (XGBoost, SHAP, MLflow, Streamlit, Docker) are intentionally not installed yet.

## Intended stack

Python → EIA/PJM/FERC/EPA → Parquet → DuckDB → scikit-learn + XGBoost/HistGradientBoosting → MLflow → SHAP → Streamlit → Docker.

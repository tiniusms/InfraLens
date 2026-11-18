# InfraLens

Explainable AI for power-cost forecasting and capital-risk screening of data-center locations.

InfraLens is a **screening and decision-support tool** for corporate-development, infrastructure-investment, or project-finance analysts. It compares a frozen 12-month-ahead commercial electricity-price model (a public EIA proxy) for PJM states with an availability-adjusted seasonal-naive baseline, turns a stated price into an annual electricity-cost scenario, and shows PJM zonal planning indicators. It is not an interconnection study, a tariff engine, or a final investment recommendation.

## Status

Python package plus EIA monthly commercial retail-sales history for VA, PA, OH, MD, and NJ. Ridge, feature set `eia_commercial_price_v1`, was the development-selected candidate. The one-shot final holdout, target months 2025-07 through 2026-06, was executed once on 2026-10-04 from `ee5bcf6` and failed the preregistered 10% paired-MAE test: Ridge MAE 2.638473 ¢/kWh versus paired seasonal-naive MAE 2.613667 ¢/kWh (−0.95%). Empirical interval coverage was 0%. That result is final. The recorded summary is `docs/final_eia_holdout_oneshot.json`. Do not run `python -m infralens.evaluation.final_holdout` again. Ridge is a closed historical evaluation, not a validated production forecast and not an investment recommendation.

A Streamlit page shows that FAIL result, the observed commercial-price history, the closed holdout comparison, the annual cost form, and a PJM zone-year screening tab. The price charts are historical evaluation. PJM zones are not joined to EIA states.

Primary geography: PJM state footprint (user-facing comparison initially VA, PA, OH, MD, NJ).  
Capstone due: 25 October 2026. The academic capstone is complete. Fallback project: RateLens (FDIC/FRED NIM forecasting) if public-data feasibility fails; the fallback was not used.

## Development after the capstone

InfraLens continues as an independently developed AI infrastructure-analysis product. Local development is the supported workflow, and public deployment remains retired. Claude Code is the primary implementation, testing, and Git development agent; Cursor is no longer required. GitHub `main` is the authoritative committed baseline.

The Version 2 charter is [`docs/version_2_charter.md`](docs/version_2_charter.md), ratified in `DECISIONS.md` on 2026-11-05. It balances forecasting, PJM screening, financial decision support, and product engineering for VA, PA, OH, MD, and NJ. Phase 1 (engineering foundation) is authorized (ratification merged as `77575d5`, pull request #9), under the acceptance criteria in `TASKS.md`. A Version 2 forecasting improvement cannot be claimed without a separately approved, preregistered evaluation. Discounted multi-year finance, new geography such as Texas/ERCOT, public deployment, and paid infrastructure each need their own decision. Version 1 results remain unchanged.

## Current deployment status

The previously validated Vercel frontend, Render API, and Cloudflare Tunnel were intentionally decommissioned on November 3, 2026. Those hosts are not a supported runtime. Do not call `https://infra-lens-gules.vercel.app` or `https://api.infralensenergy.com`.

On October 20, 2026 those names served the portable subset: the frozen commercial-price FAIL and the typed annual-cost calculator, without the EIA price history, the holdout-case file, or the PJM workbook measures. That check is historical evidence. It is not a description of infrastructure that is still running, and this retirement does not change the recorded FAIL.

Pull request #6, “docs: document verified InfraLens public release,” is merged to `main` as `895b5368cb3729953df1218346b78b39bec948e4`. Its evidence table stays in [`docs/public_release_validation.md`](docs/public_release_validation.md). The November 3 shutdown is a later event, recorded in [`docs/infrastructure_decommission_2026_11_03.md`](docs/infrastructure_decommission_2026_11_03.md) and in `DECISIONS.md`. The deployment templates in [`docs/portable_deployment.md`](docs/portable_deployment.md), `Dockerfile`, `render.yaml`, `frontend/vercel.json`, and `deploy/` remain available for a future redeploy. They do not provision a host by themselves.

The application source, FastAPI backend, React frontend, Streamlit demo, tests, and frozen evaluation artifacts remain in this repository for local development.

InfraLens is a historical evaluation, a deterministic hypothetical cost calculator, and an infrastructure-screening prototype. It is not a validated live production forecasting system and not an investment recommendation.

## Repository source of truth

| File | Role |
| --- | --- |
| `PROJECT_CONTEXT.md` | Stable scope, user, metrics, and non-goals |
| `AGENTS.md` | Rules for every AI coding/review tool |
| `DECISIONS.md` | Dated scope/data/model/evaluation changes |
| `TASKS.md` | Current sprint backlog |
| `ARCHITECTURE.md` | Implemented components and data flow |
| `RISK_REGISTER.md` | Measured failures and remaining limitations |
| `LITERATURE.md` | Verified source and methodology evidence index, not the complete APA portfolio |
| `CLAUDE.md` / `.cursor/rules/` | Thin adapters that point back to the files above. `CLAUDE.md` serves the primary agent; the Cursor rule is optional |

GitHub is authoritative. Chat histories are not.

## Portable demo

Python 3.11+ is required. An EIA API key is not required to run the existing demo.

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev,demo]"
python -m streamlit run src/infralens/demo/app.py
```

Startup reads the committed holdout summary and any local cache files that are already present. It does not call the EIA API, train a model, or score the holdout.

The three-tab defense walkthrough, expected example values, and portable-mode limits are in [`docs/demo_walkthrough.md`](docs/demo_walkthrough.md).

## Local API and React frontend

The FastAPI adapter and the Vite app talk to each other on this machine. They do not use the retired public hosts. Install the API extra with the demo extra:

```bash
python -m pip install -e ".[dev,demo,api]"
INFRALENS_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173 \
  python -m uvicorn infralens.api.app:app
```

Uvicorn’s default listen address is `127.0.0.1:8000`. In another shell:

```bash
cd frontend
npm ci
npm run dev
```

Vite listens on port 5173 (`frontend/vite.config.ts`, `strictPort`). Open the same host you listed in `INFRALENS_CORS_ORIGINS`. `localhost` and `127.0.0.1` are different origins.

`frontend/src/api/client.ts` resolves an unset `VITE_API_BASE_URL` to `http://127.0.0.1:8000`. `frontend/.env.example` sets that same local origin. Copy it to `frontend/.env` only when the API is not on that address. An explicit empty value calls same-origin `/api`, which this package does not proxy.

Frontend checks, from `frontend/`: `npm test`, `npm run lint`, and `npm run build`. The non-holdout regression command is `python -m pytest tests --ignore=tests/test_final_holdout.py`. Do not run `python -m infralens.evaluation.final_holdout`.

### Portable mode and local full-data mode

Portable mode uses the committed summary `docs/final_eia_holdout_oneshot.json`. The FAIL banner and the typed annual-cost form still run. If any of the four gitignored caches below is missing, each missing chart or workbook stays unavailable.

Local full-data mode, with charts and PJM screening, needs all four files:

- `data/interim/eia_retail_sales_monthly_com_20260911T190524Z.parquet`
- `data/processed/final_holdout/final_holdout_cases.parquet`
- `data/raw/pjm/2025-load-report-tables.xlsx`
- `data/raw/pjm/2026-load-report-tables.xlsx`

Leave a missing file unavailable. Do not download a substitute and do not regenerate the final holdout. To preview portable mode while those files remain on disk, start with `INFRALENS_PORTABLE_PREVIEW=1`. That switch only hides the cache paths for the process.

## EIA ingestion and development

A new EIA extract is separate from the demo. Copy `.env.example` to `.env` and set `EIA_API_KEY` (register at https://www.eia.gov/opendata/register.php). Then run `python -m infralens.data.eia_ingest`. Only that ingestion path reads `EIA_API_KEY`.

Raw EIA JSON is written under `data/raw/eia/` and the matching interim Parquet under `data/interim/`. Both filenames share the same UTC retrieval timestamp. There is no mutable “latest” Parquet alias. API keys are never logged; echoed `api_key` fields are redacted before the raw file is saved.

Development checks already produced the frozen comparison: `python -m infralens.evaluation.backtest`, `linear`, `tree`, `intervals`, and `explain`. They are documented in `EVALUATION.md`. Demo startup leaves them unrun. Run tests with `pytest`. The final-holdout command above stays closed.

## Implemented stack

Python 3.11+ installable package in `src/infralens`. Core dependencies are pandas, NumPy, PyArrow, DuckDB, httpx, scikit-learn, Matplotlib, and python-dotenv. The `dev` extra adds pytest and Jupyter. The `demo` extra adds Streamlit and Altair. The HTTP client is httpx.

The repository includes EIA commercial retail-sales ingest, publication-lag-constrained development backtests (seasonal naive, Ridge, and a histogram-gradient-boosting comparison that lost on development MAE), state-specific absolute-residual intervals, origin-specific Ridge coefficient explanations, a deterministic annual electricity-cost identity, PJM 2025/2026 table screening parsed from workbook ZIP/XML, and the Streamlit historical-evaluation page.

Deferred or outside this package: XGBoost, SHAP, MLflow, and openpyxl. The portable API image recipe remains in [`docs/portable_deployment.md`](docs/portable_deployment.md). The hosted service that used it was decommissioned on 2026-11-03. MLflow remains deferred (`DECISIONS.md`, 2026-09-29). Explanations are the fitted linear identity: the intercept plus each feature's contribution. Nominal 80% interval coverage is the method's stated rate. The 75–85% holdout-coverage band was a diagnostic. The frozen holdout coverage is 0%.

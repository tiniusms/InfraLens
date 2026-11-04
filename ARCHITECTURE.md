# InfraLens architecture

This note describes the evaluation and Streamlit system implemented on `feat/pjm-screening-layer`, plus the later local FastAPI and React runtimes. `PROJECT_CONTEXT.md` sections 3, 7, and 12 still name the planned stack, including MLflow, SHAP, and XGBoost. Those three names are not a description of the running code. A portable Docker recipe does exist and is retained as a template.

## Current runtime and retired public deployment

Supported use is local. Nothing in the application source calls a hosted InfraLens service unless an operator sets that origin explicitly.

| Runtime | How it starts | What it uses |
| --- | --- | --- |
| Streamlit demo | `python -m streamlit run src/infralens/demo/app.py` after `pip install -e ".[dev,demo]"` | Committed holdout summary, and the four local caches when they exist. Sections 4–6 describe this page. |
| FastAPI adapter | `python -m uvicorn infralens.api.app:app` after `pip install -e ".[api]"` | Read-only routes under `/api/v1`: status, evaluation summary, EIA history, holdout, holdout cases, finance scenarios, PJM catalog, and PJM screen. Default listen address is `127.0.0.1:8000`. It does not train or score a model. |
| React frontend | `npm run dev` in `frontend/` | Vite on port 5173. `resolveApiBaseUrl` in `frontend/src/api/client.ts` returns `http://127.0.0.1:8000` when `VITE_API_BASE_URL` is unset. |

Host checks stay off unless `RENDER=true`, `RENDER_EXTERNAL_HOSTNAME`, or `INFRALENS_ALLOWED_HOSTS` is set. CORS stays an explicit allowlist in `INFRALENS_CORS_ORIGINS`. Local development sets that list to the Vite origins and leaves the Render variables unset.

The Vercel frontend, Render private API, and Cloudflare Tunnel checked on 2026-10-20 were decommissioned on 2026-11-03. `docs/public_release_validation.md` remains that October 20 record, merged in pull request #6 (`895b5368cb3729953df1218346b78b39bec948e4`). `docs/portable_deployment.md`, `Dockerfile`, `render.yaml`, `frontend/vercel.json`, and `deploy/` remain the redeployment template. They are not a running deployment. Shutdown facts are in `docs/infrastructure_decommission_2026_11_03.md`.

InfraLens supports a screening conversation for VA, PA, OH, MD, and NJ. It has two layers. The EIA layer evaluates a frozen 12-month-ahead commercial-price model against an availability-adjusted seasonal-naive baseline. The PJM layer shows one public zone-year vintage of summer peak, Table B-9, and Table B-9b. The finance form turns a stated cents-per-kWh price into an annual energy charge. The layers do not feed each other.

## 1. System boundary

Training geography is the user-facing PJM state set: VA, PA, OH, MD, and NJ. The price target is commercial average retail price, in cents/kWh, for the calendar month 12 months after a month-end forecast origin. That series is a public EIA proxy. It is not a data-center tariff.

PJM screening uses transmission-owner zones from the 2025 and 2026 Long-Term Load Forecast Tables workbooks. A zone is not a state. `src/infralens/screening/pjm_view.py` returns summer peak, the published 10-year growth decimal, B-9 `above_embedded_mw`, and B-9b `total_associated_mw` from one vintage. B-9 and B-9b stay on separate fields. Neither is labeled data-center demand. The view has no `state_id`, no risk score, and no allocation of MW onto an EIA state. The display-only zone/state overlap table in `docs/pjm_screening_schema.md` is not a join key.

`src/infralens/evaluation/features.py` excludes PJM fields and revenue. `src/infralens/finance/annual_cost.py` does not read screening rows.

## 2. Data and provenance

```text
EIA API (EIA_API_KEY, ingest only)
  src/infralens/data/eia_client.py
  data/raw/eia/retail_sales_monthly_com_<UTC stamp>.json
  src/infralens/data/eia_normalize.py
  src/infralens/data/availability.py          assumed_available_at = first day of month m+3
  data/interim/eia_retail_sales_monthly_com_<UTC stamp>.parquet

Frozen extract used by evaluation and the demo
  data/interim/eia_retail_sales_monthly_com_20260911T190524Z.parquet

Development and the one-shot holdout
  src/infralens/evaluation/backtest.py
  src/infralens/evaluation/features.py
  src/infralens/evaluation/linear.py
  src/infralens/evaluation/tree.py
  src/infralens/evaluation/intervals.py
  src/infralens/evaluation/explain.py         evaluation only; the demo does not call it
  src/infralens/evaluation/final_holdout.py   executed once; do not run again
  docs/final_eia_holdout_oneshot.json         committed summary

PJM 2025 and 2026 Tables workbooks (ZIP/XML, not openpyxl)
  src/infralens/screening/pjm_sources.py
  src/infralens/screening/pjm_b1.py           Table B1
  src/infralens/screening/pjm_adjustments.py  Table B-9 and Table B-9b
  src/infralens/screening/pjm_view.py         screen_zone_year

Demo
  src/infralens/demo/foundation.py
  src/infralens/demo/eia_views.py
  src/infralens/demo/pjm_screen.py
  src/infralens/finance/annual_cost.py
  src/infralens/demo/app.py
```

EIA ingest is `python -m infralens.data.eia_ingest`. `src/infralens/data/eia_client.py` reads `EIA_API_KEY` from the environment or `.env`, pages the retail-sales API with httpx, and redacts echoed keys before `src/infralens/data/eia_ingest.py` writes raw JSON. The matching interim Parquet uses the same UTC stamp. There is no mutable “latest” alias. The demo does not call this path and does not need an API key.

`assumed_available_at` is an InfraLens rule in `src/infralens/data/availability.py`: for observation month *m*, availability is the first day of month *m+3*. It is not an EIA publication timestamp. `EVALUATION.md` records the consequence: the backtest is a publication-lag-constrained current-vintage evaluation. Later revisions can already be inside the frozen extract. The observation `period` is not treated as the date a row became public.

The frozen evaluation extract is `eia_retail_sales_monthly_com_20260911T190524Z.parquet`.

PJM file-level dates live in `src/infralens/screening/pjm_sources.py`. The 2025 workbook is available 2025-01-24, with no revision date. The 2026 workbook was first listed 2026-01-14 and is available to InfraLens on 2026-02-06, the file-level revision used for the stored Tables workbook. `src/infralens/screening/pjm_b1.py` opens each `.xlsx` as a ZIP and reads sheet XML with `xml.etree`. `src/infralens/screening/pjm_adjustments.py` uses that same sheet reader for B-9 and B-9b. The 2024 revised PDF is not parsed. `docs/pjm_ltlf_inventory.md` keeps the inventory of vintages that are outside this code.

On the demo, `retrieved_at` for those workbooks is the later local file-creation time of the two cached files (`src/infralens/demo/pjm_screen.py`). That timestamp is not a PJM publication date. If the creation time cannot be read, the page does not invent one.

The committed holdout summary is `docs/final_eia_holdout_oneshot.json`. These four caches are gitignored. Full charts and PJM screening need all four:

- `data/interim/eia_retail_sales_monthly_com_20260911T190524Z.parquet`
- `data/processed/final_holdout/final_holdout_cases.parquet`
- `data/raw/pjm/2025-load-report-tables.xlsx`
- `data/raw/pjm/2026-load-report-tables.xlsx`

`data/processed/final_holdout/final_holdout_summary.json` is the gitignored runner output. The demo banner reads the committed JSON, not that local copy. A missing cache stays missing. The page does not download a substitute and does not call `python -m infralens.evaluation.final_holdout`.

## 3. Forecast evaluation

The seasonal-naive baseline is `availability_adjusted_seasonal_naive` in `src/infralens/evaluation/baseline.py`. At an origin, the analog is the latest same calendar month whose `assumed_available_at` is already on or before that origin. An unavailable t-12 is not used. The target month is 12 months after the origin month. Development reproduction is `python -m infralens.evaluation.backtest`.

Features are frozen as `eia_commercial_price_v1` in `src/infralens/evaluation/selection.py`: `price_latest`, `price_same_month`, `price_yoy_change`, `price_trail12_mean`, `sales_latest`, `sales_yoy_change`, `state_id`, and `target_calendar_month`.

Ridge lives in `src/infralens/evaluation/linear.py`. At each origin the last 12 eligible training origins choose the penalty. The grid is `0.01, 0.1, 1, 10, 100, 1000`. Ties keep the larger penalty. Scaler, one-hot encoder, and Ridge (`solver="cholesky"`) are then refit on eligible pre-origin rows. Training labels must be available at the origin, and their target month must be before 2025-07. Reproduce the development run with `python -m infralens.evaluation.linear`.

Histogram gradient boosting lives in `src/infralens/evaluation/tree.py` (`HistGradientBoostingRegressor`). On the 1,145 common development cases, `EVALUATION.md` records Ridge MAE 0.7075 ¢/kWh, paired seasonal-naive MAE 0.7997 ¢/kWh, and tree MAE 0.7831 ¢/kWh. The 2026-09-29 decision selected Ridge. The tree result is negative evidence. That comparison is not the final-holdout gate.

Intervals are state-specific absolute residual bands in `src/infralens/evaluation/intervals.py`. The nominal rate is 80 percent: the half-width is the order statistic `k = ceil((n + 1) * 4 / 5)`, and the band is withheld when fewer than 24 earlier residuals exist for that state. This is not a second model. Development empirical coverage was 80.10%.

Coefficient explanations are `explain_prediction` in `src/infralens/evaluation/explain.py`. For one stored Ridge prediction they return the intercept plus each transformed feature's contribution. `python -m infralens.evaluation.explain` prints the development summary. The function can explain a stored prediction after the holdout without changing the score. `src/infralens/demo/app.py` does not import or call it, so explanations are not a demo tab or control.

The only final-holdout command is `python -m infralens.evaluation.final_holdout`. It accepts no options. It was executed once on 2026-10-04 from runner commit `ee5bcf6d541a1b15822f705e4099320f6f05dc32`. Do not run it again.

`EVALUATION.md`, “Final holdout result (one-shot, 2026-10-04),” records the primary criterion as **FAIL**. Ridge MAE was 2.638473 ¢/kWh. Paired seasonal-naive MAE was 2.613667 ¢/kWh. Relative improvement was −0.9491%. The primary gate, implemented as `PRIMARY_RELATIVE_IMPROVEMENT = 0.10`, requires that ratio to be at least +10% on the same 60 cases (target months 2025-07 through 2026-06). State MAE is descriptive and does not change the gate.

Empirical interval coverage on that holdout was 0.0% overall and in every state. The 75–85% band is a diagnostic for the nominal 80% interval. It is not the pass/fail rule, and the 0.0% result is not a reason to retune the interval or the Ridge fit. `docs/final_eia_holdout_oneshot.json` stores the same result at full precision (`ridge_mae` 2.6384726503825626, `paired_baseline_mae` 2.6136666666666666, `mae_improvement_percent` -0.9490875034777213, `interval_coverage` 0.0, `primary_criterion` `FAIL`). The rounded figures above are the `EVALUATION.md` quotation.

Ridge is the development-selected candidate. It failed the final criterion. The demo shows that closed historical evaluation. It does not present a validated production forecast.

Post-hoc notes in `docs/final_eia_holdout_posthoc_analysis.md` and `docs/final_eia_holdout_external_evidence.md` describe the scored cases. They do not rescore them. `scripts/describe_final_holdout_errors.py` reprints counts from the local case file and does not call the holdout runner.

## 4. Streamlit execution

Launch from the repository root, after `python -m pip install -e ".[dev,demo]"`:

```bash
python -m streamlit run src/infralens/demo/app.py
```

`src/infralens/demo/app.py` keeps one page and three tabs:

| Tab | What it reads | What the user sets |
| --- | --- | --- |
| EIA history and closed holdout | Price-history Parquet and holdout-case Parquet | State, VA / PA / OH / MD / NJ |
| Financial scenarios | Committed summary always; holdout cases only when that Parquet is present | IT capacity MW, PUE, utilization, hours, and two prices |
| PJM infrastructure screening | The two local Tables workbooks | Zone, forecast year, as-of date |

The FAIL banner from `load_holdout_banner` stays above the tabs. It reads `docs/final_eia_holdout_oneshot.json`. History and the closed-holdout chart are Altair marks in `src/infralens/demo/eia_views.py`. History is observed commercial price. The holdout chart plots actual, Ridge, and seasonal naive by target month, with the stored residual band. Forecast origins stay in the caption. Those lines are closed predictions with actuals, not a forward forecast.

`assess_artifacts` in `src/infralens/demo/foundation.py` sets `local_full_data` only when all four gitignored files exist. Otherwise the mode is `portable_summary`. In portable mode the banner and the typed cost form still run. Each missing chart or workbook is named unavailable. A typed price remains available. The “Closed holdout Ridge prediction” choice appears only when the case file is present. `INFRALENS_PORTABLE_PREVIEW=1` points the four cache paths at names that are not on disk, so the page can be reviewed without moving local files. The committed summary stays visible.

Price sources on the form are `typed_hypothetical` and, when cases exist, `holdout_ridge`. A typed price is a hypothetical energy price. A holdout Ridge price is filled from the frozen case and sets `model_derived_eia_price` automatically. The page does not let the user type a number and label it as Ridge.

Example values, provenance lines, and the defense sequence are in `docs/demo_walkthrough.md`.

## 5. Finance

`annual_electricity_cost` and `compare_price_scenarios` in `src/infralens/finance/annual_cost.py` use `Decimal`.

```text
facility average demand MW = IT capacity MW × utilization × PUE
annual consumption kWh     = facility average demand MW × 1000 × operating hours
annual electricity cost USD = annual consumption kWh × cents/kWh / 100
```

Units are MW, kWh, cents/kWh, and USD. Hours default to 8760. Any other positive hour count is a scenario assumption, not a calendar lookup. PUE must be at least 1. `compare_price_scenarios` holds the load fixed and applies each named price. `cost_difference_vs_baseline_usd` is that scenario's annual cost minus the baseline scenario's annual cost. The baseline difference is zero. Scenarios are not averaged.

The checked example is 50 MW IT, PUE 1.30, utilization 0.80, 8760 hours, and 12 cents/kWh: demand 52 MW, consumption 455,520,000 kWh, and annual cost $54,662,400.

A holdout Ridge selection sets `model_derived_eia_price=True`. The finance module then attaches `EIA_MODEL_PRICE_WARNING` and does not change the arithmetic:

> This price is a model-derived EIA scenario, not a validated investment forecast. The frozen 60-case holdout primary criterion is FAIL. Both Ridge and the seasonal-naive baseline systematically underpredicted. Empirical interval coverage was 0%.

A typed price does not carry that warning. The calculator does not add demand charges, a tariff, a hedge, a tax, a PPA, a network charge, or a PJM capacity price. It does not discount multi-year cash flows. Identities and the checked example are also in `docs/finance.md`.

## 6. Implemented dependencies, non-goals, and exclusions

`pyproject.toml` requires Python 3.11+. Modules import pandas, NumPy, httpx, scikit-learn, and python-dotenv. NumPy is imported by the evaluation modules. httpx and python-dotenv are the EIA client. scikit-learn supplies Ridge and `HistGradientBoostingRegressor`. Parquet I/O calls pandas `read_parquet` and `to_parquet` without an `engine` argument. PyArrow is the declared dependency for that path. No module imports PyArrow by name.

DuckDB `>=1.1` and Matplotlib `>=3.9` are declared core dependencies. No module under `src/infralens/` imports either of them. `data/README.md` says processed tables may be queried through DuckDB where practical. That query path is not implemented. Demo charts are Altair, from the `demo` extra, together with Streamlit. The `dev` extra is pytest and Jupyter.

Parsing the PJM workbooks uses the Python standard library (`zipfile` and `xml.etree`). openpyxl is not a dependency and is not imported.

Outside this implementation:

- MLflow, SHAP, and XGBoost. MLflow remains deferred in `DECISIONS.md` (2026-09-29) and `TASKS.md`. The Docker recipe in `Dockerfile` is a retained local and redeploy template. It is not a running public service after the 2026-11-03 retirement.
- A tariff engine, a discounted cash flow, a risk score, and an EIA–PJM geographic join.
- The 2024 PDF parser listed as a later slice in `TASKS.md`.
- A forward production forecast. The holdout command stays closed.

`PROJECT_CONTEXT.md` remains the statement of planned scope. This file does not replace it.

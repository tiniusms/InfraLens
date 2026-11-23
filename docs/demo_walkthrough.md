# Streamlit demonstration walkthrough

The page is a historical evaluation and infrastructure-screening prototype. It is not a live production forecast, an interconnection study, or an investment recommendation.

## Launch

From the repository root, with the project virtual environment and the `demo` extra installed (`python -m pip install -e ".[dev,demo]" -c requirements-api.txt`):

```bash
python -m streamlit run src/infralens/demo/app.py
```

Startup reads local files and the committed holdout summary. It does not call the EIA API, train a model, or run `python -m infralens.evaluation.final_holdout`. Do not run that holdout command again.

The frozen primary-criterion banner stays above all three tabs: Ridge MAE 2.6384726503825626 ¢/kWh, seasonal-naive MAE 2.6136666666666666 ¢/kWh, empirical interval coverage 0.0. The result is FAIL.

## Optional local files

Full charts and PJM screening need files that are not in git:

- `data/interim/eia_retail_sales_monthly_com_20260911T190524Z.parquet`
- `data/processed/final_holdout/final_holdout_cases.parquet`
- `data/raw/pjm/2025-load-report-tables.xlsx`
- `data/raw/pjm/2026-load-report-tables.xlsx`

The committed summary `docs/final_eia_holdout_oneshot.json` is always required. If any of the four caches is missing, the page stays in portable mode: the FAIL banner and the typed cost form still run, and each missing chart or workbook is named as unavailable. Do not download a substitute or rerun the holdout to fill those gaps.

To preview that mode without moving the local files, start with `INFRALENS_PORTABLE_PREVIEW=1`. That switch only hides the cache paths for the process.

## EIA history and closed holdout

State selectors use the codes VA, PA, OH, MD, and NJ. PA is Pennsylvania.

The history chart is the observed commercial average retail price in cents/kWh. For one state the axis runs 2001-01 through 2026-06 (306 months). The caption records the frozen extract, which holds 1,530 state-months. The line is observed history, not a model prediction.

The holdout chart plots actual, Ridge, and seasonal naive by target month, 2025-07 through 2026-06. Forecast origins stay in the provenance line. The band is the stored Ridge residual interval, nominal 80%, with empirical coverage on this closed holdout of 0%. It is not a forward-looking forecast interval.

## Financial scenarios

Defaults: IT capacity 50 MW, PUE 1.30, utilization 0.80, 8,760 hours, typed baseline 12 cents/kWh, typed comparison 10 cents/kWh.

Calculate annual cost:

- demand 52 MW
- consumption 455,520,000 kWh
- baseline annual cost $54,662,400
- comparison difference versus baseline −$9,110,400

Both rows are labeled typed hypothetical energy prices.

Choosing “Closed holdout Ridge prediction” fills the price from a frozen case and sets the model-derived flag. The page then shows:

> This price is a model-derived EIA scenario, not a validated investment forecast. The frozen 60-case holdout primary criterion is FAIL. Both Ridge and the seasonal-naive baseline systematically underpredicted. Empirical interval coverage was 0%.

A typed price does not carry that warning. In portable mode the holdout case file is absent, so only typed prices are offered.

## PJM infrastructure screening

Zone AEP, forecast year 2026. Pick the as-of date in the date control and leave the control so the page reruns.

| As-of date | What the page shows |
| --- | --- |
| 2025-06-30 | Vintage 2025, original release 2025-01-24, no revision. Summer peak 25,788 MW. B-9 3,621 MW. B-9b 3,936 MW. |
| 2026-02-06 | Vintage 2026, original release 2026-01-14, revision 2026-02-06. Summer peak 24,635 MW. B-9 1,913 MW. B-9b 2,699 MW. |
| 2025-01-23 | Unpublished. No MW figures, and the measures are not shown as zero. |

B-9 and B-9b stay separate. Neither is isolated data-center MW. Zones are not US states: the tab does not join a zone to an EIA state, allocate MW, or rank locations.

Source lines link to the official PJM Tables workbook for the selected vintage. `retrieved_at` is each workbook's recorded retrieval time from `data/manifest.json`: a 2026-11-20 re-download of a byte-identical file. The original download time was not recorded. It is not a PJM publication date.

## Five-minute defense sequence

1. Start the app and read the FAIL banner above the tabs, including both MAEs and 0% coverage.
2. On the EIA tab, select PA. Show the observed price line from 2001-01 through 2026-06, then the closed holdout from 2025-07 through 2026-06 with the nominal-80% interval labeled at 0% empirical coverage.
3. On Financial scenarios, calculate the 50 MW typed example and read 455,520,000 kWh, $54,662,400, and the −$9,110,400 comparison.
4. Switch the baseline to one frozen holdout Ridge case and read the model-derived warning.
5. On PJM infrastructure screening, keep AEP and forecast year 2026. Show 2026-02-06 (vintage 2026: 24,635 / 1,913 / 2,699 MW), then 2025-06-30 (vintage 2025: 25,788 / 3,621 / 3,936 MW). Point to the zone warning, the large-load warning, the source URL, and the `retrieved_at` caveat (a recorded re-download of a byte-identical file, not the original download time and not a PJM publication date).

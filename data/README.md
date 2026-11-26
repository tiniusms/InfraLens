# Data layout

- `raw/` — immutable downloads and original extracts. Do not overwrite. EIA JSON under `raw/eia/`; public PJM LTLF PDF/XLSX under `raw/pjm/` (gitignored).
- `interim/` — cleaned or joined tables still in progress.
- `processed/` — analysis-ready Parquet (and similar) artifacts. Slice 1 PJM output belongs under `processed/pjm/` and stays gitignored.

Read and write processed tables as Parquet with pandas (PyArrow engine). Track publication / availability dates so features never use information that would not have been available at the prediction date.

## Distribution policy

`data/distribution_policy.json` classifies every `data/manifest.json` entry, and CI enforces it (`DECISIONS.md`, 2026-11-23). Local-only files stay out of git. The committed entries are the frozen holdout summary and the synthetic EIA test fixture.

- **EIA:** EIA states that U.S. government publications are in the public domain and asks for an acknowledgment with the publication date. Sources, retrieved 2026-11-23: [Copyrights and Reuse](https://www.eia.gov/about/copyrights_reuse.php) and [API Terms of Service](https://www.eia.gov/opendata/terms-of-service.php). The local EIA extract still stays out of git. A re-fetch returns EIA's current vintage, not these frozen bytes.
- **PJM:** the two Tables workbooks stay local because PJM's published terms give no clear redistribution right. Do not commit the workbooks or excerpts without written PJM permission. Sources, retrieved 2026-11-23: [PJM Legal](https://www.pjm.com/m/About-PJM/Legal) and the [load forecast page](https://www.pjm.com/planning/resource-adequacy-planning/load-forecast-dev-process).

This is an engineering reading of the published terms, not legal advice.

# Data layout

- `raw/` — immutable downloads and original extracts. Do not overwrite. EIA JSON under `raw/eia/`; public PJM LTLF PDF/XLSX under `raw/pjm/` (gitignored).
- `interim/` — cleaned or joined tables still in progress.
- `processed/` — analysis-ready Parquet (and similar) artifacts. Slice 1 PJM output belongs under `processed/pjm/` and stays gitignored.

Query processed tables through DuckDB where practical. Track publication / availability dates so features never use information that would not have been available at the prediction date.

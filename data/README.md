# Data layout

- `raw/` — immutable downloads and original extracts. Do not overwrite.
- `interim/` — cleaned or joined tables still in progress.
- `processed/` — analysis-ready Parquet (and similar) artifacts.

Query processed tables through DuckDB where practical. Track publication / availability dates so features never use information that would not have been available at the prediction date.

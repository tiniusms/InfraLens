"""Run the EIA retail-sales feasibility ingest (retrieve, archive, normalize)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from infralens.data import (
    EIA_START_PERIOD,
    USER_FACING_STATES,
    repository_root,
)
from infralens.data.eia_client import fetch_retail_sales_pages, write_raw_eia_artifact
from infralens.data.eia_normalize import ValidationReport, normalize_retail_sales


@dataclass(frozen=True)
class IngestResult:
    raw_path: Path
    parquet_path: Path
    validation: ValidationReport


def run_eia_retail_sales_ingest(
    *,
    project_root: Path | None = None,
    states: tuple[str, ...] = USER_FACING_STATES,
    start: str = EIA_START_PERIOD,
) -> IngestResult:
    """Fetch EIA retail sales and write timestamp-matched raw JSON and Parquet."""
    root = project_root or repository_root()
    retrieved_at = datetime.now(timezone.utc)
    stamp = retrieved_at.strftime("%Y%m%dT%H%M%SZ")
    raw_path = root / "data" / "raw" / "eia" / f"retail_sales_monthly_com_{stamp}.json"
    parquet_path = (
        root / "data" / "interim" / f"eia_retail_sales_monthly_com_{stamp}.parquet"
    )

    pages = fetch_retail_sales_pages(states=states, start=start)
    write_raw_eia_artifact(
        pages,
        raw_path,
        retrieved_at=retrieved_at,
        states=states,
        start=start,
    )
    frame, report = normalize_retail_sales(
        pages,
        retrieved_at=retrieved_at,
        expected_states=states,
        require_all_expected_states=True,
    )
    if parquet_path.exists():
        raise FileExistsError(f"Interim EIA artifact already exists: {parquet_path}")
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(parquet_path, index=False)
    return IngestResult(raw_path=raw_path, parquet_path=parquet_path, validation=report)


def _print_report(result: IngestResult) -> None:
    report = result.validation
    print(f"row_count: {report.row_count}")
    print(f"earliest_period: {report.earliest_period}")
    print(f"latest_period: {report.latest_period}")
    print("rows_by_state:")
    for state, count in report.rows_by_state.items():
        print(f"  {state}: {count}")
    print("missing_value_counts:")
    for column, count in report.missing_value_counts.items():
        print(f"  {column}: {count}")
    print(f"duplicate_count: {report.duplicate_count}")
    print(f"raw_path: {result.raw_path}")
    print(f"parquet_path: {result.parquet_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest EIA monthly commercial retail electricity sales."
    )
    parser.parse_args(argv)
    result = run_eia_retail_sales_ingest()
    _print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

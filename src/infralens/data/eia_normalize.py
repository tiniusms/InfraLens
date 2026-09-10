"""Normalize and validate EIA retail-sales API pages into a table."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from infralens.data import (
    EIA_DATA_COLUMNS,
    EIA_FREQUENCY,
    EIA_RETAIL_SALES_DATA_URL,
    EIA_RETAIL_SALES_ROUTE,
    EIA_SECTOR_ID,
    USER_FACING_STATES,
)

PERIOD_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


class EiaNormalizationError(ValueError):
    """Raised when EIA observations fail structural validation."""


@dataclass(frozen=True)
class ValidationReport:
    row_count: int
    earliest_period: str | None
    latest_period: str | None
    rows_by_state: dict[str, int]
    missing_value_counts: dict[str, int]
    duplicate_count: int


def collect_observations(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract ``response.data`` rows from one or more EIA page objects."""
    rows: list[dict[str, Any]] = []
    for page in pages:
        body = page.get("response") or {}
        data = body.get("data") or []
        if not isinstance(data, list):
            raise EiaNormalizationError("EIA page response.data must be a list.")
        rows.extend(data)
    return rows


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if pd.isna(value):
            return None
        return float(value)
    text = str(value).strip()
    if text == "" or text == ".":
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise EiaNormalizationError(f"Non-numeric EIA measure: {text!r}.") from exc


def normalize_retail_sales(
    pages: list[dict[str, Any]],
    *,
    retrieved_at: datetime,
    expected_states: tuple[str, ...] = USER_FACING_STATES,
    require_all_expected_states: bool = True,
) -> tuple[pd.DataFrame, ValidationReport]:
    """Convert EIA pages to a typed table and validate the feasibility slice."""
    observations = collect_observations(pages)
    records: list[dict[str, Any]] = []
    retrieved_iso = retrieved_at.astimezone(timezone.utc).isoformat()
    for raw in observations:
        if not isinstance(raw, dict):
            raise EiaNormalizationError("Each EIA observation must be an object.")
        period = str(raw.get("period", "")).strip()
        if not PERIOD_PATTERN.match(period):
            raise EiaNormalizationError(f"Period is not monthly YYYY-MM: {period!r}.")
        state_id = str(raw.get("stateid", "")).strip().upper()
        sector_id = str(raw.get("sectorid", "")).strip().upper()
        year, month = period.split("-")
        record = {
            "period": period,
            "period_start": pd.Timestamp(year=int(year), month=int(month), day=1),
            "state_id": state_id,
            "state_name": raw.get("stateDescription"),
            "sector_id": sector_id,
            "sector_name": raw.get("sectorName"),
            "price_cents_per_kwh": _to_float(raw.get("price")),
            "sales_million_kwh": _to_float(raw.get("sales")),
            "revenue_million_usd": _to_float(raw.get("revenue")),
            "price_units": raw.get("price-units"),
            "sales_units": raw.get("sales-units"),
            "revenue_units": raw.get("revenue-units"),
            "retrieved_at": retrieved_iso,
            "source": "U.S. Energy Information Administration",
            "source_route": EIA_RETAIL_SALES_ROUTE,
            "source_url": EIA_RETAIL_SALES_DATA_URL,
            "frequency": EIA_FREQUENCY,
        }
        records.append(record)

    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        raise EiaNormalizationError("EIA retail-sales response contained no observations.")

    report = validate_retail_sales(
        frame,
        expected_states=expected_states,
        require_all_expected_states=require_all_expected_states,
    )
    return frame.sort_values(["period", "state_id"]).reset_index(drop=True), report


def validate_retail_sales(
    frame: pd.DataFrame,
    *,
    expected_states: tuple[str, ...] = USER_FACING_STATES,
    require_all_expected_states: bool = True,
) -> ValidationReport:
    """Check states, monthly periods, numeric measures, duplicates, and missingness."""
    expected = {state.upper() for state in expected_states}
    observed_states = set(frame["state_id"].dropna().astype(str).str.upper())
    unexpected = sorted(observed_states - expected)
    if unexpected:
        raise EiaNormalizationError(f"Unexpected state_id values: {unexpected}.")
    if require_all_expected_states:
        missing_states = sorted(expected - observed_states)
        if missing_states:
            raise EiaNormalizationError(f"Missing expected state_id values: {missing_states}.")

    if not frame["period"].map(lambda value: bool(PERIOD_PATTERN.match(str(value)))).all():
        raise EiaNormalizationError("One or more periods are not monthly YYYY-MM.")

    bad_sector = frame.loc[frame["sector_id"] != EIA_SECTOR_ID]
    if not bad_sector.empty:
        raise EiaNormalizationError("Observations include a sector other than COM.")

    key_cols = ["state_id", "period", "sector_id"]
    duplicate_count = int(frame.duplicated(subset=key_cols).sum())
    if duplicate_count:
        raise EiaNormalizationError(
            f"Duplicate state/period/sector rows: {duplicate_count}."
        )

    identity_missing = bool(frame[key_cols].isna().any().any())
    if identity_missing:
        raise EiaNormalizationError("Missing state_id, period, or sector_id values.")

    measure_map = {
        "price": "price_cents_per_kwh",
        "sales": "sales_million_kwh",
        "revenue": "revenue_million_usd",
    }
    for column in measure_map.values():
        series = frame[column]
        if not pd.api.types.is_numeric_dtype(series):
            raise EiaNormalizationError(f"Column {column} must be numeric.")

    missing_value_counts = {
        column: int(frame[column].isna().sum())
        for column in [
            *key_cols,
            *measure_map.values(),
            "period_start",
            "retrieved_at",
            "source",
            "source_route",
        ]
    }
    rows_by_state = {
        state: int((frame["state_id"] == state).sum())
        for state in sorted(observed_states)
    }
    return ValidationReport(
        row_count=int(len(frame)),
        earliest_period=str(frame["period"].min()),
        latest_period=str(frame["period"].max()),
        rows_by_state=rows_by_state,
        missing_value_counts=missing_value_counts,
        duplicate_count=0,
    )

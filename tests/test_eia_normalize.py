"""Tests for EIA retail-sales parsing, redaction, and validation (no live API)."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from infralens.data.eia_client import redact_secrets, write_raw_eia_artifact
from infralens.data.eia_normalize import (
    EiaNormalizationError,
    collect_observations,
    normalize_retail_sales,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "eia_retail_sales_sample.json"
RETRIEVED_AT = datetime(2026, 9, 10, 2, 0, tzinfo=timezone.utc)
EXPECTED = ("VA", "PA")


def _load_pages() -> list[dict]:
    return [json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))]


def test_collect_observations_from_fixture() -> None:
    rows = collect_observations(_load_pages())
    assert len(rows) == 3
    assert {row["stateid"] for row in rows} == {"VA", "PA"}


def test_normalize_fixture_types_and_metadata() -> None:
    frame, report = normalize_retail_sales(
        _load_pages(),
        retrieved_at=RETRIEVED_AT,
        expected_states=EXPECTED,
        require_all_expected_states=True,
    )
    assert report.row_count == 3
    assert report.earliest_period == "2001-01"
    assert report.latest_period == "2001-02"
    assert report.rows_by_state == {"PA": 1, "VA": 2}
    assert report.duplicate_count == 0
    assert report.missing_value_counts["price_cents_per_kwh"] == 1
    assert report.missing_value_counts["sales_million_kwh"] == 0
    assert frame["price_cents_per_kwh"].dtype.kind == "f"
    assert str(frame.loc[frame["period"] == "2001-02", "price_cents_per_kwh"].iloc[0]) == "nan"
    assert (frame["retrieved_at"] == "2026-09-10T02:00:00+00:00").all()
    assert (frame["source_route"] == "/v2/electricity/retail-sales/data/").all()
    assert (frame["frequency"] == "monthly").all()
    assert "SECRET_SHOULD_NOT_APPEAR" not in frame.to_csv(index=False)


def test_redact_secrets_removes_api_key() -> None:
    redacted = redact_secrets(_load_pages()[0])
    dumped = json.dumps(redacted)
    assert "SECRET_SHOULD_NOT_APPEAR" not in dumped
    assert redacted["request"]["params"]["api_key"] == "<redacted>"


def test_write_raw_artifact_is_redacted_and_immutable(tmp_path: Path) -> None:
    destination = tmp_path / "raw.json"
    write_raw_eia_artifact(
        _load_pages(),
        destination,
        retrieved_at=RETRIEVED_AT,
        states=EXPECTED,
        start="2001-01",
    )
    text = destination.read_text(encoding="utf-8")
    assert "SECRET_SHOULD_NOT_APPEAR" not in text
    assert "<redacted>" in text
    with pytest.raises(FileExistsError):
        write_raw_eia_artifact(
            _load_pages(),
            destination,
            retrieved_at=RETRIEVED_AT,
            states=EXPECTED,
            start="2001-01",
        )


def test_rejects_unexpected_state() -> None:
    pages = _load_pages()
    pages[0]["response"]["data"][0]["stateid"] = "TX"
    with pytest.raises(EiaNormalizationError, match="Unexpected state_id"):
        normalize_retail_sales(
            pages,
            retrieved_at=RETRIEVED_AT,
            expected_states=EXPECTED,
        )


def test_rejects_missing_expected_state() -> None:
    with pytest.raises(EiaNormalizationError, match="Missing expected state_id"):
        normalize_retail_sales(
            _load_pages(),
            retrieved_at=RETRIEVED_AT,
            expected_states=("VA", "PA", "OH"),
            require_all_expected_states=True,
        )


def test_rejects_non_monthly_period() -> None:
    pages = _load_pages()
    pages[0]["response"]["data"][0]["period"] = "2001"
    with pytest.raises(EiaNormalizationError, match="monthly YYYY-MM"):
        normalize_retail_sales(
            pages,
            retrieved_at=RETRIEVED_AT,
            expected_states=EXPECTED,
        )


def test_rejects_non_numeric_price() -> None:
    pages = _load_pages()
    pages[0]["response"]["data"][0]["price"] = "not-a-number"
    with pytest.raises(EiaNormalizationError, match="Non-numeric"):
        normalize_retail_sales(
            pages,
            retrieved_at=RETRIEVED_AT,
            expected_states=EXPECTED,
        )


def test_rejects_duplicates() -> None:
    pages = _load_pages()
    extra = copy.deepcopy(pages[0]["response"]["data"][0])
    pages[0]["response"]["data"].append(extra)
    with pytest.raises(EiaNormalizationError, match="Duplicate"):
        normalize_retail_sales(
            pages,
            retrieved_at=RETRIEVED_AT,
            expected_states=EXPECTED,
        )

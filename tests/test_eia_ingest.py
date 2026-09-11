"""Orchestration tests for EIA ingest (mocked fetch; no live API)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from infralens.data.eia_ingest import run_eia_retail_sales_ingest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "eia_retail_sales_sample.json"
EXPECTED_STATES = ("VA", "PA")
EXPECTED_START = "2001-01"


def test_run_ingest_writes_timestamp_matched_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = [json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))]
    captured: dict[str, object] = {}

    def fake_fetch(*, states: tuple[str, ...], start: str) -> list[dict]:
        captured["states"] = states
        captured["start"] = start
        return pages

    monkeypatch.setattr(
        "infralens.data.eia_ingest.fetch_retail_sales_pages",
        fake_fetch,
    )

    result = run_eia_retail_sales_ingest(
        project_root=tmp_path,
        states=EXPECTED_STATES,
        start=EXPECTED_START,
    )

    assert captured["states"] == EXPECTED_STATES
    assert captured["start"] == EXPECTED_START

    raw_files = list((tmp_path / "data" / "raw" / "eia").glob("*.json"))
    parquet_files = list((tmp_path / "data" / "interim").glob("*.parquet"))
    assert len(raw_files) == 1
    assert len(parquet_files) == 1
    assert result.raw_path == raw_files[0]
    assert result.parquet_path == parquet_files[0]

    raw_stamp = result.raw_path.name.removeprefix(
        "retail_sales_monthly_com_"
    ).removesuffix(".json")
    parquet_stamp = result.parquet_path.name.removeprefix(
        "eia_retail_sales_monthly_com_"
    ).removesuffix(".parquet")
    assert raw_stamp == parquet_stamp
    assert raw_stamp.endswith("Z")

    frame = pd.read_parquet(result.parquet_path)
    assert len(frame) == result.validation.row_count == 3
    assert result.validation.rows_by_state == {"PA": 1, "VA": 2}
    assert result.validation.duplicate_count == 0
    assert set(frame["state_id"]) == {"PA", "VA"}
    assert "SECRET_SHOULD_NOT_APPEAR" not in result.raw_path.read_text(encoding="utf-8")

"""Point-in-time tests for the PJM zone-year screening view."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from data_cache_skips import skip_missing_cache
from infralens.screening.pjm_adjustments import (
    ABOVE_EMBEDDED_MW,
    TOTAL_ASSOCIATED_MW,
    AdjustmentRow,
    load_slice2_adjustments,
)
from infralens.screening.pjm_b1 import B1Row, load_slice1_tables
from infralens.screening.pjm_sources import TABLE_B1_SOURCES, source_for_vintage
from infralens.screening.pjm_view import (
    PjmViewError,
    compare_zone_year_vintages,
    screen_zone_year,
)

_RAW = Path("data/raw/pjm")
_RETRIEVED = datetime(2026, 10, 14, 20, 0)


def test_latest_complete_vintage_is_selected_without_blending() -> None:
    b1, adjustments = _pair()
    early = screen_zone_year(b1, adjustments, "AEP", 2026, "2025-06-30")
    assert early.available is True
    assert early.ltlf_vintage_year == 2025
    assert early.summer_peak_mw == 25788.0
    assert early.above_embedded_mw == 3621.0
    assert early.total_associated_mw == 3936.0
    assert early.summer_peak_mw != 24635.0

    on_revision = screen_zone_year(b1, adjustments, "AEP", 2026, date(2026, 2, 6))
    assert on_revision.ltlf_vintage_year == 2026
    assert on_revision.summer_peak_mw == 24635.0
    assert on_revision.summer_peak_10yr_cagr == 0.0525293343
    assert on_revision.above_embedded_mw == 1913.0
    assert on_revision.total_associated_mw == 2699.0
    assert on_revision.original_release_date == date(2026, 1, 14)
    assert on_revision.revision_date == date(2026, 2, 6)
    assert on_revision.vintage_available_at == date(2026, 2, 6)
    assert on_revision.above_embedded_mw + on_revision.total_associated_mw not in {
        on_revision.summer_peak_mw,
        on_revision.above_embedded_mw,
        on_revision.total_associated_mw,
    }
    assert screen_zone_year(b1, adjustments, "AEP", 2026, "2026-01-14").ltlf_vintage_year == 2025
    assert screen_zone_year(b1, adjustments, "AEP", 2026, "2025-01-24").ltlf_vintage_year == 2025


def test_unpublished_vintage_is_distinct_from_a_malformed_record() -> None:
    b1, adjustments = _pair()
    missing = screen_zone_year(b1, adjustments, "AEP", 2026, "2025-01-23")
    assert missing.available is False
    assert missing.summer_peak_mw is None
    assert missing.above_embedded_mw is None
    assert missing.total_associated_mw is None
    assert missing.ltlf_vintage_year is None
    assert missing.source_urls == ()
    assert missing.unavailable_reason is not None
    assert "public" in missing.unavailable_reason
    before_2024_parser = screen_zone_year(b1, adjustments, "AEP", 2026, "2024-06-30")
    assert before_2024_parser.available is False
    assert compare_zone_year_vintages(b1, adjustments, "AEP", 2026, "2025-01-23") == ()
    with pytest.raises(PjmViewError, match="as_of_date"):
        screen_zone_year(b1, adjustments, "AEP", 2026, "2026/02/06")
    with pytest.raises(PjmViewError, match="vintage_available_at"):
        screen_zone_year(
            [replace(b1[0], vintage_available_at=None)],
            adjustments,
            "AEP",
            2026,
            "2026-02-06",
        )


def test_public_incomplete_vintage_does_not_fall_back() -> None:
    b1, adjustments = _pair()
    kept = [
        row
        for row in adjustments
        if not (
            row.ltlf_vintage_year == 2026
            and row.pjm_zone == "AEP"
            and row.forecast_year == 2026
            and row.adjustment_measure == TOTAL_ASSOCIATED_MW
        )
    ]
    with pytest.raises(PjmViewError, match="does not have complete"):
        screen_zone_year(b1, kept, "AEP", 2026, "2026-02-06")
    with pytest.raises(PjmViewError, match="does not have complete"):
        compare_zone_year_vintages(b1, kept, "AEP", 2026, "2026-02-06")
    # The unpublished 2026 hole does not block the 2025 vintage.
    assert screen_zone_year(b1, kept, "AEP", 2026, "2025-06-30").ltlf_vintage_year == 2025
    older_hole = [
        row
        for row in adjustments
        if not (
            row.ltlf_vintage_year == 2025
            and row.pjm_zone == "AEP"
            and row.forecast_year == 2026
            and row.adjustment_measure == TOTAL_ASSOCIATED_MW
        )
    ]
    current = screen_zone_year(b1, older_hole, "AEP", 2026, "2026-02-06")
    assert current.ltlf_vintage_year == 2026
    assert current.above_embedded_mw == 1913.0
    with pytest.raises(PjmViewError, match="does not have complete"):
        compare_zone_year_vintages(b1, older_hole, "AEP", 2026, "2026-02-06")


def test_contradictory_dates_and_duplicate_keys_fail_closed() -> None:
    b1, adjustments = _pair()
    shifted = [
        replace(row, vintage_available_at=date(2026, 1, 14), revision_date=date(2026, 1, 14))
        if row.ltlf_vintage_year == 2026
        and row.pjm_zone == "AEP"
        and row.forecast_year == 2026
        and row.adjustment_measure == ABOVE_EMBEDDED_MW
        else row
        for row in adjustments
    ]
    with pytest.raises(PjmViewError, match="contradictory publication dates"):
        screen_zone_year(b1, shifted, "AEP", 2026, "2026-02-06")
    target = next(
        row
        for row in b1
        if row.ltlf_vintage_year == 2026
        and row.pjm_zone == "AEP"
        and row.forecast_year == 2026
    )
    with pytest.raises(PjmViewError, match="Duplicate Table B1"):
        screen_zone_year([target, *b1], adjustments, "AEP", 2026, "2026-02-06")


def test_negative_and_zero_adjustments_stay_unchanged() -> None:
    b1, adjustments = _pair()
    ekpc = screen_zone_year(b1, adjustments, "EKPC", 2026, "2026-02-06")
    ae = screen_zone_year(b1, adjustments, "AE", 2026, "2026-02-06")
    assert ekpc.ltlf_vintage_year == 2026
    assert ekpc.above_embedded_mw == -10.0
    assert ekpc.total_associated_mw == -10.0
    assert ekpc.above_embedded_mw < 0
    assert ae.above_embedded_mw == 0.0
    assert ae.total_associated_mw == 0.0
    assert "state_id" not in ekpc.__dict__
    assert "risk_score" not in ekpc.__dict__
    assert "has_data_center_adjustment" not in ekpc.__dict__


def test_vintage_comparison_keeps_each_vintage_labeled() -> None:
    b1, adjustments = _pair()
    both = compare_zone_year_vintages(b1, adjustments, "AEP", 2026, "2026-02-06")
    assert [row.ltlf_vintage_year for row in both] == [2026, 2025]
    assert both[0].summer_peak_mw == 24635.0
    assert both[1].summer_peak_mw == 25788.0
    assert both[0].above_embedded_mw == 1913.0
    assert both[1].above_embedded_mw == 3621.0
    blended = (both[0].summer_peak_mw + both[1].summer_peak_mw) / 2
    assert blended not in {row.summer_peak_mw for row in both}
    only_2025 = compare_zone_year_vintages(b1, adjustments, "AEP", 2026, "2025-06-30")
    assert [row.ltlf_vintage_year for row in only_2025] == [2025]
    assert screen_zone_year(b1, adjustments, "AEP", 2026, "2026-02-06") == both[0]
    # Forecast year 2025 is outside the 2026 horizon, so the older vintage remains usable.
    prior_year = screen_zone_year(b1, adjustments, "AEP", 2025, "2026-02-06")
    assert prior_year.ltlf_vintage_year == 2025
    assert prior_year.summer_peak_mw == 23592.0


def test_distinct_retrieval_timestamps_stay_on_their_source_tables() -> None:
    b1, adjustments = _pair()
    b1 = [replace(row, retrieved_at=datetime(2026, 10, 1, 1, 0)) for row in b1]
    adjustments = [
        replace(
            row,
            retrieved_at=datetime(2026, 10, 2, 1, 0)
            if row.adjustment_measure == ABOVE_EMBEDDED_MW
            else datetime(2026, 10, 3, 1, 0),
        )
        for row in adjustments
    ]
    view = screen_zone_year(b1, adjustments, "AEP", 2026, "2026-02-06")
    assert [source.source_table for source in view.sources] == ["B1", "B-9", "B-9b"]
    assert view.retrieved_at == (
        datetime(2026, 10, 1, 1, 0),
        datetime(2026, 10, 2, 1, 0),
        datetime(2026, 10, 3, 1, 0),
    )


def test_official_aep_2026_view_matches_workbook_columns() -> None:
    if not all((_RAW / source.source_file).is_file() for source in TABLE_B1_SOURCES):
        skip_missing_cache("pjm_workbooks")
    b1 = load_slice1_tables(_RAW, retrieved_at=_RETRIEVED)
    adjustments = load_slice2_adjustments(_RAW, retrieved_at=_RETRIEVED)
    early = screen_zone_year(b1, adjustments, "AEP", 2026, "2025-06-30")
    assert early.available is True
    assert early.ltlf_vintage_year == 2025
    assert early.summer_peak_mw == 25788.0
    assert early.summer_peak_10yr_cagr == 0.0547154909
    assert early.above_embedded_mw == 3621.0
    assert early.total_associated_mw == 3936.0
    assert early.original_release_date == date(2025, 1, 24)
    assert early.revision_date is None
    assert early.vintage_available_at == date(2025, 1, 24)
    assert early.source_urls == (source_for_vintage(2025).source_url,) * 3
    assert early.retrieved_at == (_RETRIEVED,) * 3

    current = screen_zone_year(b1, adjustments, "AEP", 2026, "2026-02-06")
    assert current.ltlf_vintage_year == 2026
    assert current.summer_peak_mw == 24635.0
    assert current.summer_peak_10yr_cagr == 0.0525293343
    assert current.above_embedded_mw == 1913.0
    assert current.total_associated_mw == 2699.0
    assert current.original_release_date == date(2026, 1, 14)
    assert current.revision_date == date(2026, 2, 6)
    assert current.vintage_available_at == date(2026, 2, 6)
    assert current.source_urls == (source_for_vintage(2026).source_url,) * 3
    assert current.summer_peak_mw != early.summer_peak_mw
    assert "state_id" not in current.__dict__
    assert "risk_score" not in current.__dict__

    compared = compare_zone_year_vintages(b1, adjustments, "AEP", 2026, "2026-02-06")
    assert [row.ltlf_vintage_year for row in compared] == [2026, 2025]
    assert compared[0] == current
    assert compared[1].above_embedded_mw == 3621.0
    ekpc = screen_zone_year(b1, adjustments, "EKPC", 2026, "2026-02-06")
    assert ekpc.above_embedded_mw == -10.0
    assert ekpc.total_associated_mw == -10.0
    ae = screen_zone_year(b1, adjustments, "AE", 2026, "2026-02-06")
    assert ae.above_embedded_mw == 0.0
    assert ae.total_associated_mw == 0.0
    outside_horizon = screen_zone_year(b1, adjustments, "AEP", 2046, "2026-02-06")
    assert outside_horizon.ltlf_vintage_year == 2026
    assert compare_zone_year_vintages(b1, adjustments, "AEP", 2046, "2026-02-06") == (
        outside_horizon,
    )


def _pair() -> tuple[list[B1Row], list[AdjustmentRow]]:
    specs = (
        (2025, 2025, 23592.0, 0.0547154909, 1412.0, 1761.0, 0.0, -6.0),
        (2025, 2026, 25788.0, 0.0547154909, 3621.0, 3936.0, 1.0, -6.0),
        (2026, 2026, 24635.0, 0.0525293343, 1913.0, 2699.0, 0.0, -10.0),
        (2026, 2046, 46354.0, 0.0525293343, 20019.0, 20726.0, 4.0, -10.0),
    )
    peaks: list[B1Row] = []
    adjustments: list[AdjustmentRow] = []
    for vintage, year, peak, cagr, aep_above, aep_total, ae_value, ekpc_value in specs:
        for zone, above, total in (
            ("AEP", aep_above, aep_total),
            ("AE", ae_value, ae_value),
            ("EKPC", ekpc_value, ekpc_value),
        ):
            peaks.append(_peak(vintage, zone, year, peak if zone == "AEP" else 100.0, cagr))
            adjustments.append(_adjustment(vintage, zone, year, ABOVE_EMBEDDED_MW, above))
            adjustments.append(_adjustment(vintage, zone, year, TOTAL_ASSOCIATED_MW, total))
    return peaks, adjustments


def _peak(
    vintage: int,
    zone: str,
    year: int,
    peak: float,
    cagr: float,
) -> B1Row:
    source = source_for_vintage(vintage)
    return B1Row(
        pjm_zone=zone,
        ltlf_vintage_year=vintage,
        original_release_date=source.original_release_date,
        revision_date=source.revision_date,
        vintage_available_at=source.vintage_available_at,
        forecast_year=year,
        summer_peak_mw=peak,
        summer_peak_10yr_cagr=cagr,
        source_url=source.source_url,
        source_file=source.source_file,
        retrieved_at=_RETRIEVED,
    )


def _adjustment(
    vintage: int,
    zone: str,
    year: int,
    measure: str,
    value: float,
) -> AdjustmentRow:
    source = source_for_vintage(vintage)
    table = "B-9" if measure == ABOVE_EMBEDDED_MW else "B-9b"
    return AdjustmentRow(
        pjm_zone=zone,
        ltlf_vintage_year=vintage,
        forecast_year=year,
        adjustment_measure=measure,
        adjustment_mw=value,
        source_table=table,
        original_release_date=source.original_release_date,
        revision_date=source.revision_date,
        vintage_available_at=source.vintage_available_at,
        source_url=source.source_url,
        source_file=source.source_file,
        retrieved_at=_RETRIEVED,
    )

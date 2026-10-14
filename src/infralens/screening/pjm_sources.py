"""Official PJM sources for screening Slice 1.

Slice 1 reads Table B1 from the 2025 and 2026 Long-Term Load Forecast Tables
workbooks only. Dates below are file-level facts for those workbooks. They are
not inferred from a PDF cover or from a single sheet inside the file.

Deferred, and intentionally absent from the row schema:

- 2024 remains a revised PDF. Its Data workbook is a monthly peak and energy
  file, not Table B1. This slice does not parse it.
- Table B-9 and Table B-9b are different series. In the 2025 and 2026
  workbooks they differ by zone and year. A later slice must keep them as
  separate fields. Adjustment megawatts are not data-center demand: the 2024
  B-9 note mixes data-center growth with other adjustments, and the 2025 and
  2026 workbooks do not label B-9 as data-center load.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Published Table B1 transmission-owner zone order in the 2025 and 2026 workbooks.
# Aggregates in the same sheet (PJM RTO, PJM MID-ATLANTIC, PJM WESTERN,
# FE-EAST, PLGRP, and diversity rows) are not zone codes.
EXPECTED_B1_ZONE_CODES: tuple[str, ...] = (
    "AE",
    "BGE",
    "DPL",
    "JCPL",
    "METED",
    "PECO",
    "PENLC",
    "PEPCO",
    "PL",
    "PS",
    "RECO",
    "UGI",
    "AEP",
    "APS",
    "ATSI",
    "COMED",
    "DAYTON",
    "DEOK",
    "DLCO",
    "EKPC",
    "OVEC",
    "DOM",
)

_PJM_MEDIA = "https://www.pjm.com/-/media/DotCom/planning/res-adeq/load-forecast"


@dataclass(frozen=True)
class PjmTablesSource:
    """One official Tables workbook used for Table B1."""

    ltlf_vintage_year: int
    source_url: str
    source_file: str
    original_release_date: date
    revision_date: date | None
    vintage_available_at: date
    sheet_name: str = "Table B1"

    def __post_init__(self) -> None:
        expected = (
            self.revision_date
            if self.revision_date is not None
            else self.original_release_date
        )
        if self.vintage_available_at != expected:
            raise ValueError(
                f"{self.ltlf_vintage_year} vintage_available_at "
                f"{self.vintage_available_at.isoformat()} does not match "
                f"the file-level revision rule ({expected.isoformat()})."
            )


TABLE_B1_SOURCES: tuple[PjmTablesSource, ...] = (
    PjmTablesSource(
        ltlf_vintage_year=2025,
        source_url=f"{_PJM_MEDIA}/2025-load-report-tables.xlsx",
        source_file="2025-load-report-tables.xlsx",
        original_release_date=date(2025, 1, 24),
        revision_date=None,
        vintage_available_at=date(2025, 1, 24),
    ),
    PjmTablesSource(
        ltlf_vintage_year=2026,
        source_url=f"{_PJM_MEDIA}/2026-load-report-tables.xlsx",
        source_file="2026-load-report-tables.xlsx",
        original_release_date=date(2026, 1, 14),
        revision_date=date(2026, 2, 6),
        vintage_available_at=date(2026, 2, 6),
    ),
)


def source_for_vintage(ltlf_vintage_year: int) -> PjmTablesSource:
    """Return the Slice 1 manifest entry for one Tables vintage."""
    matches = [
        source
        for source in TABLE_B1_SOURCES
        if source.ltlf_vintage_year == ltlf_vintage_year
    ]
    if len(matches) != 1:
        raise KeyError(f"No Slice 1 Tables source for vintage {ltlf_vintage_year}.")
    return matches[0]

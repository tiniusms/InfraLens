"""PJM zone-year screening for the demo page.

Parsing and vintage selection stay in ``infralens.screening``. This module
only locates the cached workbooks, records their local file-creation times,
and presents one ``screen_zone_year`` result. It does not download files,
add B-9 to B-9b, or score investment risk.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from infralens.demo.foundation import DemoDataError
from infralens.screening.pjm_adjustments import AdjustmentRow, load_slice2_adjustments
from infralens.screening.pjm_b1 import B1Row, load_slice1_tables
from infralens.screening.pjm_sources import EXPECTED_B1_ZONE_CODES, TABLE_B1_SOURCES
from infralens.screening.pjm_view import ZoneYearScreening, screen_zone_year

FORECAST_YEARS: tuple[int, ...] = tuple(range(2025, 2047))
DEFAULT_ZONE = "AEP"
DEFAULT_FORECAST_YEAR = 2026
DEFAULT_AS_OF = date(2026, 2, 6)

GEOGRAPHIC_WARNING = (
    "PJM zones and US states are not interchangeable. Some zones cross state borders. "
    "This tab does not join a zone to an EIA state, allocate MW to a state, or rank locations."
)
LARGE_LOAD_WARNING = (
    "B-9 above-embedded MW and B-9b total-associated MW are separate forecast adjustment measures. "
    "Neither is isolated data-center MW, and neither is a verified realized load. "
    "They are not added together."
)
MISSING_WORKBOOKS = (
    "The official 2025 or 2026 PJM Tables workbook is not on this machine, "
    "so zonal screening is unavailable. Do not download a substitute from this page. "
    "The EIA charts and the cost calculator still run."
)
RETRIEVAL_UNAVAILABLE = (
    "A retrieval timestamp for the local PJM workbooks cannot be established "
    "from file-creation metadata. Screening numbers are not shown, because a "
    "retrieval time will not be invented."
)
UNPUBLISHED_NOTE = "Unpublished on this as-of date. Measures are not shown as zero."
CAGR_PERCENT_LABEL = (
    "10-year CAGR percent per year (decimal × 100; not a separate published field)"
)
MALFORMED_VINTAGE_NOTE = (
    "This published vintage is incomplete or contradictory. An older vintage is not substituted."
)


@dataclass(frozen=True)
class WorkbookRetrieval:
    """One loader timestamp taken from local file-creation times.

    ``loader_retrieved_at`` is the later creation time because the workbook
    parsers accept a single timestamp. Both creation times stay in the note.
    """

    loader_retrieved_at: datetime
    file_creation_times_utc: tuple[tuple[str, str], ...]
    note: str


@dataclass(frozen=True)
class ScreeningDisplay:
    """UI-facing fields for one zone and forecast year. B-9 and B-9b stay separate."""

    available: bool
    pjm_zone: str
    forecast_year: int
    as_of_date: date
    ltlf_vintage_year: int | None
    summer_peak_mw: float | None
    summer_peak_10yr_cagr: float | None
    cagr_percent_per_year: float | None
    above_embedded_mw: float | None
    total_associated_mw: float | None
    original_release_date: date | None
    revision_date: date | None
    vintage_available_at: date | None
    source_tables: tuple[str, ...]
    source_files: tuple[str, ...]
    source_urls: tuple[str, ...]
    retrieved_at: tuple[str, ...]
    unavailable_reason: str | None
    geographic_warning: str
    large_load_warning: str
    retrieval_note: str


def workbook_paths(raw_dir: Path) -> tuple[Path, Path]:
    """The two cached Tables workbooks, in manifest order."""

    return tuple(raw_dir / source.source_file for source in TABLE_B1_SOURCES)  # type: ignore[return-value]


def workbook_identity(path: Path) -> tuple[str, int, int, int | None]:
    """Name, size, mtime, and birth time. A replaced file changes this key."""

    stat = path.stat()
    birth = getattr(stat, "st_birthtime_ns", None)
    birth_ns = None if birth is None else int(birth)
    return (path.name, stat.st_size, stat.st_mtime_ns, birth_ns)


def local_workbook_retrieved_at(paths: tuple[Path, ...]) -> WorkbookRetrieval:
    """Read file-creation times. A missing birth time is reported, not filled in."""

    created: list[tuple[str, datetime]] = []
    for path in paths:
        stat = path.stat()
        birth = getattr(stat, "st_birthtime", None)
        if birth is None:
            raise DemoDataError(RETRIEVAL_UNAVAILABLE)
        created.append((path.name, datetime.fromtimestamp(birth, tz=timezone.utc)))
    later = max(stamp for _, stamp in created)
    listed = ", ".join(f"{name} {stamp.isoformat()}" for name, stamp in created)
    note = (
        "retrieved_at is the later local file-creation time of the cached workbooks, "
        f"{later.isoformat()}. File creation times: {listed}. "
        "The parsers record that one timestamp on every row. "
        "This is not a PJM publication date and not a download receipt."
    )
    return WorkbookRetrieval(
        loader_retrieved_at=later,
        file_creation_times_utc=tuple((name, stamp.isoformat()) for name, stamp in created),
        note=note,
    )


def load_screening_tables(
    raw_dir: Path,
) -> tuple[list[B1Row], list[AdjustmentRow], WorkbookRetrieval]:
    """Parse both workbooks with the existing loaders. A missing file stays missing."""

    paths = workbook_paths(raw_dir)
    if any(not path.is_file() for path in paths):
        raise DemoDataError(MISSING_WORKBOOKS)
    retrieval = local_workbook_retrieved_at(paths)
    b1_rows = load_slice1_tables(raw_dir, retrieved_at=retrieval.loader_retrieved_at)
    adjustment_rows = load_slice2_adjustments(
        raw_dir,
        retrieved_at=retrieval.loader_retrieved_at,
    )
    return b1_rows, adjustment_rows, retrieval


def screen_cached_zone(
    b1_rows: list[B1Row],
    adjustment_rows: list[AdjustmentRow],
    pjm_zone: str,
    forecast_year: int,
    as_of_date: date,
) -> ZoneYearScreening:
    """Select one vintage. Unknown zones are rejected before the view runs.

    ``PjmViewError`` from a public but incomplete vintage is left unchanged.
    """

    if pjm_zone not in EXPECTED_B1_ZONE_CODES:
        raise DemoDataError(
            f"Unknown PJM zone {pjm_zone}. "
            "Only the 22 transmission-owner codes from the Tables workbooks are accepted."
        )
    return screen_zone_year(b1_rows, adjustment_rows, pjm_zone, forecast_year, as_of_date)


def present_screening(result: ZoneYearScreening, retrieval_note: str) -> ScreeningDisplay:
    """Copy the selected vintage into display fields. Adjustment MW are not summed."""

    cagr = result.summer_peak_10yr_cagr
    return ScreeningDisplay(
        available=result.available,
        pjm_zone=result.pjm_zone,
        forecast_year=result.forecast_year,
        as_of_date=result.as_of_date,
        ltlf_vintage_year=result.ltlf_vintage_year,
        summer_peak_mw=result.summer_peak_mw,
        summer_peak_10yr_cagr=cagr,
        cagr_percent_per_year=None if cagr is None else cagr * 100.0,
        above_embedded_mw=result.above_embedded_mw,
        total_associated_mw=result.total_associated_mw,
        original_release_date=result.original_release_date,
        revision_date=result.revision_date,
        vintage_available_at=result.vintage_available_at,
        source_tables=tuple(source.source_table for source in result.sources),
        source_files=tuple(source.source_file for source in result.sources),
        source_urls=result.source_urls,
        retrieved_at=tuple(
            "" if stamp is None else stamp.isoformat() for stamp in result.retrieved_at
        ),
        unavailable_reason=result.unavailable_reason,
        geographic_warning=GEOGRAPHIC_WARNING,
        large_load_warning=LARGE_LOAD_WARNING,
        retrieval_note=retrieval_note,
    )

"""PJM zone-year screening for the demo page.

Parsing and vintage selection stay in ``infralens.screening``. This module
only locates the cached workbooks, takes their recorded retrieval times from
``data/manifest.json`` after a SHA-256 check, and presents one
``screen_zone_year`` result. It does not read file-system times as
provenance, download files, add B-9 to B-9b, or score investment risk.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from infralens.data.manifest import (
    ManifestError,
    ManifestFileMismatch,
    RecordedRetrieval,
    default_manifest_path,
    recorded_retrieval,
)
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
    "A recorded retrieval time for the local PJM workbooks is not in the data manifest. "
    "Screening numbers are not shown, because a retrieval time will not be invented."
)
FILE_MISMATCH = (
    "A local PJM workbook does not match the SHA-256 recorded in the data manifest. "
    "Screening numbers and the recorded retrieval time are not shown."
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
    """Recorded retrieval times from the data manifest, one per workbook.

    ``loader_retrieved_at`` is the later recorded time, passed to the parsers,
    which accept a single timestamp. Parsed rows are then re-stamped with
    their own workbook's recorded time.
    """

    loader_retrieved_at: datetime
    recorded_times_utc: tuple[tuple[str, str], ...]
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


def workbook_identity(path: Path) -> tuple[str, int, int, int]:
    """Name, size, mtime, and inode-change time. Only detects a changed file.

    This key is for caching. It is not provenance: the retrieval time comes
    from the data manifest after a SHA-256 check.
    """

    stat = path.stat()
    return (path.name, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def manifest_identity(manifest_path: Path) -> tuple[str, int, int, int] | None:
    """Cache key for the manifest itself, so editing it drops parsed tables."""

    if not manifest_path.is_file():
        return None
    return workbook_identity(manifest_path)


def manifest_workbook_retrieval(
    paths: tuple[Path, ...],
    manifest_path: Path | None = None,
) -> WorkbookRetrieval:
    """Recorded retrieval times from the data manifest. Nothing is filled in.

    A file that differs from its manifest fingerprint raises ``FILE_MISMATCH``.
    A missing manifest, a missing entry, or an entry without a recorded
    retrieval time raises ``RETRIEVAL_UNAVAILABLE``.
    """

    manifest = manifest_path or default_manifest_path()
    recorded: list[RecordedRetrieval] = []
    for path in paths:
        try:
            recorded.append(recorded_retrieval(manifest, path))
        except ManifestFileMismatch as exc:
            raise DemoDataError(FILE_MISMATCH) from exc
        except ManifestError as exc:
            raise DemoDataError(RETRIEVAL_UNAVAILABLE) from exc
    return WorkbookRetrieval(
        loader_retrieved_at=max(item.retrieved_at for item in recorded),
        recorded_times_utc=tuple((item.filename, _utc_text(item.retrieved_at)) for item in recorded),
        note=_retrieval_note(recorded),
    )


def load_screening_tables(
    raw_dir: Path,
    manifest_path: Path | None = None,
) -> tuple[list[B1Row], list[AdjustmentRow], WorkbookRetrieval]:
    """Parse both workbooks with the existing loaders. A missing file stays missing."""

    paths = workbook_paths(raw_dir)
    if any(not path.is_file() for path in paths):
        raise DemoDataError(MISSING_WORKBOOKS)
    retrieval = manifest_workbook_retrieval(paths, manifest_path)
    by_file = {name: datetime.fromisoformat(text.removesuffix("Z") + "+00:00") for name, text in retrieval.recorded_times_utc}
    b1_rows = load_slice1_tables(raw_dir, retrieved_at=retrieval.loader_retrieved_at)
    adjustment_rows = load_slice2_adjustments(
        raw_dir,
        retrieved_at=retrieval.loader_retrieved_at,
    )
    b1_rows = [replace(row, retrieved_at=by_file[row.source_file]) for row in b1_rows]
    adjustment_rows = [replace(row, retrieved_at=by_file[row.source_file]) for row in adjustment_rows]
    return b1_rows, adjustment_rows, retrieval


def _utc_text(stamp: datetime) -> str:
    return stamp.isoformat().replace("+00:00", "Z")


def _retrieval_note(recorded: list[RecordedRetrieval]) -> str:
    days = sorted({item.retrieved_at.date().isoformat() for item in recorded})
    rechecked = [item.byte_identical_recheck for item in recorded]
    if all(rechecked):
        kind = "byte-identical copy; original download time not recorded"
    elif not any(rechecked):
        kind = "recorded at download"
    else:
        kind = "recorded per workbook; see the manifest evidence"
    times = "; ".join(f"{item.filename} {_utc_text(item.retrieved_at)}" for item in recorded)
    evidence = " ".join(f'{item.filename}: "{item.evidence}".' for item in recorded)
    return (
        f"Retrieved {' and '.join(days)} ({kind}). "
        f"retrieved_at comes from the data manifest: {times}. "
        f"Manifest evidence: {evidence} "
        "This is not a PJM publication date; vintage availability uses the PJM release dates."
    )


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
        retrieved_at=tuple("" if stamp is None else _utc_text(stamp) for stamp in result.retrieved_at),
        unavailable_reason=result.unavailable_reason,
        geographic_warning=GEOGRAPHIC_WARNING,
        large_load_warning=LARGE_LOAD_WARNING,
        retrieval_note=retrieval_note,
    )

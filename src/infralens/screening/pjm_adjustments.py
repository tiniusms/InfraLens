"""Parse PJM Table B-9 and Table B-9b as separate adjustment series.

B-9 is "Adjustments Above Embedded" in MW. B-9b is "Total Load Associated
with Adjustments" in MW. The two values are not added, and neither is
data-center demand. Forecast years come from each sheet's year header.
Publication dates come from the Tables-workbook manifest, not from a note
inside the sheet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping, Sequence

from infralens.screening.pjm_b1 import (
    PjmB1Error,
    _column_index,
    _forecast_year,
    _read_sheet,
    _require_number,
)
from infralens.screening.pjm_sources import (
    EXPECTED_B1_ZONE_CODES,
    TABLE_B1_SOURCES,
    PjmTablesSource,
    source_for_vintage,
)

ABOVE_EMBEDDED_MW = "above_embedded_mw"
TOTAL_ASSOCIATED_MW = "total_associated_mw"

_EXPECTED_ZONES = frozenset(EXPECTED_B1_ZONE_CODES)
_IGNORED_LABELS = frozenset(
    {
        "Back to TOC",
        "Table B-9",
        "Table B-9b",
        "PJM RTO",
    }
)


class PjmAdjustmentError(ValueError):
    """B-9 or B-9b could not be parsed without inventing a value."""


@dataclass(frozen=True)
class AdjustmentTable:
    """One adjustment sheet inside a Tables workbook."""

    sheet_name: str
    source_table: str
    adjustment_measure: str
    title_phrase: str


ADJUSTMENT_TABLES: tuple[AdjustmentTable, ...] = (
    AdjustmentTable(
        sheet_name="Table B9",
        source_table="B-9",
        adjustment_measure=ABOVE_EMBEDDED_MW,
        title_phrase="adjustments above embedded",
    ),
    AdjustmentTable(
        sheet_name="Table B9b",
        source_table="B-9b",
        adjustment_measure=TOTAL_ASSOCIATED_MW,
        title_phrase="total load associated with adjustments",
    ),
)


@dataclass(frozen=True)
class AdjustmentRow:
    """One zone, vintage, forecast year, and adjustment measure."""

    pjm_zone: str
    ltlf_vintage_year: int
    forecast_year: int
    adjustment_measure: str
    adjustment_mw: float
    source_table: str
    original_release_date: date
    revision_date: date | None
    vintage_available_at: date | None
    source_url: str
    source_file: str
    retrieved_at: datetime | None = None

    @property
    def key(self) -> tuple[str, int, int, str]:
        return (
            self.pjm_zone,
            self.ltlf_vintage_year,
            self.forecast_year,
            self.adjustment_measure,
        )


def parse_adjustment_table(
    path: Path | str,
    source: PjmTablesSource,
    table: AdjustmentTable,
    *,
    retrieved_at: datetime | None = None,
) -> list[AdjustmentRow]:
    """Parse one B-9 or B-9b sheet into zone-level rows."""
    workbook = Path(path)
    if not workbook.is_file():
        raise PjmAdjustmentError(f"Tables workbook is missing: {workbook}")
    try:
        cells = _read_sheet(workbook, table.sheet_name)
    except PjmB1Error as exc:
        raise PjmAdjustmentError(str(exc)) from exc
    _require_measure_title(cells, table)
    header_row, year_columns = _year_columns(cells)
    zone_rows = _zone_rows(cells, header_row)
    _require_exact_zones(zone_rows, table.source_table)

    parsed: list[AdjustmentRow] = []
    for zone, row_number in zone_rows:
        for year, column in year_columns:
            try:
                adjustment_mw = _require_number(
                    cells.get((row_number, column)),
                    f"{zone} {table.source_table} MW for {year}",
                )
            except PjmB1Error as exc:
                raise PjmAdjustmentError(str(exc)) from exc
            parsed.append(
                AdjustmentRow(
                    pjm_zone=zone,
                    ltlf_vintage_year=source.ltlf_vintage_year,
                    forecast_year=year,
                    adjustment_measure=table.adjustment_measure,
                    adjustment_mw=adjustment_mw,
                    source_table=table.source_table,
                    original_release_date=source.original_release_date,
                    revision_date=source.revision_date,
                    vintage_available_at=source.vintage_available_at,
                    source_url=source.source_url,
                    source_file=source.source_file,
                    retrieved_at=retrieved_at,
                )
            )
    keys = [row.key for row in parsed]
    if len(keys) != len(set(keys)):
        raise PjmAdjustmentError(
            "Duplicate pjm_zone, vintage, forecast year, and adjustment measure."
        )
    return parsed


def load_slice2_adjustments(
    raw_dir: Path | str,
    *,
    retrieved_at: datetime,
) -> list[AdjustmentRow]:
    """Parse B-9 and B-9b from both Slice 1 Tables workbooks.

    ``retrieved_at`` is supplied by the caller. Publication dates stay on
    the file-level manifest.
    """
    if not isinstance(retrieved_at, datetime):
        raise PjmAdjustmentError("retrieved_at is missing.")
    directory = Path(raw_dir)
    rows: list[AdjustmentRow] = []
    for source in TABLE_B1_SOURCES:
        workbook = directory / source.source_file
        for table in ADJUSTMENT_TABLES:
            rows.extend(
                parse_adjustment_table(
                    workbook,
                    source,
                    table,
                    retrieved_at=retrieved_at,
                )
            )
    validate_adjustment_rows(rows)
    return rows


def validate_adjustment_rows(rows: Sequence[AdjustmentRow]) -> None:
    """Reject an incomplete, undated, or mixed-measure adjustment extract."""
    if not rows:
        raise PjmAdjustmentError("No adjustment rows to validate.")
    keys = [row.key for row in rows]
    if len(keys) != len(set(keys)):
        raise PjmAdjustmentError(
            "Duplicate pjm_zone, vintage, forecast year, and adjustment measure."
        )
    by_vintage: dict[int, list[AdjustmentRow]] = {}
    for row in rows:
        _require_manifest_provenance(row)
        if row.adjustment_measure not in {ABOVE_EMBEDDED_MW, TOTAL_ASSOCIATED_MW}:
            raise PjmAdjustmentError(
                f"Unexpected adjustment measure {row.adjustment_measure!r}."
            )
        expected_table = _table_for_measure(row.adjustment_measure).source_table
        if row.source_table != expected_table:
            raise PjmAdjustmentError(
                f"{row.adjustment_measure} does not match source table {row.source_table}."
            )
        try:
            _require_number(row.adjustment_mw, f"{row.pjm_zone} adjustment MW")
        except PjmB1Error as exc:
            raise PjmAdjustmentError(str(exc)) from exc
        if not isinstance(row.retrieved_at, datetime):
            raise PjmAdjustmentError(f"retrieved_at is missing for {row.pjm_zone}.")
        by_vintage.setdefault(row.ltlf_vintage_year, []).append(row)
    for vintage, group in by_vintage.items():
        measures = {row.adjustment_measure for row in group}
        if measures != {ABOVE_EMBEDDED_MW, TOTAL_ASSOCIATED_MW}:
            raise PjmAdjustmentError(
                f"Vintage {vintage} is missing one of the two adjustment tables."
            )
        for measure in measures:
            subset = [row for row in group if row.adjustment_measure == measure]
            zones = {row.pjm_zone for row in subset}
            if zones != _EXPECTED_ZONES:
                raise PjmAdjustmentError(
                    f"Vintage {vintage} {measure} zone set is not the verified 22 codes."
                )
            years = {row.forecast_year for row in subset}
            for zone in EXPECTED_B1_ZONE_CODES:
                got = {row.forecast_year for row in subset if row.pjm_zone == zone}
                if got != years:
                    raise PjmAdjustmentError(
                        f"{zone} vintage {vintage} {measure} is missing a required forecast year."
                    )


def filter_adjustment_rows(
    rows: Sequence[AdjustmentRow],
    as_of_date: date | str,
) -> list[AdjustmentRow]:
    """Keep rows whose stored Tables file was already public on ``as_of_date``."""
    as_of = _require_date(as_of_date, "as_of_date")
    available_on: list[tuple[AdjustmentRow, date]] = []
    for row in rows:
        label = (
            f"{row.pjm_zone} {row.adjustment_measure} vintage {row.ltlf_vintage_year}"
        )
        available_on.append(
            (
                row,
                _require_date(row.vintage_available_at, f"vintage_available_at for {label}"),
            )
        )
    return [row for row, available in available_on if available <= as_of]


def _require_measure_title(
    cells: Mapping[tuple[int, str], object],
    table: AdjustmentTable,
) -> None:
    matches = [
        " ".join(value.lower().split())
        for value in cells.values()
        if isinstance(value, str) and table.title_phrase in " ".join(value.lower().split())
    ]
    if len(matches) != 1:
        raise PjmAdjustmentError(
            f"{table.source_table} title {table.title_phrase!r} was found {len(matches)} times."
        )
    if "(mw)" not in matches[0]:
        raise PjmAdjustmentError(f"{table.source_table} is not labeled in MW.")


def _year_columns(
    cells: Mapping[tuple[int, str], object],
) -> tuple[int, list[tuple[int, str]]]:
    header_rows = [row for row in {item[0] for item in cells} if _is_year_header_row(cells, row)]
    if len(header_rows) != 1:
        raise PjmAdjustmentError(
            f"Expected one forecast-year header row, found {len(header_rows)}."
        )
    header_row = header_rows[0]
    columns = sorted(
        (column for row, column in cells if row == header_row),
        key=_column_index,
    )
    years: list[tuple[int, str]] = []
    seen: set[int] = set()
    for column in columns:
        year = _forecast_year(cells[(header_row, column)])
        if year is None:
            continue
        if year in seen:
            raise PjmAdjustmentError(f"Duplicate forecast-year header {year}.")
        seen.add(year)
        years.append((year, column))
    if len(years) < 2:
        raise PjmAdjustmentError("Adjustment table has no forecast-year header.")
    sequence = [year for year, _column in years]
    if sequence != list(range(sequence[0], sequence[-1] + 1)):
        raise PjmAdjustmentError("Forecast-year headers are not contiguous.")
    return header_row, years


def _is_year_header_row(cells: Mapping[tuple[int, str], object], row: int) -> bool:
    # MW values can sit inside 1900–2200. A data row has a zone label in
    # column A; the year header does not.
    if _label_text(cells.get((row, "A"))) is not None:
        return False
    years = [
        _forecast_year(cells[(row, column)])
        for candidate, column in cells
        if candidate == row
    ]
    return sum(year is not None for year in years) >= 2


def _zone_rows(
    cells: Mapping[tuple[int, str], object],
    header_row: int,
) -> list[tuple[str, int]]:
    labels = [
        (row, cells[(row, "A")])
        for row, column in cells
        if column == "A" and row > header_row
    ]
    found: list[tuple[str, int]] = []
    seen: set[str] = set()
    for row, raw in sorted(labels):
        label = _label_text(raw)
        if label is None or _is_ignored_label(label):
            continue
        if label not in _EXPECTED_ZONES:
            raise PjmAdjustmentError(f"Unexpected adjustment zone code {label!r}.")
        if label in seen:
            raise PjmAdjustmentError(f"Duplicate adjustment zone code {label}.")
        seen.add(label)
        found.append((label, row))
    return found


def _require_exact_zones(zone_rows: Sequence[tuple[str, int]], source_table: str) -> None:
    found = [zone for zone, _row in zone_rows]
    missing = [zone for zone in EXPECTED_B1_ZONE_CODES if zone not in found]
    if missing:
        raise PjmAdjustmentError(
            f"{source_table} is missing zone codes: " + ", ".join(missing)
        )
    if found != list(EXPECTED_B1_ZONE_CODES):
        raise PjmAdjustmentError(
            f"{source_table} zone codes are not the verified 22-code list."
        )


def _label_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.replace("\xa0", " ").strip()
    return text or None


def _is_ignored_label(label: str) -> bool:
    if label in _IGNORED_LABELS:
        return True
    if label.startswith("Column") and label[6:].isdigit():
        return True
    if label.startswith("*"):
        return True
    lowered = label.lower()
    return lowered.startswith("adjustments above embedded") or lowered.startswith(
        "total load associated"
    )


def _require_manifest_provenance(row: AdjustmentRow) -> None:
    try:
        source = source_for_vintage(row.ltlf_vintage_year)
    except KeyError as exc:
        raise PjmAdjustmentError(
            f"Vintage {row.ltlf_vintage_year} is not a Slice 2 Tables source."
        ) from exc
    if row.pjm_zone not in _EXPECTED_ZONES:
        raise PjmAdjustmentError(f"Unexpected adjustment zone code {row.pjm_zone!r}.")
    if row.original_release_date != source.original_release_date:
        raise PjmAdjustmentError(
            f"{row.ltlf_vintage_year} original_release_date does not match the manifest."
        )
    if row.revision_date != source.revision_date:
        raise PjmAdjustmentError(
            f"{row.ltlf_vintage_year} revision_date does not match the manifest."
        )
    if row.vintage_available_at != source.vintage_available_at:
        raise PjmAdjustmentError(
            f"{row.ltlf_vintage_year} vintage_available_at does not match the manifest."
        )
    if row.source_url != source.source_url or row.source_file != source.source_file:
        raise PjmAdjustmentError(
            f"{row.ltlf_vintage_year} source URL or filename does not match the manifest."
        )


def _table_for_measure(adjustment_measure: str) -> AdjustmentTable:
    matches = [
        table
        for table in ADJUSTMENT_TABLES
        if table.adjustment_measure == adjustment_measure
    ]
    if len(matches) != 1:
        raise PjmAdjustmentError(f"Unexpected adjustment measure {adjustment_measure!r}.")
    return matches[0]


def _require_date(value: date | datetime | str | None, field_name: str) -> date:
    if value is None or value == "":
        raise PjmAdjustmentError(f"{field_name} is missing.")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise PjmAdjustmentError(
                f"{field_name} is not an ISO date: {value!r}."
            ) from exc
    raise PjmAdjustmentError(f"{field_name} is not a date: {value!r}.")

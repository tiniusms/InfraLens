"""Parse PJM Table B1 summer-peak rows from the Slice 1 Tables workbooks.

Forecast-year headers are the calendar year alone. ``Metered`` and
``Unrestricted`` headers are prior-year history, even when they contain a
year. The 10-year rate is the decimal in the ``Annual Growth Rate (10 yr)``
column on the zone row. The following row's year-by-year growth text is not
that rate.

Missing or non-numeric peak and growth cells raise. They are not stored as zero.
"""

from __future__ import annotations

import math
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping, Sequence
from xml.etree import ElementTree as ET

from infralens.screening.pjm_sources import (
    EXPECTED_B1_ZONE_CODES,
    TABLE_B1_SOURCES,
    PjmTablesSource,
    source_for_vintage,
)

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

# Labels on Table B1 that are not transmission-owner zone codes.
_NON_ZONE_LABELS = frozenset(
    {
        "Back to TOC",
        "Table B-1",
        "DIVERSITY - TOTAL(-)",
        "DIVERSITY - MID-ATLANTIC(-)",
        "DIVERSITY - WESTERN(-)",
        "PJM RTO",
        "PJM MID-ATLANTIC",
        "PJM WESTERN",
        "FE-EAST",
        "PLGRP",
    }
)
_EXPECTED_ZONES = frozenset(EXPECTED_B1_ZONE_CODES)


class PjmB1Error(ValueError):
    """Table B1 could not be parsed without inventing a value."""


@dataclass(frozen=True)
class B1Row:
    """One zone, vintage, and forecast year from Table B1."""

    pjm_zone: str
    ltlf_vintage_year: int
    original_release_date: date
    revision_date: date | None
    vintage_available_at: date | None
    forecast_year: int
    summer_peak_mw: float
    summer_peak_10yr_cagr: float
    source_url: str
    source_file: str
    retrieved_at: datetime | None = None

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.pjm_zone, self.ltlf_vintage_year, self.forecast_year)


def parse_table_b1(
    path: Path | str,
    source: PjmTablesSource,
    *,
    retrieved_at: datetime | None = None,
) -> list[B1Row]:
    """Parse one official or fixture workbook into zone-level B1 rows."""
    workbook = Path(path)
    if not workbook.is_file():
        raise PjmB1Error(f"Tables workbook is missing: {workbook}")
    cells = _read_sheet(workbook, source.sheet_name)
    header_row, year_columns, cagr_column = _header_columns(cells)
    zone_rows = _zone_rows(cells, header_row)
    _require_exact_zones(zone_rows)

    parsed: list[B1Row] = []
    for zone, row_number in zone_rows:
        cagr = _require_number(
            cells.get((row_number, cagr_column)),
            f"{zone} 10-year growth rate",
        )
        for year, column in year_columns:
            peak_mw = _require_number(
                cells.get((row_number, column)),
                f"{zone} summer peak for {year}",
            )
            parsed.append(
                B1Row(
                    pjm_zone=zone,
                    ltlf_vintage_year=source.ltlf_vintage_year,
                    original_release_date=source.original_release_date,
                    revision_date=source.revision_date,
                    vintage_available_at=source.vintage_available_at,
                    forecast_year=year,
                    summer_peak_mw=peak_mw,
                    summer_peak_10yr_cagr=cagr,
                    source_url=source.source_url,
                    source_file=source.source_file,
                    retrieved_at=retrieved_at,
                )
            )
    keys = [row.key for row in parsed]
    if len(keys) != len(set(keys)):
        raise PjmB1Error("Duplicate pjm_zone, vintage, and forecast year.")
    return parsed


def load_slice1_tables(
    raw_dir: Path | str,
    *,
    retrieved_at: datetime,
) -> list[B1Row]:
    """Parse both Slice 1 workbooks and reject an incomplete or undated result.

    ``retrieved_at`` is the caller's retrieval timestamp. This function does
    not invent one, and it does not read publication dates from the workbook.
    """
    if not isinstance(retrieved_at, datetime):
        raise PjmB1Error("retrieved_at is missing.")
    directory = Path(raw_dir)
    rows: list[B1Row] = []
    for source in TABLE_B1_SOURCES:
        rows.extend(
            parse_table_b1(
                directory / source.source_file,
                source,
                retrieved_at=retrieved_at,
            )
        )
    validate_b1_rows(rows)
    return rows


def validate_b1_rows(rows: Sequence[B1Row]) -> None:
    """Reject a Slice 1 result that is incomplete, undated, or not zone-level.

    Dates and URLs must match the file-level manifest. A blank, nonnumeric,
    or duplicate forecast cell cannot be repaired here.
    """
    if not rows:
        raise PjmB1Error("No Table B1 rows to validate.")
    keys = [row.key for row in rows]
    if len(keys) != len(set(keys)):
        raise PjmB1Error("Duplicate pjm_zone, vintage, and forecast year.")
    by_vintage: dict[int, list[B1Row]] = {}
    for row in rows:
        _require_manifest_provenance(row)
        _require_number(row.summer_peak_mw, f"{row.pjm_zone} summer peak")
        _require_number(row.summer_peak_10yr_cagr, f"{row.pjm_zone} 10-year growth rate")
        if not isinstance(row.retrieved_at, datetime):
            raise PjmB1Error(f"retrieved_at is missing for {row.pjm_zone}.")
        by_vintage.setdefault(row.ltlf_vintage_year, []).append(row)
    for vintage, group in by_vintage.items():
        zones = {row.pjm_zone for row in group}
        if zones != set(EXPECTED_B1_ZONE_CODES):
            raise PjmB1Error(
                f"Vintage {vintage} zone set is not the verified 22 Table B1 codes."
            )
        years = {row.forecast_year for row in group}
        if not years:
            raise PjmB1Error(f"Vintage {vintage} has no forecast years.")
        for zone in EXPECTED_B1_ZONE_CODES:
            got = {row.forecast_year for row in group if row.pjm_zone == zone}
            if got != years:
                raise PjmB1Error(
                    f"{zone} vintage {vintage} is missing a required forecast year."
                )


def filter_b1_rows(rows: Sequence[B1Row], as_of_date: date | str) -> list[B1Row]:
    """Keep rows whose stored file was already public on ``as_of_date``.

    A missing or invalid date raises. The row is not treated as available
    and it is not dropped quietly while other rows are returned.
    """
    as_of = _require_date(as_of_date, "as_of_date")
    available_on: list[tuple[B1Row, date]] = []
    for row in rows:
        label = f"{row.pjm_zone} vintage {row.ltlf_vintage_year}"
        available_on.append(
            (row, _require_date(row.vintage_available_at, f"vintage_available_at for {label}"))
        )
    return [row for row, available in available_on if available <= as_of]


def write_b1_parquet(rows: Sequence[B1Row], path: Path | str) -> Path:
    """Write parsed rows to a local Parquet file. The caller chooses a gitignored path."""
    import pandas as pd

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "pjm_zone": row.pjm_zone,
                "ltlf_vintage_year": row.ltlf_vintage_year,
                "original_release_date": row.original_release_date,
                "revision_date": row.revision_date,
                "vintage_available_at": row.vintage_available_at,
                "forecast_year": row.forecast_year,
                "summer_peak_mw": row.summer_peak_mw,
                "summer_peak_10yr_cagr": row.summer_peak_10yr_cagr,
                "source_url": row.source_url,
                "source_file": row.source_file,
                "retrieved_at": row.retrieved_at,
            }
            for row in rows
        ]
    )
    frame.to_parquet(destination, index=False)
    return destination


def _read_sheet(path: Path, sheet_name: str) -> dict[tuple[int, str], object]:
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise PjmB1Error(f"Not an xlsx workbook: {path}") from exc
    with archive:
        shared = _shared_strings(archive)
        target = _sheet_target(archive, sheet_name)
        root = ET.fromstring(archive.read(target))
    cells: dict[tuple[int, str], object] = {}
    for cell in root.iter(f"{_MAIN}c"):
        ref = cell.attrib.get("r")
        if not ref:
            raise PjmB1Error(f"{sheet_name} has a cell without a reference.")
        column = "".join(char for char in ref if char.isalpha())
        row_text = "".join(char for char in ref if char.isdigit())
        if not column or not row_text:
            raise PjmB1Error(f"Unreadable cell reference {ref!r}.")
        value = _cell_value(cell, shared)
        if value is not None:
            cells[(int(row_text), column)] = value
    if not cells:
        raise PjmB1Error(f"{sheet_name} has no cells.")
    return cells


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall(f"{_MAIN}si"):
        strings.append("".join(node.text or "" for node in item.iter(f"{_MAIN}t")))
    return strings


def _sheet_target(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in relationships.findall(f"{_PKG_REL}Relationship")
    }
    for sheet in workbook.findall(f"{_MAIN}sheets/{_MAIN}sheet"):
        if sheet.attrib.get("name") != sheet_name:
            continue
        relation_id = sheet.attrib.get(_REL + "id")
        if relation_id is None or relation_id not in targets:
            raise PjmB1Error(f"{sheet_name} has no workbook relationship.")
        target = targets[relation_id].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        return target
    raise PjmB1Error(f"Workbook has no sheet named {sheet_name!r}.")


def _cell_value(cell: ET.Element, shared: Sequence[str]) -> object | None:
    kind = cell.attrib.get("t")
    value = cell.find(f"{_MAIN}v")
    inline = cell.find(f"{_MAIN}is")
    if kind == "s":
        if value is None or value.text is None:
            raise PjmB1Error("Shared-string cell has no index.")
        try:
            return shared[int(value.text)]
        except (ValueError, IndexError) as exc:
            raise PjmB1Error(f"Shared-string index {value.text!r} is invalid.") from exc
    if kind == "inlineStr":
        if inline is None:
            return None
        return "".join(node.text or "" for node in inline.iter(f"{_MAIN}t"))
    if kind == "b":
        raise PjmB1Error("Boolean cell is not a Table B1 number or label.")
    if value is None or value.text is None:
        return None
    try:
        return float(value.text)
    except ValueError as exc:
        raise PjmB1Error(f"Numeric cell {value.text!r} is not a number.") from exc


def _header_columns(
    cells: Mapping[tuple[int, str], object],
) -> tuple[int, list[tuple[int, str]], str]:
    rows = sorted({row for row, _column in cells})
    header_rows = [row for row in rows if _looks_like_header(cells, row)]
    if len(header_rows) != 1:
        raise PjmB1Error(
            f"Expected one Table B1 header row, found {len(header_rows)}."
        )
    header_row = header_rows[0]
    columns = sorted(
        (column for row, column in cells if row == header_row),
        key=_column_index,
    )
    year_columns: list[tuple[int, str]] = []
    cagr_column: str | None = None
    seen_years: set[int] = set()
    for column in columns:
        value = cells[(header_row, column)]
        if _is_history_header(value):
            continue
        if _is_cagr_header(value):
            if cagr_column is not None:
                raise PjmB1Error("Table B1 has more than one 10-year growth column.")
            cagr_column = column
            continue
        year = _forecast_year(value)
        if year is None:
            continue
        if year in seen_years:
            raise PjmB1Error(f"Duplicate forecast-year header {year}.")
        seen_years.add(year)
        year_columns.append((year, column))
    if not year_columns:
        raise PjmB1Error("Table B1 header has no forecast-year columns.")
    if cagr_column is None:
        raise PjmB1Error("Table B1 header has no 10-year growth column.")
    return header_row, year_columns, cagr_column


def _looks_like_header(cells: Mapping[tuple[int, str], object], row: int) -> bool:
    values = [cells[(row, column)] for candidate, column in cells if candidate == row]
    has_history = any(_is_history_header(value) for value in values)
    has_cagr = any(_is_cagr_header(value) for value in values)
    has_year = any(_forecast_year(value) is not None for value in values)
    return has_history and has_cagr and has_year


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
        if label is None or _is_non_zone_label(label):
            continue
        if label not in _EXPECTED_ZONES:
            raise PjmB1Error(f"Unexpected Table B1 zone code {label!r}.")
        if label in seen:
            raise PjmB1Error(f"Duplicate Table B1 zone code {label}.")
        seen.add(label)
        found.append((label, row))
    return found


def _require_exact_zones(zone_rows: Sequence[tuple[str, int]]) -> None:
    found = [zone for zone, _row in zone_rows]
    missing = [zone for zone in EXPECTED_B1_ZONE_CODES if zone not in found]
    if missing:
        raise PjmB1Error("Table B1 is missing zone codes: " + ", ".join(missing))
    if found != list(EXPECTED_B1_ZONE_CODES):
        raise PjmB1Error("Table B1 zone codes are not the verified 22-code list.")


def _label_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.replace("\xa0", " ").strip()
    return text or None


def _is_non_zone_label(label: str) -> bool:
    if label in _NON_ZONE_LABELS:
        return True
    return label.startswith("Summer Peak Load (MW)")


def _is_history_header(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.lower()
    return "metered" in text or "unrestricted" in text


def _is_cagr_header(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = " ".join(value.lower().split())
    return "annual" in text and "growth rate" in text and "10 yr" in text


def _forecast_year(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and float(value).is_integer():
        year = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        year = int(value.strip())
    else:
        return None
    if 1900 <= year <= 2200:
        return year
    return None


def _require_number(value: object, context: str) -> float:
    if isinstance(value, bool) or value is None:
        raise PjmB1Error(f"{context} is missing.")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if text == "" or "%" in text or "," in text:
            raise PjmB1Error(f"{context} is not a plain number: {value!r}.")
        try:
            number = float(text)
        except ValueError as exc:
            raise PjmB1Error(f"{context} is not a plain number: {value!r}.") from exc
    else:
        raise PjmB1Error(f"{context} is not a plain number: {value!r}.")
    if not math.isfinite(number):
        raise PjmB1Error(f"{context} is not a finite number.")
    return number


def _require_manifest_provenance(row: B1Row) -> None:
    try:
        source = source_for_vintage(row.ltlf_vintage_year)
    except KeyError as exc:
        raise PjmB1Error(
            f"Vintage {row.ltlf_vintage_year} is not a Slice 1 Tables source."
        ) from exc
    if row.pjm_zone not in _EXPECTED_ZONES:
        raise PjmB1Error(f"Unexpected Table B1 zone code {row.pjm_zone!r}.")
    if row.original_release_date != source.original_release_date:
        raise PjmB1Error(
            f"{row.ltlf_vintage_year} original_release_date does not match the manifest."
        )
    if row.revision_date != source.revision_date:
        raise PjmB1Error(
            f"{row.ltlf_vintage_year} revision_date does not match the manifest."
        )
    if row.vintage_available_at != source.vintage_available_at:
        raise PjmB1Error(
            f"{row.ltlf_vintage_year} vintage_available_at does not match the manifest."
        )
    if row.source_url != source.source_url or row.source_file != source.source_file:
        raise PjmB1Error(
            f"{row.ltlf_vintage_year} source URL or filename does not match the manifest."
        )


def _require_date(value: date | datetime | str | None, field_name: str) -> date:
    if value is None or value == "":
        raise PjmB1Error(f"{field_name} is missing.")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise PjmB1Error(f"{field_name} is not an ISO date: {value!r}.") from exc
    raise PjmB1Error(f"{field_name} is not a date: {value!r}.")


def _column_index(letters: str) -> int:
    index = 0
    for char in letters:
        index = index * 26 + ord(char.upper()) - 64
    return index

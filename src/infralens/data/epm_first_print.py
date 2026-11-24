"""Read first-print commercial prices from archived EPM issues (Phase 2 criterion 5).

This is the Tier 2 "reconstructed first-print" source in the 2026-11-23 vintage
policy (``DECISIONS.md``). Each Electric Power Monthly (EPM) issue carries its
reference month two calendar months later, in Table 5.6.A. The parser reads the
commercial column for five states and never synthesizes, back-fills, or corrects
a value. A missing value is returned as a recorded gap.

Reference months from 2024-07 on are refused before any worksheet is opened.
Issues after the window are used for publication timing only, through
:func:`price_table_metadata`, which reads the workbook's ``docProps/core.xml``
and no worksheet.
"""

from __future__ import annotations

import calendar
import hashlib
import io
import re
import statistics
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree as ET

FIRST_REFERENCE_MONTH = "2012-05"
LAST_REFERENCE_MONTH = "2024-06"
FIRST_REFUSED_REFERENCE_MONTH = "2024-07"
LAST_TIMING_REFERENCE_MONTH = "2026-07"
ISSUE_LAG_MONTHS = 2
STATE_NAMES = {
    "VA": "Virginia",
    "PA": "Pennsylvania",
    "OH": "Ohio",
    "MD": "Maryland",
    "NJ": "New Jersey",
}

_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_MONTH_LABEL = re.compile(r"^([A-Za-z]+)\s+(\d{4})$")
_TABLE_NAME = re.compile(r"^table_5_0?6_a\.xlsx$", re.IGNORECASE)
_CELL = re.compile(r"^([A-Z]+)(\d+)$")
_FINAL_NOTE = re.compile(r"values for (\d{4}) are final", re.IGNORECASE)
_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DOC_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_DCTERMS = "http://purl.org/dc/terms/"
_MAX_XML_BYTES = 16_000_000
_MAX_TABLE_BYTES = 5_000_000
_ROUNDING_TOLERANCE = Decimal("0.000001")
_CENT = Decimal("0.01")


class ReferenceMonthRefused(ValueError):
    """The reference month is outside the approved first-print window."""


class TableLayoutError(ValueError):
    """The table does not have the layout or months this parser can verify."""


@dataclass(frozen=True)
class FirstPrintRecord:
    """One state-month from one issue. ``price`` is None when ``gap_reason`` is set."""

    state: str
    reference_month: str
    issue_month: str
    table_name: str
    table_sha256: str
    cell: str
    raw_value: str | None
    price_cents_per_kwh: float | None
    gap_reason: str | None
    year_ago_month: str
    year_ago_cell: str
    year_ago_raw_value: str | None
    year_ago_price_cents_per_kwh: float | None
    year_ago_gap_reason: str | None

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


def _month_parts(month: str) -> tuple[int, int]:
    match = _MONTH.match(month)
    if match is None:
        raise ValueError(f"Expected a YYYY-MM month, got {month!r}")
    return int(match.group(1)), int(match.group(2))


def add_months(month: str, count: int) -> str:
    year, number = _month_parts(month)
    total = year * 12 + (number - 1) + count
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def reference_month_for_issue(issue_month: str) -> str:
    return add_months(issue_month, -ISSUE_LAG_MONTHS)


def issue_month_for_reference(reference_month: str) -> str:
    return add_months(reference_month, ISSUE_LAG_MONTHS)


def month_range(first: str, last: str) -> list[str]:
    months = [first]
    while months[-1] < last:
        months.append(add_months(months[-1], 1))
    return months


def first_print_issue_months() -> list[str]:
    """The 146 issues that carry reference months 2012-05 to 2024-06."""

    return [issue_month_for_reference(month) for month in month_range(FIRST_REFERENCE_MONTH, LAST_REFERENCE_MONTH)]


def timing_issue_months() -> list[str]:
    """The 171 issues used for timing, reference months 2012-05 to 2026-07."""

    return [issue_month_for_reference(month) for month in month_range(FIRST_REFERENCE_MONTH, LAST_TIMING_REFERENCE_MONTH)]


def issue_archive_stem(issue_month: str) -> str:
    year, number = _month_parts(issue_month)
    return f"{calendar.month_name[number].lower()}{year}"


def refuse_reference_month(reference_month: str) -> None:
    """Raise unless the month is inside the approved 2012-05 to 2024-06 window."""

    _month_parts(reference_month)
    if reference_month >= FIRST_REFUSED_REFERENCE_MONTH:
        raise ReferenceMonthRefused(
            f"Reference month {reference_month} is on or after {FIRST_REFUSED_REFERENCE_MONTH} and is not parsed."
        )
    if reference_month < FIRST_REFERENCE_MONTH:
        raise ReferenceMonthRefused(f"Reference month {reference_month} is before {FIRST_REFERENCE_MONTH}.")


def _read_xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    info = archive.getinfo(name)
    if info.file_size > _MAX_XML_BYTES:
        raise TableLayoutError(f"{name} is larger than the parser allows.")
    data = archive.read(info)
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise TableLayoutError(f"{name} declares a DTD or entity.")
    return ET.fromstring(data)


def find_price_table_name(names: list[str]) -> str:
    """The issue's one Table 5.6.A workbook. Some issues keep their tables in a folder."""

    matches = [name for name in names if _TABLE_NAME.match(name.rsplit("/", 1)[-1])]
    if len(matches) != 1:
        raise TableLayoutError(f"Expected one Table 5.6.A workbook, found {len(matches)}.")
    return matches[0]


def read_price_table(issue_zip: Any) -> tuple[str, bytes, zipfile.ZipInfo]:
    """Return the Table 5.6.A workbook's name, bytes, and ZIP entry. Nothing is extracted to disk."""

    with zipfile.ZipFile(issue_zip) as archive:
        name = find_price_table_name(archive.namelist())
        info = archive.getinfo(name)
        if info.file_size > _MAX_TABLE_BYTES:
            raise TableLayoutError(f"{name} is larger than the parser allows.")
        return name, archive.read(info), info


def _utc_text(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise TableLayoutError(f"Workbook timestamp has no time zone: {value!r}")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def price_table_metadata(issue_zip: Any) -> dict[str, Any]:
    """Fingerprint and timestamps of the price table. Reads no worksheet."""

    name, table, info = read_price_table(issue_zip)
    with zipfile.ZipFile(io.BytesIO(table)) as workbook:
        core = _read_xml(workbook, "docProps/core.xml")
    created = core.findtext(f"{{{_DCTERMS}}}created")
    modified = core.findtext(f"{{{_DCTERMS}}}modified")
    return {
        "name": name,
        "sha256": hashlib.sha256(table).hexdigest(),
        "size_bytes": len(table),
        "zip_entry_timestamp_local": datetime(*info.date_time).isoformat(),
        "internal_created_utc": _utc_text(created),
        "internal_modified_utc": _utc_text(modified),
    }


def _cell_text(cell: ET.Element, shared: list[str]) -> str | None:
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{_MAIN}}}t"))
    value = cell.find(f"{{{_MAIN}}}v")
    if value is None or value.text is None:
        return None
    if kind == "s":
        index = int(value.text)
        if not 0 <= index < len(shared):
            raise TableLayoutError(f"Shared string {index} is out of range.")
        return shared[index]
    return value.text


def _read_rows(table: bytes) -> dict[int, dict[str, str]]:
    try:
        workbook = zipfile.ZipFile(io.BytesIO(table))
    except zipfile.BadZipFile as exc:
        raise TableLayoutError("The price table is not a readable workbook.") from exc
    with workbook:
        names = set(workbook.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for item in _read_xml(workbook, "xl/sharedStrings.xml"):
                shared.append("".join(node.text or "" for node in item.iter(f"{{{_MAIN}}}t")))
        sheets = _read_xml(workbook, "xl/workbook.xml").find(f"{{{_MAIN}}}sheets")
        if sheets is None or len(sheets) != 1:
            raise TableLayoutError("Expected exactly one worksheet in the price table.")
        relation = sheets[0].attrib.get(f"{{{_DOC_RELS}}}id")
        targets = {
            item.attrib.get("Id"): item.attrib.get("Target", "")
            for item in _read_xml(workbook, "xl/_rels/workbook.xml.rels").findall(f"{{{_RELS}}}Relationship")
        }
        target = targets.get(relation, "")
        path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        if path not in names:
            raise TableLayoutError("The worksheet part is missing.")
        data = _read_xml(workbook, path).find(f"{{{_MAIN}}}sheetData")
    if data is None:
        raise TableLayoutError("The worksheet has no data.")
    rows: dict[int, dict[str, str]] = {}
    for cell in data.iter(f"{{{_MAIN}}}c"):
        match = _CELL.match(cell.attrib.get("r", ""))
        if match is None:
            raise TableLayoutError("A cell has no usable reference.")
        text = _cell_text(cell, shared)
        if text is not None:
            rows.setdefault(int(match.group(2)), {})[match.group(1)] = text
    return rows


def _normal(text: str | None) -> str:
    return " ".join((text or "").split()).casefold()


def _next_column(column: str) -> str:
    number = 0
    for letter in column:
        number = number * 26 + ord(letter) - 64
    number += 1
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _label_month(label: str | None) -> str:
    match = _MONTH_LABEL.match(" ".join((label or "").split()))
    if match is None:
        raise TableLayoutError(f"Unreadable month header: {label!r}")
    names = {name.casefold(): index for index, name in enumerate(calendar.month_name) if name}
    number = names.get(match.group(1).casefold())
    if number is None:
        raise TableLayoutError(f"Unreadable month header: {label!r}")
    return f"{match.group(2)}-{number:02d}"


def _locate_commercial(rows: dict[int, dict[str, str]]) -> tuple[int, str, str]:
    found = [
        (number, column)
        for number in sorted(rows)[:12]
        for column, text in rows[number].items()
        if _normal(text) == "commercial"
    ]
    if len(found) != 1:
        raise TableLayoutError(f"Expected one Commercial header, found {len(found)}.")
    band_row, column = found[0]
    return band_row + 1, column, _next_column(column)


def _parse_value(raw: str | None) -> tuple[float | None, str | None]:
    if raw is None or not raw.strip():
        return None, "empty_cell"
    try:
        number = Decimal(raw.strip())
    except InvalidOperation:
        return None, f"non_numeric_cell:{raw.strip()[:20]}"
    if not number.is_finite():
        return None, f"non_numeric_cell:{raw.strip()[:20]}"
    if number <= 0:
        return None, f"non_positive_cell:{raw.strip()[:20]}"
    rounded = number.quantize(_CENT)
    if abs(number - rounded) > _ROUNDING_TOLERANCE:
        return None, f"more_than_two_decimals:{raw.strip()[:24]}"
    return float(rounded), None


def parse_price_table(table: bytes, issue_month: str, table_name: str) -> list[FirstPrintRecord]:
    """Parse the five states' commercial prices from one in-window issue.

    The issue's month and the sheet's own column headers must agree, so a
    misnamed or shifted file is refused rather than read as another month.
    """

    reference_month = reference_month_for_issue(issue_month)
    refuse_reference_month(reference_month)
    rows = _read_rows(table)
    title = " ".join(rows.get(number, {}).get("A", "") for number in (1, 2)).casefold()
    if "5.6.a" not in title or "cents per kilowatthour" not in title:
        raise TableLayoutError("The sheet title does not identify Table 5.6.A in cents per kilowatthour.")
    header_row, column, year_ago_column = _locate_commercial(rows)
    header = rows.get(header_row, {})
    shown = _label_month(header.get(column))
    refuse_reference_month(shown)
    if shown != reference_month:
        raise TableLayoutError(f"Issue {issue_month} should show {reference_month}, but its header shows {shown}.")
    year_ago_month = add_months(reference_month, -12)
    if _label_month(header.get(year_ago_column)) != year_ago_month:
        raise TableLayoutError(f"Issue {issue_month} has no {year_ago_month} year-ago column.")
    label_columns = [name for name, text in header.items() if _normal(text) == "census division and state"]
    if len(label_columns) != 1:
        raise TableLayoutError("Expected one Census Division and State column.")
    table_sha256 = hashlib.sha256(table).hexdigest()
    records = []
    for state, name in STATE_NAMES.items():
        matches = [
            number
            for number in sorted(rows)
            if number > header_row and _normal(rows[number].get(label_columns[0])) == name.casefold()
        ]
        if len(matches) != 1:
            raise TableLayoutError(f"Expected one row for {name}, found {len(matches)}.")
        row = rows[matches[0]]
        raw, year_ago_raw = row.get(column), row.get(year_ago_column)
        price, gap = _parse_value(raw)
        year_ago_price, year_ago_gap = _parse_value(year_ago_raw)
        records.append(
            FirstPrintRecord(
                state=state,
                reference_month=reference_month,
                issue_month=issue_month,
                table_name=table_name,
                table_sha256=table_sha256,
                cell=f"{column}{matches[0]}",
                raw_value=raw,
                price_cents_per_kwh=price,
                gap_reason=gap,
                year_ago_month=year_ago_month,
                year_ago_cell=f"{year_ago_column}{matches[0]}",
                year_ago_raw_value=year_ago_raw,
                year_ago_price_cents_per_kwh=year_ago_price,
                year_ago_gap_reason=year_ago_gap,
            )
        )
    return records


def final_data_years(table: bytes, issue_month: str) -> dict[int, str]:
    """Data years this in-window issue's notes label final, with the note's cell."""

    refuse_reference_month(reference_month_for_issue(issue_month))
    found: dict[int, str] = {}
    for number, row in sorted(_read_rows(table).items()):
        for match in _FINAL_NOTE.finditer(" ".join(row.get("A", "").split())):
            found.setdefault(int(match.group(1)), f"A{number}")
    return found


def parse_issue(issue_zip: Any, issue_month: str) -> list[FirstPrintRecord]:
    """Parse one issue ZIP. An out-of-window month is refused before the ZIP is opened."""

    refuse_reference_month(reference_month_for_issue(issue_month))
    name, table, _ = read_price_table(issue_zip)
    return parse_price_table(table, issue_month, name)


def _month_end(month: str) -> date:
    year, number = _month_parts(month)
    return date(year, number, calendar.monthrange(year, number)[1])


def _utc_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).date()


def timing_row(issue: dict[str, Any]) -> dict[str, Any]:
    """One release-level timing row. Every date is a file-date proxy, not a release log."""

    reference = issue["reference_month"]
    month_end = _month_end(reference)
    m3 = add_months(reference, 3)
    year, number = _month_parts(m3)
    day_one, mid_month, m3_end = date(year, number, 1), date(year, number, 15), _month_end(m3)
    zip_date = _utc_date(issue["server_last_modified_utc"])
    pdf_date = _utc_date(issue.get("pdf_server_last_modified_utc"))
    table_date = _utc_date(issue["price_table"]["internal_modified_utc"])
    if zip_date is None or table_date is None:
        raise ValueError(f"Issue {issue['issue_month']} is missing a file date.")
    earliest = min(item for item in (zip_date, pdf_date) if item is not None)
    return {
        "issue_month": issue["issue_month"],
        "reference_month": reference,
        "reference_month_basis": issue["reference_month_basis"],
        "zip_server_date_proxy": zip_date.isoformat(),
        "pdf_server_date_proxy": pdf_date.isoformat() if pdf_date else "",
        "table_internal_date_proxy": table_date.isoformat(),
        "earliest_public_file_date_proxy": earliest.isoformat(),
        "m3_day_1": day_one.isoformat(),
        "m3_mid_month": mid_month.isoformat(),
        "m3_month_end": m3_end.isoformat(),
        "days_month_end_to_zip": (zip_date - month_end).days,
        "days_day_1_to_table": (table_date - day_one).days,
        "days_day_1_to_earliest_public": (earliest - day_one).days,
        "zip_on_or_after_day_1": zip_date >= day_one,
        "table_on_or_after_day_1": table_date >= day_one,
        "earliest_public_after_day_1": earliest > day_one,
        "earliest_public_after_mid_month": earliest > mid_month,
        "earliest_public_after_month_end": earliest > m3_end,
    }


def timing_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Release-level m+3 results for month-end and mid-month forecast origins."""

    lags = [row["days_month_end_to_zip"] for row in rows]
    ordered = sorted(lags)
    table_late = [row["days_day_1_to_table"] for row in rows if row["table_on_or_after_day_1"]]
    public_late = [row["days_day_1_to_earliest_public"] for row in rows if row["earliest_public_after_day_1"]]
    mid_late = [row for row in rows if row["earliest_public_after_mid_month"]]
    end_late = [row for row in rows if row["earliest_public_after_month_end"]]
    return {
        "issues": len(rows),
        "days_month_end_to_zip": {
            "min": ordered[0],
            "median": statistics.median(ordered),
            "p75": ordered[max(0, (75 * len(ordered) + 99) // 100 - 1)],
            "max": ordered[-1],
        },
        "zip_on_or_after_day_1": sum(row["zip_on_or_after_day_1"] for row in rows),
        "table_on_or_after_day_1": len(table_late),
        "table_max_days_after_day_1": max(table_late, default=0),
        "earliest_public_after_day_1": len(public_late),
        "earliest_public_max_days_after_day_1": max(public_late, default=0),
        "mid_month_origin_failures": len(mid_late),
        "mid_month_failure_issues": [row["issue_month"] for row in mid_late],
        "month_end_origin_failures": len(end_late),
        "month_end_failure_issues": [row["issue_month"] for row in end_late],
    }


__all__ = [
    "FIRST_REFERENCE_MONTH",
    "FIRST_REFUSED_REFERENCE_MONTH",
    "LAST_REFERENCE_MONTH",
    "LAST_TIMING_REFERENCE_MONTH",
    "STATE_NAMES",
    "FirstPrintRecord",
    "ReferenceMonthRefused",
    "TableLayoutError",
    "add_months",
    "final_data_years",
    "find_price_table_name",
    "first_print_issue_months",
    "issue_archive_stem",
    "issue_month_for_reference",
    "month_range",
    "parse_issue",
    "parse_price_table",
    "price_table_metadata",
    "read_price_table",
    "reference_month_for_issue",
    "refuse_reference_month",
    "timing_issue_months",
    "timing_row",
    "timing_summary",
]

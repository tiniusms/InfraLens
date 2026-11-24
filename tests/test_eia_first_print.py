"""First-print parser, refusal window, and metadata (Phase 2 criterion 5, PR B).

These tests never skip and use no network. Workbooks are synthetic and built in
memory. Real-data checks run through ``scripts/eia_first_print.py`` and are
recorded in ``docs/eia_vintage_research.md``.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import re
import subprocess
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import httpx
import pandas as pd
import pytest

from infralens.data import repository_root
from infralens.data.epm_first_print import (
    FirstPrintRecord,
    ReferenceMonthRefused,
    TableLayoutError,
    add_months,
    find_price_table_name,
    first_print_issue_months,
    issue_archive_stem,
    parse_issue,
    parse_price_table,
    price_table_metadata,
    reference_month_for_issue,
    refuse_reference_month,
    timing_issue_months,
    timing_row,
    timing_summary,
)

_ROOT = repository_root()
_spec = importlib.util.spec_from_file_location("eia_first_print", _ROOT / "scripts" / "eia_first_print.py")
assert _spec is not None and _spec.loader is not None
first_print_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(first_print_tool)

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_NAMES = "January February March April May June July August September October November December".split()
_STATE_ROWS = {"New Jersey": 13, "Pennsylvania": 15, "Ohio": 20, "Maryland": 35, "Virginia": 38}
_PRICES = {
    "New Jersey": ("13.57", "13.5"),
    "Pennsylvania": ("8.76", "8.44"),
    "Ohio": ("9.8699999999999992", "9.4700000000000006"),
    "Maryland": ("10.02", "9.56"),
    "Virginia": ("7.66", "7.61"),
}


class Number(str):
    """A cell written as a numeric value with these exact digits."""


def _label(month: str) -> str:
    return f"{_MONTH_NAMES[int(month[5:]) - 1]} {month[:4]}"


def _table_rows(reference: str, prices: dict[str, tuple[str, str]] | None = None) -> dict[int, dict[str, str]]:
    now, before = _label(reference), _label(add_months(reference, -12))
    rows: dict[int, dict[str, str]] = {
        1: {"A": "Table 5.6.A. Average Price of Electricity to Ultimate Customers by End-Use Sector,"},
        2: {"A": f"by State, {now} and {before[-4:]} (Cents per Kilowatthour)"},
        3: {"B": "Residential", "D": "Commercial", "F": "Industrial"},
        4: {"A": "Census Division\nand State", "B": now, "C": before, "D": now, "E": before, "F": now, "G": before},
        5: {"A": "New England", "B": Number("20.71"), "D": Number("16.170000000000002"), "E": Number("15.4")},
    }
    for name, row in _STATE_ROWS.items():
        current, year_ago = (prices or _PRICES)[name]
        rows[row] = {"A": name, "B": Number("12.5"), "C": Number("12.1"), "D": Number(current), "E": Number(year_ago)}
    return rows


def _workbook(
    rows: dict[int, dict[str, str]],
    *,
    inline: bool = False,
    absolute_target: bool = False,
    sheet_xml: bytes | None = None,
    modified: str = "2020-05-26T16:08:04Z",
) -> bytes:
    shared: list[str] = []
    body = []
    for number in sorted(rows):
        cells = []
        for column in sorted(rows[number], key=lambda item: (len(item), item)):
            value = rows[number][column]
            reference = f"{column}{number}"
            if isinstance(value, Number):
                cells.append(f'<c r="{reference}"><v>{value}</v></c>')
            elif inline:
                cells.append(f'<c r="{reference}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
            else:
                shared.append(value)
                cells.append(f'<c r="{reference}" t="s"><v>{len(shared) - 1}</v></c>')
        body.append(f'<row r="{number}">{"".join(cells)}</row>')
    sheet = f'<worksheet xmlns="{_MAIN}"><sheetData>{"".join(body)}</sheetData></worksheet>'.encode()
    strings = "".join(f"<si><t>{escape(item)}</t></si>" for item in shared)
    target = "/xl/worksheets/sheet1.xml" if absolute_target else "worksheets/sheet1.xml"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{_MAIN}" xmlns:r="{_DOC}"><sheets>'
            '<sheet name="Table_5_06_A" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{_PACKAGE}"><Relationship Id="rId1" Target="{target}" '
            f'Type="{_DOC}/worksheet"/></Relationships>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml if sheet_xml is not None else sheet)
        if not inline:
            archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="{_MAIN}">{strings}</sst>')
        archive.writestr(
            "docProps/core.xml",
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{modified}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{modified}</dcterms:modified>'
            "</cp:coreProperties>",
        )
    return buffer.getvalue()


def _issue_zip(table: bytes, name: str = "Table_5_06_A.xlsx") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Table_1_01.xlsx", b"not read")
        info = zipfile.ZipInfo(name, date_time=(2020, 5, 26, 12, 8, 6))
        archive.writestr(info, table)
    return buffer.getvalue()


def _shifted_rows(reference: str) -> dict[int, dict[str, str]]:
    """An equivalent layout: an extra top row and the Commercial block two columns right."""

    moved: dict[int, dict[str, str]] = {1: {"A": "Table 5.6.A. Average Price of Electricity (Cents per Kilowatthour)"}}
    moved[2] = {"A": "by State"}
    for number, row in _table_rows(reference).items():
        if number < 3:
            continue
        shifted = {}
        for column, value in row.items():
            shifted[column if column == "A" else chr(ord(column) + 2)] = value
        moved[number + 1] = shifted
    return moved


@pytest.mark.parametrize(
    ("build", "cell", "year_ago_cell", "row_offset"),
    [
        (lambda: _workbook(_table_rows("2020-03")), "D", "E", 0),
        (lambda: _workbook(_table_rows("2020-03"), inline=True), "D", "E", 0),
        (lambda: _workbook(_table_rows("2020-03"), absolute_target=True), "D", "E", 0),
        (lambda: _workbook(_shifted_rows("2020-03")), "F", "G", 1),
    ],
    ids=["shared-strings", "inline-strings", "absolute-sheet-target", "shifted-equivalent"],
)
def test_parser_reads_each_workbook_layout(build, cell: str, year_ago_cell: str, row_offset: int) -> None:
    table = build()
    records = {item.state: item for item in parse_price_table(table, "2020-05", "Table_5_06_A.xlsx")}
    assert set(records) == {"VA", "PA", "OH", "MD", "NJ"}
    ohio = records["OH"]
    assert ohio.price_cents_per_kwh == 9.87 and ohio.raw_value == "9.8699999999999992"
    assert ohio.year_ago_price_cents_per_kwh == 9.47 and ohio.year_ago_month == "2019-03"
    assert (ohio.cell, ohio.year_ago_cell) == (f"{cell}{20 + row_offset}", f"{year_ago_cell}{20 + row_offset}")
    assert records["VA"].price_cents_per_kwh == 7.66
    assert all(item.gap_reason is None and item.reference_month == "2020-03" for item in records.values())
    assert all(len(item.table_sha256) == 64 for item in records.values())


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("--", "non_numeric_cell:--"),
        ("W", "non_numeric_cell:W"),
        ("*", "non_numeric_cell:*"),
        ("NaN", "non_numeric_cell:NaN"),
        ("0", "non_positive_cell:0"),
        ("-1.2", "non_positive_cell:-1.2"),
        ("9.876", "more_than_two_decimals:9.876"),
    ],
)
def test_unusable_value_is_a_gap_and_is_never_filled(raw: str, reason: str) -> None:
    prices = {**_PRICES, "Maryland": (raw, "9.56")}
    rows = _table_rows("2020-03", prices)
    if not re.fullmatch(r"-?[\d.]+", raw):
        rows[35]["D"] = raw
    records = {item.state: item for item in parse_price_table(_workbook(rows), "2020-05", "t.xlsx")}
    assert records["MD"].price_cents_per_kwh is None
    assert records["MD"].gap_reason == reason
    assert records["MD"].year_ago_price_cents_per_kwh == 9.56
    assert records["VA"].price_cents_per_kwh == 7.66


def test_an_empty_cell_is_a_gap() -> None:
    rows = _table_rows("2020-03")
    del rows[35]["D"]
    records = {item.state: item for item in parse_price_table(_workbook(rows), "2020-05", "t.xlsx")}
    assert (records["MD"].price_cents_per_kwh, records["MD"].gap_reason) == (None, "empty_cell")


@pytest.mark.parametrize("reference", ["2024-07", "2024-08", "2025-06", "2026-07", "2030-01"])
def test_reference_months_from_2024_07_are_refused_before_the_file_is_opened(reference: str, tmp_path: Path) -> None:
    issue = add_months(reference, 2)
    with pytest.raises(ReferenceMonthRefused):
        refuse_reference_month(reference)
    with pytest.raises(ReferenceMonthRefused):
        parse_issue(tmp_path / "does-not-exist.zip", issue)
    with pytest.raises(ReferenceMonthRefused):
        parse_price_table(b"not a workbook", issue, "t.xlsx")


def test_window_boundaries() -> None:
    refuse_reference_month("2012-05")
    refuse_reference_month("2024-06")
    with pytest.raises(ReferenceMonthRefused):
        refuse_reference_month("2012-04")
    records = parse_price_table(_workbook(_table_rows("2024-06")), "2024-08", "t.xlsx")
    assert {item.reference_month for item in records} == {"2024-06"}


def test_an_in_window_issue_whose_header_shows_a_refused_month_returns_nothing() -> None:
    table = _workbook(_table_rows("2024-07"))
    with pytest.raises(ReferenceMonthRefused):
        parse_price_table(table, "2024-08", "t.xlsx")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda rows: rows[4].__setitem__("D", "April 2020"), "header shows"),
        (lambda rows: rows[4].__setitem__("E", "March 2018"), "year-ago"),
        (lambda rows: rows[4].__setitem__("D", "Spring 2020"), "Unreadable month"),
        (lambda rows: rows[3].pop("D"), "Commercial header"),
        (lambda rows: rows[3].__setitem__("F", "Commercial"), "Commercial header"),
        (lambda rows: rows.pop(38), "row for Virginia"),
        (lambda rows: rows.__setitem__(39, {"A": "Virginia", "D": Number("7.1"), "E": Number("7.2")}), "row for Virginia"),
        (lambda rows: rows[2].__setitem__("A", "by State (Dollars)"), "cents per kilowatthour"),
        (lambda rows: rows[1].__setitem__("A", "Table 5.6.B. Year to date"), "Table 5.6.A"),
        (lambda rows: rows[4].__setitem__("A", "State"), "Census Division"),
    ],
)
def test_changed_layouts_are_refused_not_guessed(change, message: str) -> None:
    rows = _table_rows("2020-03")
    change(rows)
    with pytest.raises(TableLayoutError, match=message):
        parse_price_table(_workbook(rows), "2020-05", "t.xlsx")


def test_unreadable_or_unsafe_workbooks_are_refused() -> None:
    with pytest.raises(TableLayoutError):
        parse_price_table(b"not a workbook", "2020-05", "t.xlsx")
    unsafe = b'<!DOCTYPE x [<!ENTITY a "b">]><worksheet xmlns="' + _MAIN.encode() + b'"><sheetData/></worksheet>'
    with pytest.raises(TableLayoutError, match="DTD"):
        parse_price_table(_workbook(_table_rows("2020-03"), sheet_xml=unsafe), "2020-05", "t.xlsx")


def test_table_name_must_be_unique_in_either_archive_layout() -> None:
    assert find_price_table_name(["Table_1_01.xlsx", "Table_5_06_A.xlsx"]) == "Table_5_06_A.xlsx"
    assert find_price_table_name(["XLS/", "XLS/Table_5_06_A.xlsx", "XLS/Table_5_06_B.xlsx"]) == "XLS/Table_5_06_A.xlsx"
    assert find_price_table_name(["table_5_6_a.XLSX"]) == "table_5_6_a.XLSX"
    for names in (["Table_5_06_B.xlsx"], ["XLS/._Table_5_06_A.xlsx"], ["Table_5_06_A.xlsx", "XLS/Table_5_6_A.xlsx"]):
        with pytest.raises(TableLayoutError):
            find_price_table_name(names)


def test_timing_metadata_reads_no_worksheet() -> None:
    table = _workbook(_table_rows("2026-07"), sheet_xml=b"this worksheet must never be parsed")
    metadata = price_table_metadata(io.BytesIO(_issue_zip(table)))
    assert metadata["name"] == "Table_5_06_A.xlsx"
    assert metadata["internal_modified_utc"] == "2020-05-26T16:08:04Z"
    assert metadata["zip_entry_timestamp_local"] == "2020-05-26T12:08:06"
    assert _SHA.match(metadata["sha256"]) and metadata["size_bytes"] == len(table)


def test_month_helpers_and_issue_lists() -> None:
    assert reference_month_for_issue("2012-07") == "2012-05"
    assert add_months("2023-12", 1) == "2024-01"
    assert issue_archive_stem("2024-08") == "august2024"
    parsed, timing = first_print_issue_months(), timing_issue_months()
    assert (len(parsed), parsed[0], parsed[-1]) == (146, "2012-07", "2024-08")
    assert (len(timing), timing[0], timing[-1]) == (171, "2012-07", "2026-09")


def _issue(reference: str, zip_date: str, table_date: str, pdf_date: str | None = None) -> dict:
    return {
        "issue_month": add_months(reference, 2),
        "reference_month": reference,
        "reference_month_basis": "table_header",
        "server_last_modified_utc": f"{zip_date}T17:00:00Z",
        "pdf_server_last_modified_utc": f"{pdf_date}T17:00:00Z" if pdf_date else None,
        "price_table": {"internal_modified_utc": f"{table_date}T16:00:00Z"},
    }


def test_timing_separates_month_end_and_mid_month_origins() -> None:
    rows = [
        timing_row(_issue("2020-01", "2020-03-26", "2020-03-25", "2020-03-26")),
        timing_row(_issue("2020-02", "2020-05-20", "2020-05-18", "2020-05-20")),
        timing_row(_issue("2020-03", "2020-07-02", "2020-06-20")),
    ]
    assert rows[0]["days_month_end_to_zip"] == 55
    assert not rows[0]["earliest_public_after_day_1"]
    assert rows[1]["earliest_public_after_mid_month"] and not rows[1]["earliest_public_after_month_end"]
    assert rows[2]["earliest_public_after_month_end"]
    summary = timing_summary(rows)
    assert summary["issues"] == 3
    assert summary["mid_month_failure_issues"] == ["2020-04", "2020-05"]
    assert summary["month_end_failure_issues"] == ["2020-05"]
    assert summary["table_on_or_after_day_1"] == 2


def test_earliest_public_file_uses_the_earlier_of_zip_and_pdf() -> None:
    row = timing_row(_issue("2020-01", "2020-04-20", "2020-03-25", "2020-03-26"))
    assert row["earliest_public_file_date_proxy"] == "2020-03-26"
    assert row["zip_on_or_after_day_1"] and not row["earliest_public_after_day_1"]


def _record(state: str, month: str, price: float | None, year_ago: float | None) -> dict:
    return FirstPrintRecord(
        state=state,
        reference_month=month,
        issue_month=add_months(month, 2),
        table_name="t.xlsx",
        table_sha256="0" * 64,
        cell="D1",
        raw_value=str(price),
        price_cents_per_kwh=price,
        gap_reason=None if price is not None else "empty_cell",
        year_ago_month=add_months(month, -12),
        year_ago_cell="E1",
        year_ago_raw_value=str(year_ago),
        year_ago_price_cents_per_kwh=year_ago,
        year_ago_gap_reason=None if year_ago is not None else "empty_cell",
    ).as_row()


def test_year_ago_check_reports_differences_and_changes_nothing() -> None:
    frame = pd.DataFrame(
        [
            _record("VA", "2019-03", 8.00, 7.00),
            _record("VA", "2020-03", 8.50, 8.00),
            _record("MD", "2019-03", 9.00, 7.00),
            _record("MD", "2020-03", 9.50, 9.25),
            _record("OH", "2019-03", None, 7.00),
            _record("OH", "2020-03", 9.10, 9.00),
        ]
    )
    before = frame.copy(deep=True)
    result = first_print_tool.year_ago_check(frame)
    assert (result["compared"], result["matched"], result["mismatched"]) == (2, 1, 1)
    assert result["match_rate"] == 0.5
    assert result["mismatches"][0]["state"] == "MD"
    assert result["mismatches"][0]["difference"] == 0.25
    pd.testing.assert_frame_equal(frame, before)


def _mock_client(table: bytes, *, status: int = 200) -> httpx.Client:
    body = _issue_zip(table)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".pdf"):
            return httpx.Response(200, headers={"last-modified": "Tue, 26 May 2020 18:00:00 GMT"})
        return httpx.Response(
            status, content=body, headers={"last-modified": "Tue, 26 May 2020 18:31:24 GMT"}
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_records_metadata_at_download_and_refuses_to_overwrite(tmp_path: Path) -> None:
    moment = datetime(2026, 11, 24, 3, 0, 0, tzinfo=timezone.utc)
    table = _workbook(_table_rows("2020-03"))
    with _mock_client(table) as client:
        entry = first_print_tool.fetch_issue(tmp_path, "2020-05", client, clock=lambda: moment, sleep=lambda _: None)
    _assert_issue_schema(entry)
    assert entry["retrieved_at"] == "2026-11-24T03:00:00Z"
    assert entry["server_last_modified_utc"] == "2020-05-26T18:31:24Z"
    assert entry["pdf_server_last_modified_utc"] == "2020-05-26T18:00:00Z"
    assert entry["source_url"] == "https://www.eia.gov/electricity/monthly/archive/may2020.zip"
    assert (tmp_path / entry["local_path"]).is_file()
    with _mock_client(table) as client, pytest.raises(first_print_tool.FetchError, match="refusing to overwrite"):
        first_print_tool.fetch_issue(tmp_path, "2020-05", client, clock=lambda: moment, sleep=lambda _: None)


def test_failed_fetch_writes_nothing(tmp_path: Path) -> None:
    with _mock_client(_workbook(_table_rows("2020-03")), status=404) as client:
        with pytest.raises(first_print_tool.FetchError, match="404"):
            first_print_tool.fetch_issue(tmp_path, "2020-05", client, sleep=lambda _: None)
    assert not list(tmp_path.rglob("*.zip*"))


def _assert_issue_schema(entry: dict) -> None:
    assert set(entry) == {
        "issue_month",
        "reference_month",
        "reference_month_basis",
        "source_url",
        "local_path",
        "server_last_modified_utc",
        "pdf_url",
        "pdf_server_last_modified_utc",
        "retrieved_at",
        "size_bytes",
        "sha256",
        "price_table",
    }
    assert _MONTH.match(entry["issue_month"]) and entry["reference_month"] == add_months(entry["issue_month"], -2)
    stem = issue_archive_stem(entry["issue_month"])
    assert entry["source_url"] == f"https://www.eia.gov/electricity/monthly/archive/{stem}.zip"
    assert entry["local_path"] == f"data/raw/eia/epm_backissues/{stem}.zip"
    assert _UTC.match(entry["server_last_modified_utc"]) and _UTC.match(entry["retrieved_at"])
    assert _SHA.match(entry["sha256"]) and entry["size_bytes"] > 0
    table = entry["price_table"]
    assert set(table) == {
        "name",
        "sha256",
        "size_bytes",
        "zip_entry_timestamp_local",
        "internal_created_utc",
        "internal_modified_utc",
    }
    assert re.fullmatch(r"([^/]+/)*Table_5_0?6_A\.xlsx", table["name"], re.IGNORECASE)
    assert _SHA.match(table["sha256"]) and table["size_bytes"] > 0
    assert _UTC.match(table["internal_modified_utc"])
    datetime.fromisoformat(table["zip_entry_timestamp_local"])


def test_committed_source_metadata_schema() -> None:
    sources = json.loads((_ROOT / "data" / "epm_backissue_sources.json").read_text(encoding="utf-8"))
    assert sources["metadata_version"] == 1
    assert sources["first_print_window"] == {"first": "2012-05", "last": "2024-06"}
    assert sources["timing_window"] == {"first": "2012-05", "last": "2026-07"}
    issues = sources["issues"]
    assert [item["issue_month"] for item in issues] == timing_issue_months()
    for entry in issues:
        _assert_issue_schema(entry)
        in_window = entry["reference_month"] <= "2024-06"
        expected = "table_header" if in_window else "issue_month_minus_2_not_opened"
        assert entry["reference_month_basis"] == expected


def test_committed_timing_table_holds_dates_only() -> None:
    with (_ROOT / "data" / "epm_publication_timing.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["issue_month"] for row in rows] == timing_issue_months()
    assert not [name for name in rows[0] if "price" in name or "value" in name]
    for row in rows:
        for name, value in row.items():
            if name.endswith("_proxy") or name.startswith("m3_"):
                if value:
                    assert _DATE.match(value), name
                    date.fromisoformat(value)
            elif name.startswith("days_"):
                assert re.fullmatch(r"-?\d+", value), name
            elif name.endswith(("_day_1", "_mid_month", "_month_end")):
                assert value in {"True", "False"}, name
    assert all(row["zip_server_date_proxy"] for row in rows)


def test_committed_year_ago_differences_hold_no_price_level() -> None:
    with (_ROOT / "data" / "epm_year_ago_differences.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert reader.fieldnames == first_print_tool.YEAR_AGO_COLUMNS
    keys = [(row["state"], row["reference_month"]) for row in rows]
    assert rows and len(keys) == len(set(keys))
    for row in rows:
        assert row["state"] in {"VA", "PA", "OH", "MD", "NJ"}
        assert "2012-05" <= row["reference_month"] <= "2023-06"
        assert row["first_print_issue"] == add_months(row["reference_month"], 2)
        assert row["year_ago_issue"] == add_months(row["reference_month"], 14)
        assert row["year_ago_issue"] <= "2024-08"
        assert re.fullmatch(r"-?\d+\.\d{2}", row["difference_cents_per_kwh"])
        assert float(row["difference_cents_per_kwh"]) != 0


def test_first_print_files_stay_local_only() -> None:
    policy = json.loads((_ROOT / "data" / "distribution_policy.json").read_text(encoding="utf-8"))
    section = policy["epm_first_print"]
    assert section["local_only_directories"] == ["data/raw/eia/epm_backissues/", "data/processed/eia_first_print/"]
    assert set(section["committed_files"]) == {
        "data/epm_backissue_sources.json",
        "data/epm_publication_timing.csv",
        "data/epm_year_ago_differences.csv",
    }
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=_ROOT, check=True, capture_output=True).stdout.decode()
    names = [name for name in tracked.split("\0") if name]
    for directory in section["local_only_directories"]:
        assert not [name for name in names if name.startswith(directory)]
        probe = f"{directory}probe.zip"
        ignored = subprocess.run(["git", "check-ignore", "-q", "--no-index", "--", probe], cwd=_ROOT)
        assert ignored.returncode == 0, directory


def test_first_print_command_is_not_part_of_ci() -> None:
    for workflow in (_ROOT / ".github" / "workflows").glob("*.yml"):
        assert "eia_first_print" not in workflow.read_text(encoding="utf-8")

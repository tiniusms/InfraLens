"""Slice 1 tests for PJM Table B1 screening rows."""

from __future__ import annotations

import tempfile
import zipfile
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from data_cache_skips import skip_missing_cache
from infralens.screening.pjm_b1 import (
    B1Row,
    PjmB1Error,
    filter_b1_rows,
    load_slice1_tables,
    parse_table_b1,
    validate_b1_rows,
    write_b1_parquet,
)
from infralens.screening.pjm_sources import (
    EXPECTED_B1_ZONE_CODES,
    TABLE_B1_SOURCES,
    source_for_vintage,
)

_RAW = Path("data/raw/pjm")
_AE_2026_CAGR = float("7.7760890000000004E-4")
_DPL_2026_CAGR = float("-4.9910999999999997E-5")


def test_manifest_dates_follow_the_file_level_rule() -> None:
    source_2025 = source_for_vintage(2025)
    source_2026 = source_for_vintage(2026)
    assert source_2025.original_release_date == date(2025, 1, 24)
    assert source_2025.revision_date is None
    assert source_2025.vintage_available_at == date(2025, 1, 24)
    assert source_2026.original_release_date == date(2026, 1, 14)
    assert source_2026.revision_date == date(2026, 2, 6)
    assert source_2026.vintage_available_at == date(2026, 2, 6)
    assert {source.ltlf_vintage_year for source in TABLE_B1_SOURCES} == {2025, 2026}
    assert len(EXPECTED_B1_ZONE_CODES) == 22


def test_2026_layout_keeps_mw_decimal_cagr_and_drops_history() -> None:
    path = _workbook(
        header_row=7,
        first_zone_row=8,
        growth="percent_text",
        history_year=2025,
    )
    rows = parse_table_b1(path, source_for_vintage(2026))
    _assert_grain(rows, vintage=2026, years=(2026, 2027))
    ae = _zone(rows, "AE")
    assert [row.forecast_year for row in ae] == [2026, 2027]
    assert ae[0].summer_peak_mw == 2563.0
    assert ae[1].summer_peak_mw == -12.5
    assert ae[0].summer_peak_10yr_cagr == _AE_2026_CAGR
    assert ae[1].summer_peak_10yr_cagr == _AE_2026_CAGR
    assert all(row.summer_peak_mw != 99999 for row in rows)
    assert all(row.summer_peak_mw != 88888 for row in rows)
    dpl = _zone(rows, "DPL")
    assert dpl[0].summer_peak_10yr_cagr == _DPL_2026_CAGR
    assert rows[0].original_release_date == date(2026, 1, 14)
    assert rows[0].revision_date == date(2026, 2, 6)
    assert rows[0].vintage_available_at == date(2026, 2, 6)
    assert not hasattr(rows[0], "large_load_adjustment_mw")
    assert not hasattr(rows[0], "has_data_center_adjustment")


def test_2025_layout_does_not_read_the_numeric_growth_row() -> None:
    path = _workbook(
        header_row=7,
        first_zone_row=9,
        growth="numeric",
        history_year=2024,
    )
    rows = parse_table_b1(path, source_for_vintage(2025))
    _assert_grain(rows, vintage=2025, years=(2025, 2026))
    ae = _zone(rows, "AE")
    assert ae[0].summer_peak_mw == 2563.0
    assert ae[0].summer_peak_10yr_cagr == _AE_2026_CAGR
    assert rows[0].revision_date is None
    assert rows[0].vintage_available_at == date(2025, 1, 24)
    assert rows[0].original_release_date == date(2025, 1, 24)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        ("blank_peak", "summer peak"),
        ("percent_cagr", "10-year growth"),
        ("duplicate_zone", "Duplicate"),
        ("missing_zone", "missing zone"),
        ("unexpected_zone", "Unexpected"),
    ],
)
def test_malformed_table_fails_closed(mutate: str, match: str) -> None:
    path = _workbook(
        header_row=7,
        first_zone_row=8,
        growth="percent_text",
        history_year=2025,
        mutate=mutate,
    )
    with pytest.raises(PjmB1Error, match=match):
        parse_table_b1(path, source_for_vintage(2026))


def test_as_of_filter_uses_stored_file_availability() -> None:
    rows = [_sample_row(2025), _sample_row(2026)]
    june_2025 = filter_b1_rows(rows, "2025-06-30")
    assert {row.ltlf_vintage_year for row in june_2025} == {2025}
    assert filter_b1_rows(rows, date(2025, 1, 23)) == []
    assert {row.ltlf_vintage_year for row in filter_b1_rows(rows, "2025-01-24")} == {2025}
    on_pdf_date = filter_b1_rows(rows, "2026-01-14")
    assert {row.ltlf_vintage_year for row in on_pdf_date} == {2025}
    assert source_for_vintage(2026).original_release_date == date(2026, 1, 14)
    both = filter_b1_rows(rows, "2026-02-06")
    assert {row.ltlf_vintage_year for row in both} == {2025, 2026}
    assert all(row.ltlf_vintage_year != 2024 for row in both)


def test_filter_rejects_missing_and_invalid_dates() -> None:
    row = _sample_row(2025)
    with pytest.raises(PjmB1Error, match="vintage_available_at"):
        filter_b1_rows([replace(row, vintage_available_at=None)], "2025-06-30")
    with pytest.raises(PjmB1Error, match="as_of_date"):
        filter_b1_rows([row], "2025/06/30")
    with pytest.raises(PjmB1Error, match="as_of_date"):
        filter_b1_rows([row], "")


def test_screening_package_does_not_import_evaluation() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "infralens" / "screening"
    sources = [path.read_text(encoding="utf-8") for path in root.glob("*.py")]
    assert sources
    assert all("infralens.evaluation" not in source for source in sources)


def test_parquet_roundtrip_preserves_null_revision(tmp_path: Path) -> None:
    rows = [_sample_row(2025), _sample_row(2026)]
    destination = tmp_path / "pjm_b1.parquet"
    write_b1_parquet(rows, destination)
    import pandas as pd

    frame = pd.read_parquet(destination)
    assert list(frame["ltlf_vintage_year"]) == [2025, 2026]
    assert pd.isna(frame.loc[0, "revision_date"])
    assert frame.loc[1, "summer_peak_mw"] == 10.0


def test_official_workbooks_match_published_b1_cells() -> None:
    if not _official_files_present():
        skip_missing_cache("pjm_workbooks")
    retrieved_at = datetime(2026, 10, 14, 18, 30)
    rows = load_slice1_tables(_RAW, retrieved_at=retrieved_at)
    validate_b1_rows(rows)
    assert len(rows) == 924
    _assert_grain(rows, vintage=2025, years=tuple(range(2025, 2046)))
    _assert_grain(rows, vintage=2026, years=tuple(range(2026, 2047)))
    assert _peak(rows, 2026, "AE", 2026) == 2563.0
    assert _cagr(rows, 2026, "AE") == _AE_2026_CAGR
    assert _cagr(rows, 2026, "DPL") == _DPL_2026_CAGR
    assert _cagr(rows, 2026, "DPL") < 0
    assert _peak(rows, 2025, "AE", 2025) == 2584.0
    assert _peak(rows, 2025, "DOM", 2025) == 23351.0
    assert _peak(rows, 2026, "DOM", 2026) == 25193.0
    assert _peak(rows, 2026, "AEP", 2026) == 24635.0
    assert _cagr(rows, 2025, "AE") == float("1.3463034E-3")
    assert {row.pjm_zone for row in rows} == set(EXPECTED_B1_ZONE_CODES)
    assert all(row.pjm_zone != "PJM RTO" for row in rows)
    forbidden = {
        "state_id",
        "large_load_adjustment_mw",
        "has_data_center_adjustment",
        "risk_score",
    }
    for row in rows:
        source = source_for_vintage(row.ltlf_vintage_year)
        assert row.original_release_date == source.original_release_date
        assert row.revision_date == source.revision_date
        assert row.vintage_available_at == source.vintage_available_at
        assert row.source_url == source.source_url
        assert row.source_file == source.source_file
        assert row.retrieved_at == retrieved_at
        assert forbidden.isdisjoint(row.__dict__)
    for source in TABLE_B1_SOURCES:
        published = _published_zone_values(_RAW / source.source_file)
        parsed = {
            (row.pjm_zone, row.forecast_year): row.summer_peak_mw
            for row in rows
            if row.ltlf_vintage_year == source.ltlf_vintage_year
        }
        assert parsed == published


def test_official_ingest_rejects_corrupt_workbooks(tmp_path: Path) -> None:
    if not _official_files_present():
        skip_missing_cache("pjm_workbooks")
    source = source_for_vintage(2026)
    original = _RAW / source.source_file
    cases = (
        ("blank_peak", "summer peak"),
        ("text_peak", "not a plain number"),
        ("text_growth", "not a plain number"),
        ("duplicate_zone", "Duplicate"),
        ("unexpected_zone", "Unexpected"),
    )
    for mode, match in cases:
        path = tmp_path / f"{mode}.xlsx"
        _corrupt_official_workbook(original, path, mode)
        with pytest.raises(PjmB1Error, match=match):
            parse_table_b1(path, source, retrieved_at=datetime(2026, 10, 14, 18, 30))


def test_official_rows_reject_duplicate_keys_and_invented_dates() -> None:
    if not _official_files_present():
        skip_missing_cache("pjm_workbooks")
    retrieved_at = datetime(2026, 10, 14, 18, 30)
    rows = load_slice1_tables(_RAW, retrieved_at=retrieved_at)
    with pytest.raises(PjmB1Error, match="Duplicate"):
        validate_b1_rows([*rows, rows[0]])
    with pytest.raises(PjmB1Error, match="missing a required forecast year"):
        validate_b1_rows(rows[:-1])
    invented = [
        replace(row, vintage_available_at=date(2026, 1, 14))
        if row.ltlf_vintage_year == 2026
        and row.pjm_zone == "AE"
        and row.forecast_year == 2026
        else row
        for row in rows
    ]
    with pytest.raises(PjmB1Error, match="vintage_available_at"):
        validate_b1_rows(invented)
    with pytest.raises(PjmB1Error, match="not a plain number"):
        validate_b1_rows(
            [replace(rows[0], summer_peak_10yr_cagr="0.5%"), *rows[1:]]
        )
    with pytest.raises(PjmB1Error, match="Unexpected"):
        validate_b1_rows([replace(rows[0], pjm_zone="DAY"), *rows[1:]])
    with pytest.raises(PjmB1Error, match="as_of_date"):
        filter_b1_rows(rows, "14-01-2026")
    with pytest.raises(PjmB1Error, match="retrieved_at"):
        load_slice1_tables(_RAW, retrieved_at=None)  # type: ignore[arg-type]


def _official_files_present() -> bool:
    return all((_RAW / source.source_file).is_file() for source in TABLE_B1_SOURCES)


def _corrupt_official_workbook(source: Path, dest: Path, mode: str) -> None:
    """Copy an official Tables workbook and break one Table B1 cell."""
    main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    pkg = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    with zipfile.ZipFile(source) as archive:
        payload = {name: archive.read(name) for name in archive.namelist()}
        shared_root = ET.fromstring(payload["xl/sharedStrings.xml"])
        shared = [
            "".join(node.text or "" for node in item.iter(f"{main}t"))
            for item in shared_root.findall(f"{main}si")
        ]
        workbook = ET.fromstring(payload["xl/workbook.xml"])
        relationships = ET.fromstring(payload["xl/_rels/workbook.xml.rels"])
        targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall(f"{pkg}Relationship")
        }
        sheet_name = ""
        for sheet in workbook.findall(f"{main}sheets/{main}sheet"):
            if sheet.attrib.get("name") == "Table B1":
                sheet_name = targets[sheet.attrib[rel + "id"]]
        if not sheet_name.startswith("xl/"):
            sheet_name = "xl/" + sheet_name.lstrip("/")
        root = ET.fromstring(payload[sheet_name])

    def cell_text(cell: ET.Element) -> object | None:
        kind = cell.attrib.get("t")
        node = cell.find(f"{main}v")
        if node is None or node.text is None:
            return None
        if kind == "s":
            return shared[int(node.text)]
        return float(node.text)

    located: dict[tuple[int, str], ET.Element] = {}
    for cell in root.iter(f"{main}c"):
        ref = cell.attrib.get("r", "")
        column = "".join(char for char in ref if char.isalpha())
        row_text = "".join(char for char in ref if char.isdigit())
        if column and row_text:
            located[(int(row_text), column)] = cell
    header_row = next(
        row
        for row in sorted({item[0] for item in located})
        if any(
            isinstance(cell_text(located[(row, column)]), str)
            and "Metered" in str(cell_text(located[(row, column)]))
            for column in {col for candidate, col in located if candidate == row}
        )
    )
    year_columns = []
    cagr_column = ""
    for column in sorted(
        {col for row, col in located if row == header_row},
        key=lambda letters: sum(
            (ord(char) - 64) * 26**index
            for index, char in enumerate(reversed(letters))
        ),
    ):
        value = cell_text(located[(header_row, column)])
        if isinstance(value, str) and "10 yr" in " ".join(value.lower().split()):
            cagr_column = column
        elif isinstance(value, float) and float(value).is_integer():
            year_columns.append(column)
    zone_rows = {
        str(cell_text(cell)).strip(): row
        for (row, column), cell in located.items()
        if column == "A" and isinstance(cell_text(cell), str)
    }
    peak = located[(zone_rows["AE"], year_columns[0])]
    growth = located[(zone_rows["AE"], cagr_column)]
    if mode == "blank_peak":
        parent = next(candidate for candidate in root.iter(f"{main}row") if peak in list(candidate))
        parent.remove(peak)
    elif mode == "text_peak":
        _set_inline_text(peak, "n/a")
    elif mode == "text_growth":
        _set_inline_text(growth, "0.5%")
    elif mode == "duplicate_zone":
        ae_index = located[(zone_rows["AE"], "A")].find(f"{main}v")
        bge_index = located[(zone_rows["BGE"], "A")].find(f"{main}v")
        assert ae_index is not None and bge_index is not None and ae_index.text is not None
        bge_index.text = ae_index.text
    elif mode == "unexpected_zone":
        _set_inline_text(located[(zone_rows["UGI"], "A")], "DAY")
    else:
        raise AssertionError(mode)
    payload[sheet_name] = ET.tostring(root, encoding="utf-8")
    with zipfile.ZipFile(dest, "w") as archive:
        for name, data in payload.items():
            archive.writestr(name, data)


def _set_inline_text(cell: ET.Element, text: str) -> None:
    main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    cell.attrib["t"] = "inlineStr"
    for child in list(cell):
        cell.remove(child)
    inline = ET.SubElement(cell, f"{main}is")
    node = ET.SubElement(inline, f"{main}t")
    node.text = text


def _assert_grain(rows: list[B1Row], *, vintage: int, years: tuple[int, ...]) -> None:
    selected = [row for row in rows if row.ltlf_vintage_year == vintage]
    keys = [row.key for row in selected]
    assert len(keys) == len(set(keys))
    assert len(selected) == 22 * len(years)
    zones = [row.pjm_zone for row in selected if row.forecast_year == years[0]]
    assert zones == list(EXPECTED_B1_ZONE_CODES)
    assert {row.forecast_year for row in selected} == set(years)


def _zone(rows: list[B1Row], zone: str) -> list[B1Row]:
    return [row for row in rows if row.pjm_zone == zone]


def _peak(rows: list[B1Row], vintage: int, zone: str, year: int) -> float:
    matches = [
        row.summer_peak_mw
        for row in rows
        if row.ltlf_vintage_year == vintage
        and row.pjm_zone == zone
        and row.forecast_year == year
    ]
    assert len(matches) == 1
    return matches[0]


def _cagr(rows: list[B1Row], vintage: int, zone: str) -> float:
    values = {
        row.summer_peak_10yr_cagr
        for row in rows
        if row.ltlf_vintage_year == vintage and row.pjm_zone == zone
    }
    assert len(values) == 1
    return next(iter(values))


def _sample_row(vintage: int) -> B1Row:
    source = source_for_vintage(vintage)
    return B1Row(
        pjm_zone="AE",
        ltlf_vintage_year=source.ltlf_vintage_year,
        original_release_date=source.original_release_date,
        revision_date=source.revision_date,
        vintage_available_at=source.vintage_available_at,
        forecast_year=source.ltlf_vintage_year,
        summer_peak_mw=10.0,
        summer_peak_10yr_cagr=0.01,
        source_url=source.source_url,
        source_file=source.source_file,
    )


def _workbook(
    *,
    header_row: int,
    first_zone_row: int,
    growth: str,
    history_year: int,
    mutate: str | None = None,
) -> Path:
    cells: dict[tuple[int, str], object] = {
        (header_row - 2, "A"): (
            "Summer Peak Load (MW) and Growth Rates for Each PJM Zone "
            f"({history_year + 1} - {history_year + 2})"
        ),
        (header_row, "A"): "",
        (header_row, "B"): f"Metered {history_year}",
        (header_row, "C"): f"Unrestricted {history_year}",
        (header_row, "D"): float(history_year + 1),
        (header_row, "E"): float(history_year + 2),
        (header_row, "F"): "Annual\nGrowth Rate\n(10 yr)",
    }
    cells.pop((header_row, "A"))
    zones = list(EXPECTED_B1_ZONE_CODES)
    if mutate == "missing_zone":
        zones = [zone for zone in zones if zone != "UGI"]
    if mutate == "unexpected_zone":
        zones.append("DAY")
    for index, zone in enumerate(zones):
        row = first_zone_row + index * 2
        year_one = 1000.0 + index
        year_two = 1100.0 + index
        cagr = 0.01
        if zone == "AE":
            year_one = 2563.0
            year_two = -12.5
            cagr = _AE_2026_CAGR
        if zone == "DPL":
            cagr = _DPL_2026_CAGR
        cells[(row, "A")] = zone
        cells[(row, "B")] = 99999.0
        cells[(row, "C")] = 88888.0
        cells[(row, "D")] = year_one
        cells[(row, "E")] = year_two
        cells[(row, "F")] = cagr
        growth_row = row + 1
        if growth == "percent_text":
            cells[(growth_row, "D")] = "-0.5%"
            cells[(growth_row, "E")] = "0.2%"
            cells[(growth_row, "F")] = "."
        else:
            cells[(growth_row, "D")] = -0.002
            cells[(growth_row, "E")] = 0.002
            cells[(growth_row, "F")] = 0.0
        if mutate == "blank_peak" and zone == "AE":
            cells.pop((row, "D"))
        if mutate == "percent_cagr" and zone == "AE":
            cells[(row, "F")] = "-0.5%"
        if mutate == "duplicate_zone" and zone == "AE":
            cells[(growth_row, "A")] = "AE"
    cells[(first_zone_row + 80, "A")] = "PJM RTO"
    cells[(first_zone_row + 80, "D")] = 1.0
    cells[(first_zone_row + 80, "E")] = 1.0
    cells[(first_zone_row + 80, "F")] = 0.0
    handle = tempfile.NamedTemporaryFile(prefix="pjm-b1-", suffix=".xlsx", delete=False)
    path = Path(handle.name)
    handle.close()
    _write_xlsx(path, cells)
    return path


def _write_xlsx(path: Path, cells: dict[tuple[int, str], object]) -> None:
    by_row: dict[int, list[tuple[str, object]]] = {}
    for (row, column), value in cells.items():
        by_row.setdefault(row, []).append((column, value))
    row_xml: list[str] = []
    for row in sorted(by_row):
        pieces = []
        for column, value in sorted(by_row[row], key=lambda item: item[0]):
            ref = f"{column}{row}"
            if isinstance(value, str):
                text = (
                    value.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                pieces.append(
                    f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
                )
            else:
                pieces.append(f'<c r="{ref}"><v>{repr(float(value))}</v></c>')
        row_xml.append(f'<row r="{row}">{"".join(pieces)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(row_xml)}</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Table B1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def _published_zone_values(path: Path) -> dict[tuple[str, int], float]:
    """Read forecast-year numbers from the official sheet without the parser."""
    main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    pkg = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    with zipfile.ZipFile(path) as archive:
        shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        shared = [
            "".join(node.text or "" for node in item.iter(f"{main}t"))
            for item in shared_root.findall(f"{main}si")
        ]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall(f"{pkg}Relationship")
        }
        target = ""
        for sheet in workbook.findall(f"{main}sheets/{main}sheet"):
            if sheet.attrib.get("name") == "Table B1":
                target = targets[sheet.attrib[rel + "id"]]
        if not target.startswith("xl/"):
            target = "xl/" + target.lstrip("/")
        root = ET.fromstring(archive.read(target))
    grid: dict[tuple[int, str], object] = {}
    for cell in root.iter(f"{main}c"):
        ref = cell.attrib.get("r", "")
        column = "".join(char for char in ref if char.isalpha())
        row = int("".join(char for char in ref if char.isdigit()))
        kind = cell.attrib.get("t")
        node = cell.find(f"{main}v")
        if node is None or node.text is None:
            continue
        grid[(row, column)] = shared[int(node.text)] if kind == "s" else float(node.text)
    header_row = next(
        row
        for row in sorted({item[0] for item in grid})
        if any(
            isinstance(grid[(row, column)], str) and "Metered" in grid[(row, column)]
            for column in {col for candidate, col in grid if candidate == row}
        )
    )
    year_columns: list[tuple[str, int]] = []
    for column, value in (
        (column, grid[(header_row, column)])
        for candidate, column in grid
        if candidate == header_row
    ):
        if isinstance(value, float) and float(value).is_integer():
            year_columns.append((column, int(value)))
    published: dict[tuple[str, int], float] = {}
    for row, column in grid:
        if column != "A":
            continue
        zone = grid[(row, column)]
        if zone not in EXPECTED_B1_ZONE_CODES:
            continue
        for year_column, year in year_columns:
            published[(str(zone), year)] = float(grid[(row, year_column)])
    return published

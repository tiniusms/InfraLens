"""Slice 2 tests for separate PJM B-9 and B-9b adjustment series."""

from __future__ import annotations

import tempfile
import zipfile
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from data_cache_skips import skip_missing_cache
from infralens.screening.pjm_adjustments import (
    ABOVE_EMBEDDED_MW,
    TOTAL_ASSOCIATED_MW,
    AdjustmentRow,
    PjmAdjustmentError,
    filter_adjustment_rows,
    load_slice2_adjustments,
    parse_adjustment_table,
    validate_adjustment_rows,
)
from infralens.screening.pjm_adjustments import ADJUSTMENT_TABLES
from infralens.screening.pjm_sources import (
    EXPECTED_B1_ZONE_CODES,
    TABLE_B1_SOURCES,
    source_for_vintage,
)

_RAW = Path("data/raw/pjm")
# Forecast year 2026 is the first year header on the 2026 B-9 and B-9b sheets
# (column B). It is not a prior-year metered column.
_AEP_2026_ABOVE_MW = 1913.0
_AEP_2026_TOTAL_MW = 2699.0


def test_fixture_layouts_keep_measures_separate_and_preserve_zero() -> None:
    retrieved_at = datetime(2026, 10, 14, 19, 0)
    for vintage, style in ((2026, "2026"), (2025, "2025")):
        path = _workbook(style)
        source = source_for_vintage(vintage)
        rows = []
        for table in ADJUSTMENT_TABLES:
            rows.extend(
                parse_adjustment_table(path, source, table, retrieved_at=retrieved_at)
            )
        validate_adjustment_rows(rows)
        assert {row.adjustment_measure for row in rows} == {
            ABOVE_EMBEDDED_MW,
            TOTAL_ASSOCIATED_MW,
        }
        assert {row.source_table for row in rows} == {"B-9", "B-9b"}
        keys = [row.key for row in rows]
        assert len(keys) == len(set(keys))
        assert [row.pjm_zone for row in rows if row.forecast_year == vintage and row.adjustment_measure == ABOVE_EMBEDDED_MW] == list(EXPECTED_B1_ZONE_CODES)
        ae = _value(rows, vintage, "AE", vintage, ABOVE_EMBEDDED_MW)
        assert ae == 0.0
        assert _value(rows, vintage, "EKPC", vintage, ABOVE_EMBEDDED_MW) < 0
        assert rows[0].original_release_date == source.original_release_date
        assert rows[0].revision_date == source.revision_date
        assert rows[0].vintage_available_at == source.vintage_available_at
        assert rows[0].retrieved_at == retrieved_at
        assert "state_id" not in rows[0].__dict__
        assert "risk_score" not in rows[0].__dict__
    path_2026 = _workbook("2026")
    rows_2026 = []
    for table in ADJUSTMENT_TABLES:
        rows_2026.extend(
            parse_adjustment_table(
                path_2026,
                source_for_vintage(2026),
                table,
                retrieved_at=retrieved_at,
            )
        )
    assert _value(rows_2026, 2026, "AEP", 2026, ABOVE_EMBEDDED_MW) == _AEP_2026_ABOVE_MW
    assert _value(rows_2026, 2026, "AEP", 2026, TOTAL_ASSOCIATED_MW) == _AEP_2026_TOTAL_MW
    assert _AEP_2026_ABOVE_MW + _AEP_2026_TOTAL_MW not in {
        row.adjustment_mw for row in rows_2026
    }


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        ("blank_peak", "MW for"),
        ("text_peak", "not a plain number"),
        ("duplicate_zone", "Duplicate"),
        ("unexpected_zone", "Unexpected"),
        ("missing_zone", "missing zone"),
        ("bad_units", "not labeled in MW"),
    ],
)
def test_malformed_adjustment_table_fails_closed(mutate: str, match: str) -> None:
    path = _workbook("2026", mutate=mutate)
    with pytest.raises(PjmAdjustmentError, match=match):
        parse_adjustment_table(
            path,
            source_for_vintage(2026),
            ADJUSTMENT_TABLES[0],
            retrieved_at=datetime(2026, 10, 14, 19, 0),
        )


def test_as_of_filter_uses_tables_file_availability() -> None:
    rows = [_sample(2025), _sample(2026)]
    assert {row.ltlf_vintage_year for row in filter_adjustment_rows(rows, "2025-06-30")} == {2025}
    assert filter_adjustment_rows(rows, date(2025, 1, 23)) == []
    assert {row.ltlf_vintage_year for row in filter_adjustment_rows(rows, "2026-01-14")} == {2025}
    assert {row.ltlf_vintage_year for row in filter_adjustment_rows(rows, "2026-02-06")} == {2025, 2026}
    with pytest.raises(PjmAdjustmentError, match="as_of_date"):
        filter_adjustment_rows(rows, "2026/02/06")
    with pytest.raises(PjmAdjustmentError, match="vintage_available_at"):
        filter_adjustment_rows(
            [replace(rows[0], vintage_available_at=None)],
            "2026-02-06",
        )


def test_official_adjustment_workbooks() -> None:
    if not _official_files_present():
        skip_missing_cache("pjm_workbooks")
    retrieved_at = datetime(2026, 10, 14, 19, 5)
    rows = load_slice2_adjustments(_RAW, retrieved_at=retrieved_at)
    assert len(rows) == 1848
    assert len({row.key for row in rows}) == 1848
    for vintage, start, end in ((2025, 2025, 2045), (2026, 2026, 2046)):
        for measure in (ABOVE_EMBEDDED_MW, TOTAL_ASSOCIATED_MW):
            selected = [
                row
                for row in rows
                if row.ltlf_vintage_year == vintage and row.adjustment_measure == measure
            ]
            assert len(selected) == 22 * 21
            years = sorted({row.forecast_year for row in selected})
            assert years == list(range(start, end + 1))
            zones = [row.pjm_zone for row in selected if row.forecast_year == start]
            assert zones == list(EXPECTED_B1_ZONE_CODES)
    assert _value(rows, 2026, "AEP", 2026, ABOVE_EMBEDDED_MW) == _AEP_2026_ABOVE_MW
    assert _value(rows, 2026, "AEP", 2026, TOTAL_ASSOCIATED_MW) == _AEP_2026_TOTAL_MW
    assert _value(rows, 2025, "AEP", 2025, ABOVE_EMBEDDED_MW) == 1412.0
    assert _value(rows, 2025, "AEP", 2025, TOTAL_ASSOCIATED_MW) == 1761.0
    assert _value(rows, 2026, "AE", 2026, ABOVE_EMBEDDED_MW) == 0.0
    assert _value(rows, 2026, "AE", 2026, TOTAL_ASSOCIATED_MW) == 0.0
    assert _value(rows, 2025, "AE", 2025, ABOVE_EMBEDDED_MW) == 0.0
    assert _value(rows, 2025, "AE", 2025, TOTAL_ASSOCIATED_MW) == 0.0
    assert _value(rows, 2026, "EKPC", 2026, ABOVE_EMBEDDED_MW) == -10.0
    assert _value(rows, 2026, "EKPC", 2026, TOTAL_ASSOCIATED_MW) == -10.0
    assert _value(rows, 2025, "EKPC", 2025, ABOVE_EMBEDDED_MW) == -6.0
    assert _value(rows, 2025, "EKPC", 2025, TOTAL_ASSOCIATED_MW) == -6.0
    assert _value(rows, 2026, "PS", 2026, ABOVE_EMBEDDED_MW) == 72.0
    assert _value(rows, 2026, "PS", 2026, TOTAL_ASSOCIATED_MW) == 308.0
    assert all(row.pjm_zone != "PJM RTO" for row in rows)
    for row in rows:
        source = source_for_vintage(row.ltlf_vintage_year)
        assert row.original_release_date == source.original_release_date
        assert row.revision_date == source.revision_date
        assert row.vintage_available_at == source.vintage_available_at
        assert row.source_url == source.source_url
        assert row.source_file == source.source_file
        assert row.retrieved_at == retrieved_at
        assert (row.adjustment_measure == ABOVE_EMBEDDED_MW) is (row.source_table == "B-9")
        assert (row.adjustment_measure == TOTAL_ASSOCIATED_MW) is (row.source_table == "B-9b")
        assert {
            "state_id",
            "large_load_adjustment_mw",
            "has_data_center_adjustment",
            "risk_score",
        }.isdisjoint(row.__dict__)
    assert filter_adjustment_rows(rows, "2025-06-30")
    assert {row.ltlf_vintage_year for row in filter_adjustment_rows(rows, "2026-01-14")} == {2025}
    with pytest.raises(PjmAdjustmentError, match="Duplicate"):
        validate_adjustment_rows([*rows, rows[0]])
    with pytest.raises(PjmAdjustmentError, match="missing a required forecast year"):
        validate_adjustment_rows(rows[:-1])
    invented = [
        replace(row, vintage_available_at=date(2026, 1, 14))
        if row.ltlf_vintage_year == 2026
        and row.pjm_zone == "AEP"
        and row.forecast_year == 2026
        and row.adjustment_measure == ABOVE_EMBEDDED_MW
        else row
        for row in rows
    ]
    with pytest.raises(PjmAdjustmentError, match="vintage_available_at"):
        validate_adjustment_rows(invented)


def test_official_b9_workbook_rejects_corrupt_cells(tmp_path: Path) -> None:
    if not _official_files_present():
        skip_missing_cache("pjm_workbooks")
    source = source_for_vintage(2026)
    original = _RAW / source.source_file
    table = ADJUSTMENT_TABLES[0]
    for mode, match in (
        ("blank_peak", "MW for"),
        ("text_peak", "not a plain number"),
        ("duplicate_zone", "Duplicate"),
        ("unexpected_zone", "Unexpected"),
    ):
        path = tmp_path / f"{mode}.xlsx"
        _corrupt_official_b9(original, path, mode)
        with pytest.raises(PjmAdjustmentError, match=match):
            parse_adjustment_table(
                path,
                source,
                table,
                retrieved_at=datetime(2026, 10, 14, 19, 5),
            )


def _value(
    rows: list[AdjustmentRow],
    vintage: int,
    zone: str,
    year: int,
    measure: str,
) -> float:
    matches = [
        row.adjustment_mw
        for row in rows
        if row.ltlf_vintage_year == vintage
        and row.pjm_zone == zone
        and row.forecast_year == year
        and row.adjustment_measure == measure
    ]
    assert len(matches) == 1
    return matches[0]


def _sample(vintage: int) -> AdjustmentRow:
    source = source_for_vintage(vintage)
    return AdjustmentRow(
        pjm_zone="AE",
        ltlf_vintage_year=source.ltlf_vintage_year,
        forecast_year=source.ltlf_vintage_year,
        adjustment_measure=ABOVE_EMBEDDED_MW,
        adjustment_mw=0.0,
        source_table="B-9",
        original_release_date=source.original_release_date,
        revision_date=source.revision_date,
        vintage_available_at=source.vintage_available_at,
        source_url=source.source_url,
        source_file=source.source_file,
        retrieved_at=datetime(2026, 10, 14, 19, 0),
    )


def _official_files_present() -> bool:
    return all((_RAW / source.source_file).is_file() for source in TABLE_B1_SOURCES)


def _workbook(style: str, mutate: str | None = None) -> Path:
    if style == "2026":
        years = (2026, 2027)
        b9_title = (
            "Adjustments Above Embedded to Summer Peak Load (MW) "
            "for Each PJM Zone and RTO (2026 - 2046)"
        )
        b9b_title = (
            "Total Load Associated with Adjustments to Summer Peak Load (MW) "
            "for Each PJM Zone and RTO (2026 - 2046)"
        )
        note = "* Note: This Table was updated 2/6/2026 to correct for an error calculating embedded"
        column1 = False
        aep = (1913.0, 2699.0)
        ekpc = -10.0
    else:
        years = (2025, 2026)
        b9_title = (
            "Adjustments Above Embedded to Summer Peak Load (MW) "
            "for Each PJM Zone and RTO (2025 - 2045)"
        )
        b9b_title = (
            "Total Load Associated with Adjustments to Summer Peak Load (MW) "
            "for Each PJM Zone and RTO"
        )
        note = None
        column1 = True
        aep = (1412.0, 1761.0)
        ekpc = -6.0
    if mutate == "bad_units":
        b9_title = b9_title.replace("(MW)", "(GW)")
    sheets = {
        "Table B9": _sheet_cells(
            "Table B-9",
            b9_title,
            years,
            aep[0],
            ekpc,
            note=note,
            column1=column1,
            mutate=mutate,
        ),
        "Table B9b": _sheet_cells(
            "Table B-9b",
            b9b_title,
            years,
            aep[1],
            ekpc,
            note=None,
            column1=False,
            mutate=None,
        ),
    }
    handle = tempfile.NamedTemporaryFile(prefix="pjm-b9-", suffix=".xlsx", delete=False)
    path = Path(handle.name)
    handle.close()
    _write_xlsx(path, sheets)
    return path


def _sheet_cells(
    table_label: str,
    title: str,
    years: tuple[int, int],
    aep_value: float,
    ekpc_value: float,
    *,
    note: str | None,
    column1: bool,
    mutate: str | None,
) -> dict[tuple[int, str], object]:
    cells: dict[tuple[int, str], object] = {
        (4, "A"): table_label,
        (5, "A"): title,
        (7, "B"): float(years[0]),
        (7, "C"): float(years[1]),
    }
    if note:
        cells[(6, "A")] = note
    row = 8
    if column1:
        cells[(row, "A")] = "Column1"
        cells[(row, "B")] = "Column2"
        cells[(row, "C")] = "Column3"
        row += 1
    zones = list(EXPECTED_B1_ZONE_CODES)
    if mutate == "missing_zone":
        zones = [zone for zone in zones if zone != "UGI"]
    if mutate == "unexpected_zone":
        zones.append("DAY")
    for zone in zones:
        first = 3.0
        second = 4.0
        if zone == "AE":
            first = 0.0
            second = 1.0
        elif zone == "AEP":
            first = aep_value
            second = aep_value + 1
        elif zone == "EKPC":
            first = ekpc_value
            second = ekpc_value
        cells[(row, "A")] = zone
        cells[(row, "B")] = first
        cells[(row, "C")] = second
        if mutate == "blank_peak" and zone == "AE":
            cells.pop((row, "B"))
        if mutate == "text_peak" and zone == "AE":
            cells[(row, "B")] = "n/a"
        if mutate == "duplicate_zone" and zone == "BGE":
            cells[(row, "A")] = "AE"
        row += 1
    cells[(row + 2, "A")] = "PJM RTO"
    cells[(row + 2, "B")] = 50.0
    cells[(row + 2, "C")] = 60.0
    return cells


def _write_xlsx(path: Path, sheets: dict[str, dict[tuple[int, str], object]]) -> None:
    sheet_xml = []
    overrides = []
    rels = []
    for index, (name, cells) in enumerate(sheets.items(), start=1):
        sheet_xml.append((f"xl/worksheets/sheet{index}.xml", _sheet_xml(cells)))
        overrides.append(
            "<Override "
            f'PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        rels.append(
            "<Relationship "
            f'Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
    sheet_tags = "".join(
        f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheets, start=1)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_tags}</sheets></workbook>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{''.join(overrides)}</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(rels)}</Relationships>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        for name, xml in sheet_xml:
            archive.writestr(name, xml)


def _sheet_xml(cells: dict[tuple[int, str], object]) -> str:
    by_row: dict[int, list[tuple[str, object]]] = {}
    for (row, column), value in cells.items():
        by_row.setdefault(row, []).append((column, value))
    rows = []
    for row in sorted(by_row):
        pieces = []
        for column, value in sorted(by_row[row]):
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
        rows.append(f'<row r="{row}">{"".join(pieces)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )


def _corrupt_official_b9(source: Path, dest: Path, mode: str) -> None:
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
            if sheet.attrib.get("name") == "Table B9":
                sheet_name = targets[sheet.attrib[rel + "id"]]
        if not sheet_name.startswith("xl/"):
            sheet_name = "xl/" + sheet_name.lstrip("/")
        root = ET.fromstring(payload[sheet_name])

    def text(cell: ET.Element) -> object | None:
        kind = cell.attrib.get("t")
        node = cell.find(f"{main}v")
        if node is None or node.text is None:
            return None
        return shared[int(node.text)] if kind == "s" else float(node.text)

    located: dict[tuple[int, str], ET.Element] = {}
    for cell in root.iter(f"{main}c"):
        ref = cell.attrib.get("r", "")
        column = "".join(char for char in ref if char.isalpha())
        row_text = "".join(char for char in ref if char.isdigit())
        if column and row_text:
            located[(int(row_text), column)] = cell
    zones = {
        str(text(cell)).strip(): row
        for (row, column), cell in located.items()
        if column == "A" and isinstance(text(cell), str)
    }
    peak = located[(zones["AEP"], "B")]
    if mode == "blank_peak":
        parent = next(candidate for candidate in root.iter(f"{main}row") if peak in list(candidate))
        parent.remove(peak)
    elif mode == "text_peak":
        cell = peak
        cell.attrib["t"] = "inlineStr"
        for child in list(cell):
            cell.remove(child)
        inline = ET.SubElement(cell, f"{main}is")
        node = ET.SubElement(inline, f"{main}t")
        node.text = "n/a"
    elif mode == "duplicate_zone":
        ae_value = located[(zones["AE"], "A")].find(f"{main}v")
        bge_value = located[(zones["BGE"], "A")].find(f"{main}v")
        assert ae_value is not None and bge_value is not None and ae_value.text
        bge_value.text = ae_value.text
    elif mode == "unexpected_zone":
        cell = located[(zones["UGI"], "A")]
        cell.attrib["t"] = "inlineStr"
        for child in list(cell):
            cell.remove(child)
        inline = ET.SubElement(cell, f"{main}is")
        node = ET.SubElement(inline, f"{main}t")
        node.text = "DAY"
    else:
        raise AssertionError(mode)
    payload[sheet_name] = ET.tostring(root, encoding="utf-8")
    with zipfile.ZipFile(dest, "w") as archive:
        for name, data in payload.items():
            archive.writestr(name, data)

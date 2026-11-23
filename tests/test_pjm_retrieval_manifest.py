"""PJM retrieval time comes from the data manifest (Version 2 Phase 2, criterion 2).

These tests never skip. They build two small synthetic Tables workbooks and a
test manifest in a temporary directory, then run the real parsers, the demo
loader, and ``GET /api/v1/pjm/screen``. Any read of a file-creation time fails
the test, so a pass on the Linux CI runner shows the PJM view works on Linux.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infralens.api.app import create_app
from infralens.data import repository_root
from infralens.demo.foundation import DemoDataError
from infralens.demo.pjm_screen import (
    FILE_MISMATCH,
    RETRIEVAL_UNAVAILABLE,
    load_screening_tables,
    present_screening,
    screen_cached_zone,
)
from infralens.screening.pjm_sources import EXPECTED_B1_ZONE_CODES

_NAMES = ("2025-load-report-tables.xlsx", "2026-load-report-tables.xlsx")
_TIMES = {
    "2025-load-report-tables.xlsx": "2026-11-20T22:08:52.810329Z",
    "2026-load-report-tables.xlsx": "2026-11-20T22:08:53.714814Z",
}
# Synthetic AEP values, chosen so they cannot be mistaken for the official workbooks.
_AEP = {2025: (111.0, 11.0, 12.0), 2026: (222.0, 21.0, 22.0)}
_OBSERVED = "2026-10-14T18:25:52.781338Z"
_BIRTH_ATTRIBUTES = ("st_birthtime", "st_birthtime_ns")


class _NoBirthTimeStat:
    def __init__(self, real: object) -> None:
        self._real = real

    def __getattr__(self, name: str) -> object:
        if name in _BIRTH_ATTRIBUTES:
            raise AssertionError(f"{name} was read; retrieval time must come from the data manifest")
        return getattr(self._real, name)


@pytest.fixture(autouse=True)
def _forbid_birth_times(monkeypatch: pytest.MonkeyPatch) -> None:
    real_stat = Path.stat

    def stat(self: Path, *args: object, **kwargs: object) -> _NoBirthTimeStat:
        return _NoBirthTimeStat(real_stat(self, *args, **kwargs))

    monkeypatch.setattr(Path, "stat", stat)


def test_screen_uses_manifest_times_without_reading_creation_time(tmp_path: Path) -> None:
    raw = _synthetic_workbooks(tmp_path)
    manifest = _write_manifest(tmp_path, {name: "recorded" for name in _NAMES})

    b1_rows, adjustment_rows, retrieval = load_screening_tables(raw, manifest_path=manifest)
    current = present_screening(
        screen_cached_zone(b1_rows, adjustment_rows, "AEP", 2026, date(2026, 2, 6)), retrieval.note
    )
    early = present_screening(
        screen_cached_zone(b1_rows, adjustment_rows, "AEP", 2026, date(2025, 6, 30)), retrieval.note
    )
    assert (current.ltlf_vintage_year, current.summer_peak_mw) == (2026, _AEP[2026][0])
    assert (current.above_embedded_mw, current.total_associated_mw) == _AEP[2026][1:]
    assert current.retrieved_at == (_TIMES["2026-load-report-tables.xlsx"],) * 3
    assert (early.ltlf_vintage_year, early.summer_peak_mw) == (2025, _AEP[2025][0])
    assert early.retrieved_at == (_TIMES["2025-load-report-tables.xlsx"],) * 3
    assert early.vintage_available_at == date(2025, 1, 24)
    assert current.vintage_available_at == date(2026, 2, 6)
    assert retrieval.note.startswith("Retrieved 2026-11-20 (byte-identical copy; original download time not recorded).")
    assert "not a PJM publication date" in retrieval.note
    assert "evidence for 2026-load-report-tables.xlsx" in retrieval.note

    with TestClient(create_app(root=tmp_path, cors_origins=[])) as client:
        response = client.get(
            "/api/v1/pjm/screen", params={"pjm_zone": "AEP", "forecast_year": 2026, "as_of": "2026-02-06"}
        )
        status = client.get("/api/v1/status").json()
    assert response.status_code == 200
    body = response.json()
    assert body["summer_peak_mw"] == _AEP[2026][0]
    assert body["above_embedded_mw"] == _AEP[2026][1]
    assert body["total_associated_mw"] == _AEP[2026][2]
    assert body["retrieved_at"] == [_TIMES["2026-load-report-tables.xlsx"]] * 3
    assert body["retrieval_note"] == retrieval.note
    pjm_status = {a["artifact_id"]: a["status"] for a in status["artifacts"] if a["artifact_id"].startswith("pjm_")}
    assert pjm_status == {"pjm_2025_tables": "valid", "pjm_2026_tables": "valid"}


def test_file_mismatch_refuses_and_never_shows_the_manifest_time(tmp_path: Path) -> None:
    raw = _synthetic_workbooks(tmp_path)
    manifest = _write_manifest(tmp_path, {name: "recorded" for name in _NAMES})
    with (raw / _NAMES[1]).open("ab") as handle:
        handle.write(b"\0")

    with pytest.raises(DemoDataError) as refused:
        load_screening_tables(raw, manifest_path=manifest)
    assert str(refused.value) == FILE_MISMATCH

    body, status_code = _api_screen(tmp_path)
    assert status_code == 500
    assert body["code"] == "artifact_invalid"
    assert body["message"] == FILE_MISMATCH
    text = json.dumps(body)
    assert all(stamp not in text for stamp in _TIMES.values())
    assert "summer_peak_mw" not in body


@pytest.mark.parametrize("case", ["no_manifest", "malformed_manifest", "missing_entry", "unrecorded_entry"])
def test_missing_or_unrecorded_entries_are_unavailable(tmp_path: Path, case: str) -> None:
    raw = _synthetic_workbooks(tmp_path)
    manifest = tmp_path / "data" / "manifest.json"
    if case == "malformed_manifest":
        manifest.write_text("{", encoding="utf-8")
    elif case == "missing_entry":
        _write_manifest(tmp_path, {_NAMES[0]: "recorded"})
    elif case == "unrecorded_entry":
        _write_manifest(tmp_path, {_NAMES[0]: "recorded", _NAMES[1]: "unrecorded"})

    with pytest.raises(DemoDataError) as refused:
        load_screening_tables(raw, manifest_path=manifest)
    assert str(refused.value) == RETRIEVAL_UNAVAILABLE

    body, status_code = _api_screen(tmp_path)
    assert status_code == 500
    assert body["message"] == RETRIEVAL_UNAVAILABLE
    text = json.dumps(body)
    assert _OBSERVED not in text
    assert all(stamp not in text for stamp in _TIMES.values())


def test_note_does_not_call_every_workbook_a_copy_when_only_one_is(tmp_path: Path) -> None:
    raw = _synthetic_workbooks(tmp_path)
    manifest = _write_manifest(tmp_path, {name: "recorded" for name in _NAMES})
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["raw_sources"][0]["retrieval_receipt"] = None
    manifest.write_text(json.dumps(document), encoding="utf-8")
    _b1, _adjustments, retrieval = load_screening_tables(raw, manifest_path=manifest)
    assert retrieval.note.startswith("Retrieved 2026-11-20 (recorded per workbook; see the manifest evidence).")
    assert "byte-identical copy; original download time not recorded" not in retrieval.note


def test_retrieval_code_never_reads_creation_time() -> None:
    src = repository_root() / "src" / "infralens"
    for relative in ("demo/pjm_screen.py", "api/readers.py", "demo/app.py", "data/manifest.py"):
        assert "birthtime" not in (src / relative).read_text(encoding="utf-8"), relative


def _api_screen(root: Path) -> tuple[dict, int]:
    with TestClient(create_app(root=root, cors_origins=[])) as client:
        response = client.get(
            "/api/v1/pjm/screen", params={"pjm_zone": "AEP", "forecast_year": 2026, "as_of": "2026-02-06"}
        )
    return response.json(), response.status_code


def _write_manifest(root: Path, statuses: dict[str, str]) -> Path:
    entries = []
    for name, status in statuses.items():
        data = (root / "data" / "raw" / "pjm" / name).read_bytes()
        recorded = status == "recorded"
        entries.append(
            {
                "path": f"data/raw/pjm/{name}",
                "filename": name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "retrieved_at": {
                    "value": _TIMES[name] if recorded else None,
                    "status": status,
                    "evidence": f"test evidence for {name}",
                },
                "retrieval_receipt": {"sha256_matches_stored_file": True} if recorded else None,
                "observed_local_time": {"value": _OBSERVED, "kind": "macOS st_birthtime of the stored copy"},
            }
        )
    manifest = root / "data" / "manifest.json"
    manifest.write_text(json.dumps({"raw_sources": entries}), encoding="utf-8")
    return manifest


def _synthetic_workbooks(root: Path) -> Path:
    raw = root / "data" / "raw" / "pjm"
    raw.mkdir(parents=True)
    for vintage, name in zip((2025, 2026), _NAMES, strict=True):
        peak, above, total = _AEP[vintage]
        years = (vintage, vintage + 1)
        sheets = {
            "Table B1": _b1_cells(years, peak),
            "Table B9": _adjustment_cells(
                "Table B-9",
                f"Adjustments Above Embedded to Summer Peak Load (MW) for Each PJM Zone and RTO ({vintage} - {vintage + 20})",
                years,
                above,
            ),
            "Table B9b": _adjustment_cells(
                "Table B-9b",
                f"Total Load Associated with Adjustments to Summer Peak Load (MW) for Each PJM Zone and RTO ({vintage} - {vintage + 20})",
                years,
                total,
            ),
        }
        _write_xlsx(raw / name, sheets)
    return raw


def _b1_cells(years: tuple[int, int], aep_peak: float) -> dict[tuple[int, str], object]:
    history = years[0] - 1
    cells: dict[tuple[int, str], object] = {
        (4, "A"): f"Summer Peak Load (MW) and Growth Rates for Each PJM Zone ({years[0]} - {years[1]})",
        (6, "B"): f"Metered {history}",
        (6, "C"): f"Unrestricted {history}",
        (6, "D"): float(years[0]),
        (6, "E"): float(years[1]),
        (6, "F"): "Annual\nGrowth Rate\n(10 yr)",
    }
    for index, zone in enumerate(EXPECTED_B1_ZONE_CODES):
        row = 8 + index * 2
        first = aep_peak if zone == "AEP" else 1000.0 + index
        cells[(row, "A")] = zone
        cells[(row, "B")] = 900.0
        cells[(row, "C")] = 950.0
        cells[(row, "D")] = first
        cells[(row, "E")] = first if zone == "AEP" else first + 10.0
        cells[(row, "F")] = 0.01
        cells[(row + 1, "D")] = 0.001
        cells[(row + 1, "E")] = 0.002
        cells[(row + 1, "F")] = 0.0
    return cells


def _adjustment_cells(
    label: str, title: str, years: tuple[int, int], aep_value: float
) -> dict[tuple[int, str], object]:
    cells: dict[tuple[int, str], object] = {
        (4, "A"): label,
        (5, "A"): title,
        (7, "B"): float(years[0]),
        (7, "C"): float(years[1]),
    }
    for index, zone in enumerate(EXPECTED_B1_ZONE_CODES):
        row = 8 + index
        value = aep_value if zone == "AEP" else 3.0
        cells[(row, "A")] = zone
        cells[(row, "B")] = value
        cells[(row, "C")] = value if zone == "AEP" else value + 1.0
    return cells


def _write_xlsx(path: Path, sheets: dict[str, dict[tuple[int, str], object]]) -> None:
    ns_main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns_pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    sheet_tags = "".join(
        f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>' for index, name in enumerate(sheets, start=1)
    )
    rels = "".join(
        f'<Relationship Id="rId{index}" Type="{ns_rel}/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        archive.writestr(
            "_rels/.rels",
            f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{ns_pkg}">'
            f'<Relationship Id="rId1" Type="{ns_rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{ns_main}" xmlns:r="{ns_rel}">'
            f"<sheets>{sheet_tags}</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{ns_pkg}">{rels}</Relationships>',
        )
        for index, cells in enumerate(sheets.values(), start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(cells, ns_main))


def _sheet_xml(cells: dict[tuple[int, str], object], ns_main: str) -> str:
    by_row: dict[int, list[tuple[str, object]]] = {}
    for (row, column), value in cells.items():
        by_row.setdefault(row, []).append((column, value))
    rows = []
    for row in sorted(by_row):
        pieces = []
        for column, value in sorted(by_row[row]):
            ref = f"{column}{row}"
            if isinstance(value, str):
                text = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                pieces.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
            else:
                pieces.append(f'<c r="{ref}"><v>{float(value)!r}</v></c>')
        rows.append(f'<row r="{row}">{"".join(pieces)}</row>')
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{ns_main}">'
        f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )

"""Demo presentation of the existing PJM screening view. It does not reparse rules."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from data_cache_skips import skip_missing_cache
from infralens.data.manifest import default_manifest_path, load_manifest
from infralens.demo.foundation import DemoDataError, default_artifact_paths
from infralens.demo.pjm_screen import (
    CAGR_PERCENT_LABEL,
    GEOGRAPHIC_WARNING,
    LARGE_LOAD_WARNING,
    MISSING_WORKBOOKS,
    RETRIEVAL_UNAVAILABLE,
    ScreeningDisplay,
    load_screening_tables,
    manifest_workbook_retrieval,
    present_screening,
    screen_cached_zone,
    workbook_identity,
    workbook_paths,
)
from infralens.finance.annual_cost import EIA_MODEL_PRICE_WARNING
from infralens.screening.pjm_b1 import PjmB1Error
from infralens.screening.pjm_view import PjmViewError, ScreeningProvenance, ZoneYearScreening

_BIRTH_ATTRIBUTES = ("st_birthtime", "st_birthtime_ns")
_NAMES = ("2025-load-report-tables.xlsx", "2026-load-report-tables.xlsx")


class _NoBirthTimeStat:
    """A real ``os.stat_result`` whose file-creation time fails the test if read.

    macOS reports ``st_birthtime``; Python on Linux does not. Retrieval time now
    comes from the data manifest, so no code path may read creation time.
    """

    def __init__(self, real: object) -> None:
        self._real = real

    def __getattr__(self, name: str) -> object:
        if name in _BIRTH_ATTRIBUTES:
            raise AssertionError(f"{name} was read; retrieval time must come from the data manifest")
        return getattr(self._real, name)


def _forbid_birth_times(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any read of a file-creation time fail, on macOS and Linux alike."""

    real_stat = Path.stat

    def stat(self: Path, *args: object, **kwargs: object) -> _NoBirthTimeStat:
        return _NoBirthTimeStat(real_stat(self, *args, **kwargs))

    monkeypatch.setattr(Path, "stat", stat)


def _write_test_manifest(root: Path, recorded: dict[str, str | None]) -> Path:
    """Write ``root/data/manifest.json`` for workbooks under ``root/data/raw/pjm``.

    ``recorded`` maps a workbook name to a recorded UTC time, or to None for an
    entry whose retrieval time was not recorded. Names left out have no entry.
    """

    entries = []
    for name, value in recorded.items():
        data = (root / "data" / "raw" / "pjm" / name).read_bytes()
        entries.append(
            {
                "path": f"data/raw/pjm/{name}",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "retrieved_at": {
                    "value": value,
                    "status": "recorded" if value is not None else "unrecorded",
                    "evidence": f"test fixture for {name}",
                },
                "retrieval_receipt": None,
            }
        )
    manifest = root / "data" / "manifest.json"
    manifest.write_text(json.dumps({"raw_sources": entries}), encoding="utf-8")
    return manifest


def _empty_workbooks(root: Path) -> tuple[Path, tuple[Path, Path]]:
    raw = root / "data" / "raw" / "pjm"
    raw.mkdir(parents=True)
    for name in _NAMES:
        (raw / name).write_bytes(b"")
    return raw, (raw / _NAMES[0], raw / _NAMES[1])


def _manifest_time(name: str) -> str:
    entry = next(e for e in load_manifest(default_manifest_path())["raw_sources"] if e["filename"] == name)
    return entry["retrieved_at"]["value"]


def test_aep_cutoffs_match_the_cached_workbooks() -> None:
    raw_dir = default_artifact_paths().pjm_2025_tables.parent
    if not all(path.is_file() for path in workbook_paths(raw_dir)):
        skip_missing_cache("pjm_workbooks")
    b1_rows, adjustment_rows, retrieval = load_screening_tables(raw_dir)
    assert "not a PJM publication date" in retrieval.note
    assert retrieval.loader_retrieved_at.tzinfo is not None

    early = present_screening(
        screen_cached_zone(b1_rows, adjustment_rows, "AEP", 2026, date(2025, 6, 30)),
        retrieval.note,
    )
    _assert_aep_2025(early)
    assert early.as_of_date == date(2025, 6, 30)

    still_2025 = present_screening(
        screen_cached_zone(b1_rows, adjustment_rows, "AEP", 2026, date(2026, 1, 14)),
        retrieval.note,
    )
    _assert_aep_2025(still_2025)
    assert still_2025.vintage_available_at == date(2025, 1, 24)

    current = present_screening(
        screen_cached_zone(b1_rows, adjustment_rows, "AEP", 2026, date(2026, 2, 6)),
        retrieval.note,
    )
    assert current.available is True
    assert current.ltlf_vintage_year == 2026
    assert current.summer_peak_mw == 24635.0
    assert current.summer_peak_10yr_cagr == 0.0525293343
    assert current.cagr_percent_per_year == pytest.approx(5.25293343)
    assert current.above_embedded_mw == 1913.0
    assert current.total_associated_mw == 2699.0
    assert current.original_release_date == date(2026, 1, 14)
    assert current.revision_date == date(2026, 2, 6)
    assert current.vintage_available_at == date(2026, 2, 6)
    assert current.source_tables == ("B1", "B-9", "B-9b")
    assert current.source_files == ("2026-load-report-tables.xlsx",) * 3
    assert all(url.endswith("/2026-load-report-tables.xlsx") for url in current.source_urls)
    assert current.retrieved_at == (_manifest_time("2026-load-report-tables.xlsx"),) * 3
    assert current.above_embedded_mw != current.total_associated_mw


def test_date_before_the_2025_release_is_unpublished() -> None:
    raw_dir = default_artifact_paths().pjm_2025_tables.parent
    if not all(path.is_file() for path in workbook_paths(raw_dir)):
        skip_missing_cache("pjm_workbooks")
    b1_rows, adjustment_rows, retrieval = load_screening_tables(raw_dir)
    shown = present_screening(
        screen_cached_zone(b1_rows, adjustment_rows, "AEP", 2026, date(2025, 1, 23)),
        retrieval.note,
    )
    assert shown.available is False
    assert shown.summer_peak_mw is None
    assert shown.above_embedded_mw is None
    assert shown.total_associated_mw is None
    assert shown.ltlf_vintage_year is None
    assert shown.unavailable_reason
    assert "public" in shown.unavailable_reason


def test_missing_or_malformed_workbook_does_not_invent_a_vintage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(DemoDataError, match="not on this machine"):
        load_screening_tables(tmp_path)
    raw, _paths = _empty_workbooks(tmp_path)
    manifest = _write_test_manifest(tmp_path, {name: "2026-11-20T00:00:00Z" for name in _NAMES})
    _forbid_birth_times(monkeypatch)
    with pytest.raises(PjmB1Error, match="Not an xlsx"):
        load_screening_tables(raw, manifest_path=manifest)


def test_missing_manifest_time_is_reported_not_invented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw, paths = _empty_workbooks(tmp_path)
    manifest = tmp_path / "data" / "manifest.json"
    _forbid_birth_times(monkeypatch)
    with pytest.raises(DemoDataError) as missing:
        manifest_workbook_retrieval(paths, manifest)
    assert str(missing.value) == RETRIEVAL_UNAVAILABLE
    with pytest.raises(DemoDataError) as before_parse:
        load_screening_tables(raw, manifest_path=manifest)
    assert str(before_parse.value) == RETRIEVAL_UNAVAILABLE
    _write_test_manifest(tmp_path, {_NAMES[0]: "2026-11-20T00:00:00Z"})
    with pytest.raises(DemoDataError) as one_missing:
        manifest_workbook_retrieval(paths, manifest)
    assert str(one_missing.value) == RETRIEVAL_UNAVAILABLE


def test_unknown_zone_is_rejected_and_view_errors_are_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(DemoDataError, match="Unknown PJM zone"):
        screen_cached_zone([], [], "NOPE", 2026, date(2026, 2, 6))

    def _boom(*_args, **_kwargs):
        raise PjmViewError("public but incomplete")

    monkeypatch.setattr("infralens.demo.pjm_screen.screen_zone_year", _boom)
    with pytest.raises(PjmViewError, match="incomplete"):
        screen_cached_zone([], [], "AEP", 2026, date(2026, 2, 6))


def test_display_keeps_zero_and_negative_measures_separate() -> None:
    stamp = datetime(2026, 10, 14, 18, 25, 52, tzinfo=timezone.utc)
    sources = tuple(
        ScreeningProvenance(table, "https://example.invalid/tables.xlsx", "2026-load-report-tables.xlsx", stamp)
        for table in ("B1", "B-9", "B-9b")
    )
    result = ZoneYearScreening(
        available=True,
        pjm_zone="EKPC",
        forecast_year=2026,
        as_of_date=date(2026, 2, 6),
        ltlf_vintage_year=2026,
        summer_peak_mw=0.0,
        summer_peak_10yr_cagr=-0.01,
        above_embedded_mw=0.0,
        total_associated_mw=-10.0,
        original_release_date=date(2026, 1, 14),
        revision_date=date(2026, 2, 6),
        vintage_available_at=date(2026, 2, 6),
        source_urls=("https://example.invalid/tables.xlsx",) * 3,
        retrieved_at=(stamp,) * 3,
        sources=sources,
    )
    shown = present_screening(result, "note")
    assert shown.summer_peak_mw == 0.0
    assert shown.above_embedded_mw == 0.0
    assert shown.total_associated_mw == -10.0
    assert shown.cagr_percent_per_year == pytest.approx(-1.0)
    assert "combined" not in ScreeningDisplay.__dataclass_fields__
    assert "risk_score" not in shown.__dict__
    assert "state_id" not in shown.__dict__
    assert "zones" in GEOGRAPHIC_WARNING and "states" in GEOGRAPHIC_WARNING
    assert "data-center" in LARGE_LOAD_WARNING
    assert "not added" in LARGE_LOAD_WARNING
    assert "decimal × 100" in CAGR_PERCENT_LABEL


def test_file_identity_changes_when_a_workbook_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "data" / "raw" / "pjm"
    raw.mkdir(parents=True)
    path = raw / "2025-load-report-tables.xlsx"
    path.write_bytes(b"abc")
    other = raw / "2026-load-report-tables.xlsx"
    other.write_bytes(b"abcd")
    _forbid_birth_times(monkeypatch)
    first = workbook_identity(path)
    path.write_bytes(b"abcd")
    assert workbook_identity(path) != first
    earlier, later = "2026-11-20T22:08:52.810329Z", "2026-11-20T22:08:53.714814Z"
    manifest = _write_test_manifest(tmp_path, {path.name: earlier, other.name: later})
    retrieval = manifest_workbook_retrieval((path, other), manifest)
    assert retrieval.loader_retrieved_at.tzinfo is timezone.utc
    assert retrieval.loader_retrieved_at == datetime(2026, 11, 20, 22, 8, 53, 714814, tzinfo=timezone.utc)
    assert retrieval.recorded_times_utc == ((path.name, earlier), (other.name, later))
    assert "not a PJM publication date" in retrieval.note
    assert MISSING_WORKBOOKS.startswith("The official 2025 or 2026")


def test_banner_and_finance_warning_stay_in_the_page() -> None:
    app = Path(__file__).resolve().parents[1] / "src" / "infralens" / "demo" / "app.py"
    source = app.read_text(encoding="utf-8")
    screen = (
        Path(__file__).resolve().parents[1] / "src" / "infralens" / "demo" / "pjm_screen.py"
    ).read_text(encoding="utf-8")
    assert source.index("_render_banner(banner)") < source.index("st.tabs")
    assert "PJM infrastructure screening" in source
    assert "EIA_MODEL_PRICE_WARNING" in source
    assert "width=\"stretch\"" in source
    assert "use_container_width" not in source
    assert "infralens.evaluation" not in screen
    assert "risk_score" not in screen
    assert "FAIL" in EIA_MODEL_PRICE_WARNING


def _assert_aep_2025(shown) -> None:
    assert shown.available is True
    assert shown.ltlf_vintage_year == 2025
    assert shown.summer_peak_mw == 25788.0
    assert shown.summer_peak_10yr_cagr == 0.0547154909
    assert shown.cagr_percent_per_year == pytest.approx(5.47154909)
    assert shown.above_embedded_mw == 3621.0
    assert shown.total_associated_mw == 3936.0
    assert shown.original_release_date == date(2025, 1, 24)
    assert shown.revision_date is None
    assert shown.source_files == ("2025-load-report-tables.xlsx",) * 3
    assert shown.source_tables == ("B1", "B-9", "B-9b")

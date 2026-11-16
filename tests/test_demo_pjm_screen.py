"""Demo presentation of the existing PJM screening view. It does not reparse rules."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from infralens.demo.foundation import DemoDataError, default_artifact_paths
from infralens.demo.pjm_screen import (
    CAGR_PERCENT_LABEL,
    GEOGRAPHIC_WARNING,
    LARGE_LOAD_WARNING,
    MISSING_WORKBOOKS,
    RETRIEVAL_UNAVAILABLE,
    ScreeningDisplay,
    load_screening_tables,
    local_workbook_retrieved_at,
    present_screening,
    screen_cached_zone,
    workbook_identity,
    workbook_paths,
)
from infralens.finance.annual_cost import EIA_MODEL_PRICE_WARNING
from infralens.screening.pjm_b1 import PjmB1Error
from infralens.screening.pjm_view import PjmViewError, ScreeningProvenance, ZoneYearScreening

_BIRTH_ATTRIBUTES = ("st_birthtime", "st_birthtime_ns")


class _BirthTimeStat:
    """A real ``os.stat_result`` with the file-creation time set or removed.

    macOS reports ``st_birthtime``; Python on Linux does not. Tests that exercise
    the creation-time rule set it explicitly so they behave the same on both.
    """

    def __init__(self, real: object, birth: float | None) -> None:
        self._real = real
        self._birth = birth

    def __getattr__(self, name: str) -> object:
        if name in _BIRTH_ATTRIBUTES:
            if self._birth is None:
                raise AttributeError(name)
            return self._birth if name == "st_birthtime" else int(self._birth * 1_000_000_000)
        return getattr(self._real, name)


def _set_birth_times(monkeypatch: pytest.MonkeyPatch, births: dict[str, float] | None) -> None:
    """Report the given creation time per file name, or none at all (as on Linux)."""

    real_stat = Path.stat

    def stat(self: Path, *args: object, **kwargs: object) -> _BirthTimeStat:
        birth = None if births is None else births.get(self.name)
        return _BirthTimeStat(real_stat(self, *args, **kwargs), birth)

    monkeypatch.setattr(Path, "stat", stat)


def test_aep_cutoffs_match_the_cached_workbooks() -> None:
    raw_dir = default_artifact_paths().pjm_2025_tables.parent
    if not all(path.is_file() for path in workbook_paths(raw_dir)):
        pytest.skip("Official PJM Tables workbooks are not in data/raw/pjm.")
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
    assert current.retrieved_at == (retrieval.loader_retrieved_at.isoformat(),) * 3
    assert current.above_embedded_mw != current.total_associated_mw


def test_date_before_the_2025_release_is_unpublished() -> None:
    raw_dir = default_artifact_paths().pjm_2025_tables.parent
    if not all(path.is_file() for path in workbook_paths(raw_dir)):
        pytest.skip("Official PJM Tables workbooks are not in data/raw/pjm.")
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
    names = ("2025-load-report-tables.xlsx", "2026-load-report-tables.xlsx")
    for name in names:
        (tmp_path / name).write_bytes(b"")
    _set_birth_times(monkeypatch, {name: 1_760_000_000.0 for name in names})
    with pytest.raises(PjmB1Error, match="Not an xlsx"):
        load_screening_tables(tmp_path)


def test_missing_creation_time_is_reported_not_invented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = ("2025-load-report-tables.xlsx", "2026-load-report-tables.xlsx")
    for name in names:
        (tmp_path / name).write_bytes(b"")
    _set_birth_times(monkeypatch, None)
    paths = tuple(tmp_path / name for name in names)
    with pytest.raises(DemoDataError) as missing:
        local_workbook_retrieved_at(paths)
    assert str(missing.value) == RETRIEVAL_UNAVAILABLE
    with pytest.raises(DemoDataError) as before_parse:
        load_screening_tables(tmp_path)
    assert str(before_parse.value) == RETRIEVAL_UNAVAILABLE
    _set_birth_times(monkeypatch, {names[0]: 1_760_000_000.0})
    with pytest.raises(DemoDataError) as one_missing:
        local_workbook_retrieved_at(paths)
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


def test_file_identity_uses_size_and_creation_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "2025-load-report-tables.xlsx"
    path.write_bytes(b"abc")
    other = tmp_path / "2026-load-report-tables.xlsx"
    other.write_bytes(b"abcd")
    first = workbook_identity(path)
    path.write_bytes(b"abcd")
    assert workbook_identity(path) != first
    earlier, later = 1_760_000_000.0, 1_760_086_400.0
    _set_birth_times(monkeypatch, {path.name: earlier, other.name: later})
    retrieval = local_workbook_retrieved_at((path, other))
    assert retrieval.loader_retrieved_at.tzinfo is timezone.utc
    assert retrieval.loader_retrieved_at == datetime.fromtimestamp(later, tz=timezone.utc)
    assert retrieval.file_creation_times_utc == (
        (path.name, datetime.fromtimestamp(earlier, tz=timezone.utc).isoformat()),
        (other.name, datetime.fromtimestamp(later, tz=timezone.utc).isoformat()),
    )
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

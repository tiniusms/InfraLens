"""Point-in-time view over validated PJM Table B1, B-9, and B-9b rows.

One result uses a single ``ltlf_vintage_year``. The selected vintage is the
newest one whose file-level ``vintage_available_at`` is on or before
``as_of_date`` and that publishes the requested zone and forecast year.
B-9 and B-9b stay separate megawatt fields. They are not added, and they
are not data-center demand.

A vintage that is already public but missing one of the three observations,
or whose rows disagree on keys or publication dates, raises
``PjmViewError``. The view does not substitute an older vintage for that
defect. A forecast year outside a vintage's published horizon is not a
defect: the 2026 workbook starts at 2026, so forecast year 2025 stays on
the 2025 vintage.

No published vintage produces ``ZoneYearScreening.available is False``.
That is unpublished data, not a malformed record. The 2024 PDF is not
parsed, so this view cannot return a 2024 vintage.

Zone results are not allocated to a state and are not joined to EIA prices.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence

from infralens.screening.pjm_adjustments import (
    ABOVE_EMBEDDED_MW,
    TOTAL_ASSOCIATED_MW,
    AdjustmentRow,
)
from infralens.screening.pjm_b1 import B1Row

_MEASURE_TABLES = {
    ABOVE_EMBEDDED_MW: "B-9",
    TOTAL_ASSOCIATED_MW: "B-9b",
}
_UNAVAILABLE_REASON = (
    "No PJM Tables vintage covering this zone and forecast year was public "
    "on the as-of date."
)


class PjmViewError(ValueError):
    """The screening view refused a malformed or contradictory record set."""


@dataclass(frozen=True)
class ScreeningProvenance:
    """One source table inside the selected vintage."""

    source_table: str
    source_url: str
    source_file: str
    retrieved_at: datetime | None


@dataclass(frozen=True)
class ZoneYearScreening:
    """One zone and forecast year from a single Tables vintage.

    Measure fields are ``None`` only when ``available`` is False. A published
    zero stays ``0.0``. A published negative stays negative.
    """

    available: bool
    pjm_zone: str
    forecast_year: int
    as_of_date: date
    ltlf_vintage_year: int | None
    summer_peak_mw: float | None
    summer_peak_10yr_cagr: float | None
    above_embedded_mw: float | None
    total_associated_mw: float | None
    original_release_date: date | None
    revision_date: date | None
    vintage_available_at: date | None
    source_urls: tuple[str, ...]
    retrieved_at: tuple[datetime | None, ...]
    sources: tuple[ScreeningProvenance, ...]
    unavailable_reason: str | None = None


def screen_zone_year(
    b1_rows: Sequence[B1Row],
    adjustment_rows: Sequence[AdjustmentRow],
    pjm_zone: str,
    forecast_year: int,
    as_of_date: date | str,
) -> ZoneYearScreening:
    """Return the newest public complete vintage for one zone and year.

    ``available`` is False when every covering vintage is still unpublished.
    Incomplete or contradictory rows on the newest public covering vintage
    raise ``PjmViewError`` instead of falling back.
    """
    observations = _public_observations(
        b1_rows,
        adjustment_rows,
        pjm_zone,
        forecast_year,
        as_of_date,
        stop_at_first=True,
    )
    if not observations:
        return _unavailable(pjm_zone, forecast_year, _require_date(as_of_date, "as_of_date"))
    return observations[0]


def compare_zone_year_vintages(
    b1_rows: Sequence[B1Row],
    adjustment_rows: Sequence[AdjustmentRow],
    pjm_zone: str,
    forecast_year: int,
    as_of_date: date | str,
) -> tuple[ZoneYearScreening, ...]:
    """Return each public complete vintage, newest first, without blending.

    A vintage that is public but incomplete or contradictory raises, including
    an older vintage. ``screen_zone_year`` stops at the newest public vintage
    and does not audit older ones. Vintages that are not yet public, and
    vintages whose horizon does not include ``forecast_year``, are omitted.
    """
    return _public_observations(
        b1_rows,
        adjustment_rows,
        pjm_zone,
        forecast_year,
        as_of_date,
        stop_at_first=False,
    )


def _public_observations(
    b1_rows: Sequence[B1Row],
    adjustment_rows: Sequence[AdjustmentRow],
    pjm_zone: str,
    forecast_year: int,
    as_of_date: date | str,
    *,
    stop_at_first: bool,
) -> tuple[ZoneYearScreening, ...]:
    as_of = _require_date(as_of_date, "as_of_date")
    zone = _require_zone(pjm_zone)
    year = _require_year(forecast_year)
    for row in b1_rows:
        _require_consistent_dates(row, f"{row.pjm_zone} Table B1 vintage {row.ltlf_vintage_year}")
    for row in adjustment_rows:
        _require_consistent_dates(
            row,
            f"{row.pjm_zone} {row.source_table} vintage {row.ltlf_vintage_year}",
        )
    matching_b1 = [
        row
        for row in b1_rows
        if row.pjm_zone == zone and row.forecast_year == year
    ]
    matching_adjustments = [
        row
        for row in adjustment_rows
        if row.pjm_zone == zone and row.forecast_year == year
    ]
    vintage_ids = sorted(
        {row.ltlf_vintage_year for row in matching_b1}
        | {row.ltlf_vintage_year for row in matching_adjustments},
        reverse=True,
    )
    selected: list[ZoneYearScreening] = []
    for vintage in vintage_ids:
        peaks = [row for row in matching_b1 if row.ltlf_vintage_year == vintage]
        adjustments = [
            row for row in matching_adjustments if row.ltlf_vintage_year == vintage
        ]
        identity = _shared_publication(peaks, adjustments, zone, vintage, year)
        if identity.vintage_available_at > as_of:
            continue
        selected.append(
            _complete_observation(
                peaks,
                adjustments,
                zone,
                year,
                as_of,
                vintage,
                identity,
            )
        )
        if stop_at_first:
            break
    return tuple(selected)


@dataclass(frozen=True)
class _Publication:
    original_release_date: date
    revision_date: date | None
    vintage_available_at: date
    source_url: str
    source_file: str


def _shared_publication(
    peaks: Sequence[B1Row],
    adjustments: Sequence[AdjustmentRow],
    zone: str,
    vintage: int,
    forecast_year: int,
) -> _Publication:
    rows = [*peaks, *adjustments]
    if not rows:
        raise PjmViewError(
            f"{zone} vintage {vintage} forecast year {forecast_year} has no observations."
        )
    first = rows[0]
    original, revision, available = _require_consistent_dates(
        first,
        f"{zone} vintage {vintage}",
    )
    for row in rows[1:]:
        other_original, other_revision, other_available = _require_consistent_dates(
            row,
            f"{zone} vintage {vintage}",
        )
        if (
            other_original != original
            or other_revision != revision
            or other_available != available
        ):
            raise PjmViewError(
                f"{zone} vintage {vintage} forecast year {forecast_year} "
                "has contradictory publication dates."
            )
        if row.source_url != first.source_url or row.source_file != first.source_file:
            raise PjmViewError(
                f"{zone} vintage {vintage} forecast year {forecast_year} "
                "has contradictory source URL or filename."
            )
    return _Publication(
        original_release_date=original,
        revision_date=revision,
        vintage_available_at=available,
        source_url=first.source_url,
        source_file=first.source_file,
    )


def _complete_observation(
    peaks: Sequence[B1Row],
    adjustments: Sequence[AdjustmentRow],
    zone: str,
    forecast_year: int,
    as_of: date,
    vintage: int,
    identity: _Publication,
) -> ZoneYearScreening:
    label = f"{zone} vintage {vintage} forecast year {forecast_year}"
    if len(peaks) != 1:
        if len(peaks) > 1:
            raise PjmViewError(f"Duplicate Table B1 observation for {label}.")
        raise PjmViewError(
            f"Vintage {vintage} is public but does not have complete B1, B-9, "
            f"and B-9b observations for {label}."
        )
    by_measure: dict[str, list[AdjustmentRow]] = {}
    for row in adjustments:
        if row.adjustment_measure not in _MEASURE_TABLES:
            raise PjmViewError(
                f"Unexpected adjustment measure {row.adjustment_measure!r} for {label}."
            )
        expected_table = _MEASURE_TABLES[row.adjustment_measure]
        if row.source_table != expected_table:
            raise PjmViewError(
                f"{row.adjustment_measure} does not match source table {row.source_table} "
                f"for {label}."
            )
        by_measure.setdefault(row.adjustment_measure, []).append(row)
    for measure in (ABOVE_EMBEDDED_MW, TOTAL_ASSOCIATED_MW):
        found = by_measure.get(measure, [])
        if len(found) > 1:
            raise PjmViewError(
                f"Duplicate {_MEASURE_TABLES[measure]} observation for {label}."
            )
        if len(found) != 1:
            raise PjmViewError(
                f"Vintage {vintage} is public but does not have complete B1, B-9, "
                f"and B-9b observations for {label}."
            )
    if set(by_measure) != {ABOVE_EMBEDDED_MW, TOTAL_ASSOCIATED_MW}:
        raise PjmViewError(
            f"Vintage {vintage} is public but does not have complete B1, B-9, "
            f"and B-9b observations for {label}."
        )
    peak = peaks[0]
    above = by_measure[ABOVE_EMBEDDED_MW][0]
    total = by_measure[TOTAL_ASSOCIATED_MW][0]
    summer_peak_mw = _require_finite(peak.summer_peak_mw, f"{label} summer peak")
    cagr = _require_finite(peak.summer_peak_10yr_cagr, f"{label} 10-year growth rate")
    above_mw = _require_finite(above.adjustment_mw, f"{label} B-9")
    total_mw = _require_finite(total.adjustment_mw, f"{label} B-9b")
    sources = (
        ScreeningProvenance("B1", peak.source_url, peak.source_file, peak.retrieved_at),
        ScreeningProvenance(
            "B-9",
            above.source_url,
            above.source_file,
            above.retrieved_at,
        ),
        ScreeningProvenance(
            "B-9b",
            total.source_url,
            total.source_file,
            total.retrieved_at,
        ),
    )
    return ZoneYearScreening(
        available=True,
        pjm_zone=zone,
        forecast_year=forecast_year,
        as_of_date=as_of,
        ltlf_vintage_year=vintage,
        summer_peak_mw=summer_peak_mw,
        summer_peak_10yr_cagr=cagr,
        above_embedded_mw=above_mw,
        total_associated_mw=total_mw,
        original_release_date=identity.original_release_date,
        revision_date=identity.revision_date,
        vintage_available_at=identity.vintage_available_at,
        source_urls=tuple(source.source_url for source in sources),
        retrieved_at=tuple(source.retrieved_at for source in sources),
        sources=sources,
        unavailable_reason=None,
    )


def _unavailable(zone: str, forecast_year: int, as_of: date) -> ZoneYearScreening:
    return ZoneYearScreening(
        available=False,
        pjm_zone=zone,
        forecast_year=forecast_year,
        as_of_date=as_of,
        ltlf_vintage_year=None,
        summer_peak_mw=None,
        summer_peak_10yr_cagr=None,
        above_embedded_mw=None,
        total_associated_mw=None,
        original_release_date=None,
        revision_date=None,
        vintage_available_at=None,
        source_urls=(),
        retrieved_at=(),
        sources=(),
        unavailable_reason=_UNAVAILABLE_REASON,
    )


def _require_consistent_dates(
    row: B1Row | AdjustmentRow,
    label: str,
) -> tuple[date, date | None, date]:
    original = _require_date(row.original_release_date, f"original_release_date for {label}")
    if row.revision_date is None:
        revision = None
    else:
        revision = _require_date(row.revision_date, f"revision_date for {label}")
    available = _require_date(row.vintage_available_at, f"vintage_available_at for {label}")
    expected = revision if revision is not None else original
    if available != expected:
        raise PjmViewError(
            f"{label} vintage_available_at does not match the file-level revision rule."
        )
    return original, revision, available


def _require_finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PjmViewError(f"{label} is not a plain number.")
    number = float(value)
    if not math.isfinite(number):
        raise PjmViewError(f"{label} is not a finite number.")
    return number


def _require_zone(pjm_zone: object) -> str:
    if not isinstance(pjm_zone, str) or not pjm_zone.strip():
        raise PjmViewError("pjm_zone is missing.")
    return pjm_zone


def _require_year(forecast_year: object) -> int:
    if isinstance(forecast_year, bool) or not isinstance(forecast_year, int):
        raise PjmViewError(f"forecast_year is not an integer: {forecast_year!r}.")
    return forecast_year


def _require_date(value: date | datetime | str | None, field_name: str) -> date:
    if value is None or value == "":
        raise PjmViewError(f"{field_name} is missing.")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise PjmViewError(f"{field_name} is not an ISO date: {value!r}.") from exc
    raise PjmViewError(f"{field_name} is not a date: {value!r}.")

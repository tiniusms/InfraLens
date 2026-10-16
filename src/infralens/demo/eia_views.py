"""Observed EIA prices and the closed holdout chart.

Parsing and validation live here so tests do not start Streamlit. Nothing in
this module trains a model, calls an API, or scores the holdout again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pandas as pd

from infralens.demo.foundation import (
    FROZEN_EXTRACT_ID,
    TYPED_PRICE_LABEL,
    DemoDataError,
    HoldoutBanner,
)

DEMO_STATES: tuple[str, ...] = ("VA", "PA", "OH", "MD", "NJ")
OBSERVED_ROLE = "observed"
CLOSED_PREDICTION_ROLE = "closed_prediction"
HYPOTHETICAL_ROLE = "hypothetical"

OBSERVED_PRICE_LABEL = "Historical observed commercial average price (cents/kWh)"
HOLDOUT_SECTION_LABEL = "Closed historical evaluation, not a forward forecast"
ACTUAL_SERIES_LABEL = "Actual observed price"
RIDGE_SERIES_LABEL = "Ridge closed prediction"
NAIVE_SERIES_LABEL = "Seasonal-naive closed prediction"
SUMMARY_SOURCE_LABEL = "docs/final_eia_holdout_oneshot.json"

HISTORY_LIMITATIONS = (
    "Observed EIA commercial average retail price to ultimate customers. "
    "It is a public price proxy, not a data-center tariff, interconnection price, or PPA. "
    "The period is the sales month, not the publication date. "
    "The frozen extract ends at 2026-06. This chart is not a forecast."
)
MISSING_PRICE_HISTORY = (
    "EIA commercial price history is not on this machine, so the observed-price chart is unavailable. "
    "The committed holdout summary and the cost calculator still run. "
    "Do not download a substitute or rerun the final EIA holdout from this page."
)
MISSING_HOLDOUT_CHART = (
    "The frozen holdout case file is not on this machine, so the closed-evaluation chart is unavailable. "
    "A Ridge price cannot be invented to fill the chart. "
    "The committed FAIL summary and the cost calculator still run."
)

# Closed origin/target pairs. The chart axis is the target month only.
_ORIGIN_BY_TARGET: dict[str, str] = {
    "2025-07": "2024-07-31",
    "2025-08": "2024-08-31",
    "2025-09": "2024-09-30",
    "2025-10": "2024-10-31",
    "2025-11": "2024-11-30",
    "2025-12": "2024-12-31",
    "2026-01": "2025-01-31",
    "2026-02": "2025-02-28",
    "2026-03": "2025-03-31",
    "2026-04": "2025-04-30",
    "2026-05": "2025-05-31",
    "2026-06": "2025-06-30",
}
HOLDOUT_TARGET_MONTHS: tuple[str, ...] = tuple(_ORIGIN_BY_TARGET)
_FROZEN_HISTORY_END = "2026-06"
_MONTH_TEXT = re.compile(r"^\d{4}-\d{2}$")
_HISTORY_COLUMNS = ("period", "state_id", "sector_id", "price_cents_per_kwh")
_POINT_COLUMNS = (
    "evaluation_stage",
    "state_id",
    "forecast_origin",
    "target_month",
    "actual",
    "ridge_prediction",
    "seasonal_naive_prediction",
    "skip_reason",
)
_INTERVAL_COLUMNS = (
    "interval_lower",
    "interval_upper",
    "interval_status",
    "interval_covered",
)


@dataclass(frozen=True)
class ChartSeries:
    """One labeled series and the kind of number it represents."""

    name: str
    role: str
    time_axis: str


@dataclass(frozen=True)
class HistoryPoint:
    """One observed commercial average price."""

    state_id: str
    period: str
    observed_price_cents_per_kwh: Decimal


@dataclass(frozen=True)
class PriceHistory:
    """Validated observed prices for the five demo states."""

    extract_id: str
    points: tuple[HistoryPoint, ...]
    earliest_period: str
    latest_period: str
    states: tuple[str, ...]
    limitations: str
    retrieved_at: str | None
    source_name: str | None
    price_units: str | None
    row_count: int


@dataclass(frozen=True)
class HoldoutPoint:
    """One closed holdout case. ``forecast_origin`` is provenance, not the chart axis."""

    state_id: str
    target_month: str
    forecast_origin: str
    actual_cents_per_kwh: Decimal
    ridge_prediction_cents_per_kwh: Decimal
    seasonal_naive_prediction_cents_per_kwh: Decimal
    interval_lower_cents_per_kwh: Decimal | None
    interval_upper_cents_per_kwh: Decimal | None
    interval_covered: bool | None


@dataclass(frozen=True)
class HoldoutComparison:
    """Sixty closed cases, sorted by state display order and target month."""

    points: tuple[HoldoutPoint, ...]
    origin_start: str
    origin_end: str
    target_start: str
    target_end: str
    has_intervals: bool
    empirical_interval_coverage: Decimal | None
    interval_warning: str | None
    row_count: int

    def point_for(self, state_id: str, target_month: str) -> HoldoutPoint:
        matches = [
            point
            for point in self.points
            if point.state_id == state_id and point.target_month == target_month
        ]
        if len(matches) != 1:
            raise DemoDataError(f"No closed holdout point for {state_id} {target_month}.")
        return matches[0]


@dataclass(frozen=True)
class HoldoutProvenance:
    """Methodology shown beside the holdout chart. The axis is the target month."""

    origin_start: str
    origin_end: str
    target_start: str
    target_end: str
    extract_id: str
    summary_source: str
    feature_set_id: str
    evaluation_stage: str
    axis: str = "target_month"


def chart_series_catalog() -> tuple[ChartSeries, ...]:
    """Observed, closed-prediction, and hypothetical labels. No production forecast."""

    return (
        ChartSeries(OBSERVED_PRICE_LABEL, OBSERVED_ROLE, "period"),
        ChartSeries(ACTUAL_SERIES_LABEL, OBSERVED_ROLE, "target_month"),
        ChartSeries(RIDGE_SERIES_LABEL, CLOSED_PREDICTION_ROLE, "target_month"),
        ChartSeries(NAIVE_SERIES_LABEL, CLOSED_PREDICTION_ROLE, "target_month"),
        ChartSeries(TYPED_PRICE_LABEL, HYPOTHETICAL_ROLE, "scenario"),
    )


def load_price_history(path: Path, *, extract_id: str | None = None) -> PriceHistory:
    """Read observed commercial prices. A missing file stays missing."""

    if not path.is_file():
        raise DemoDataError(MISSING_PRICE_HISTORY)
    if extract_id is not None and path.name != extract_id:
        raise DemoDataError(
            f"Price history file {path.name} is not the frozen extract {extract_id}."
        )
    frame = pd.read_parquet(path)
    missing = [column for column in _HISTORY_COLUMNS if column not in frame.columns]
    if missing:
        raise DemoDataError("Price history is missing columns: " + ", ".join(missing))
    if frame.empty:
        raise DemoDataError("Price history has no rows.")
    if not frame["sector_id"].eq("COM").all():
        raise DemoDataError("Price history includes a sector other than commercial (COM).")
    observed = set(frame["state_id"].astype(str))
    if observed != set(DEMO_STATES):
        raise DemoDataError(
            "Price history must contain exactly VA, PA, OH, MD, and NJ. "
            f"Found {sorted(observed)}."
        )
    points: list[HistoryPoint] = []
    for row in frame.itertuples(index=False):
        period = _require_month(row.period, "history period")
        if period > _FROZEN_HISTORY_END:
            raise DemoDataError("Price history continues past the frozen extract end of 2026-06.")
        price = _require_decimal(row.price_cents_per_kwh, "price_cents_per_kwh")
        points.append(
            HistoryPoint(
                state_id=str(row.state_id),
                period=period,
                observed_price_cents_per_kwh=price,
            )
        )
    _require_unique_periods(points)
    _require_contiguous_through_end(points)
    retrieved_at = _single_text(frame, "retrieved_at")
    source_name = _single_text(frame, "source")
    price_units = _single_text(frame, "price_units")
    periods = sorted(point.period for point in points)
    ordered = tuple(sorted(points, key=lambda point: (DEMO_STATES.index(point.state_id), point.period)))
    return PriceHistory(
        extract_id=path.name,
        points=ordered,
        earliest_period=periods[0],
        latest_period=periods[-1],
        states=DEMO_STATES,
        limitations=HISTORY_LIMITATIONS,
        retrieved_at=retrieved_at,
        source_name=source_name,
        price_units=price_units,
        row_count=len(ordered),
    )


def price_plot_frame(history: PriceHistory, state_id: str) -> pd.DataFrame:
    """One state's observed prices, sorted by sales month."""

    if state_id not in DEMO_STATES:
        raise DemoDataError(f"Unknown state {state_id}.")
    rows = [point for point in history.points if point.state_id == state_id]
    frame = pd.DataFrame(
        {
            "period": [point.period for point in rows],
            "observed_commercial_average_price_cents_per_kwh": [
                float(point.observed_price_cents_per_kwh) for point in rows
            ],
            "series": OBSERVED_PRICE_LABEL,
            "role": OBSERVED_ROLE,
        }
    )
    return frame.sort_values("period", kind="mergesort").reset_index(drop=True)


def load_holdout_comparison(path: Path) -> HoldoutComparison:
    """Read the frozen 60-case table. Incomplete interval columns are not filled in."""

    if not path.is_file():
        raise DemoDataError(MISSING_HOLDOUT_CHART)
    frame = pd.read_parquet(path)
    missing = [column for column in _POINT_COLUMNS if column not in frame.columns]
    if missing:
        raise DemoDataError("Holdout case file is missing columns: " + ", ".join(missing))
    present_intervals = [column for column in _INTERVAL_COLUMNS if column in frame.columns]
    if present_intervals and len(present_intervals) != len(_INTERVAL_COLUMNS):
        raise DemoDataError(
            "Holdout interval columns are incomplete and will not be synthesized."
        )
    has_intervals = len(present_intervals) == len(_INTERVAL_COLUMNS)
    if not frame["evaluation_stage"].eq("final_holdout").all():
        raise DemoDataError("Holdout case file is not the final holdout stage.")
    if not frame["skip_reason"].isna().all():
        raise DemoDataError("Holdout chart expects every frozen case to be scored.")
    if len(frame) != 60:
        raise DemoDataError(f"Holdout chart expects 60 cases and found {len(frame)}.")
    points: list[HoldoutPoint] = []
    for row in frame.itertuples(index=False):
        state_id = str(row.state_id)
        if state_id not in DEMO_STATES:
            raise DemoDataError(f"Holdout case has an unexpected state {state_id}.")
        target_month = _require_month(row.target_month, "target month")
        origin = _origin_text(row.forecast_origin)
        expected_origin = _ORIGIN_BY_TARGET.get(target_month)
        if expected_origin is None or origin != expected_origin:
            raise DemoDataError(
                "Holdout origin and target month do not match the closed window. "
                "The chart will not plot an origin date as a target month."
            )
        lower, upper, covered = _interval_values(row, has_intervals)
        points.append(
            HoldoutPoint(
                state_id=state_id,
                target_month=target_month,
                forecast_origin=origin,
                actual_cents_per_kwh=_require_decimal(row.actual, "actual"),
                ridge_prediction_cents_per_kwh=_require_decimal(row.ridge_prediction, "ridge_prediction"),
                seasonal_naive_prediction_cents_per_kwh=_require_decimal(
                    row.seasonal_naive_prediction, "seasonal_naive_prediction"
                ),
                interval_lower_cents_per_kwh=lower,
                interval_upper_cents_per_kwh=upper,
                interval_covered=covered,
            )
        )
    _require_holdout_grid(points)
    coverage, warning = _coverage(points, has_intervals)
    ordered = tuple(
        sorted(points, key=lambda point: (DEMO_STATES.index(point.state_id), point.target_month))
    )
    origins = sorted(point.forecast_origin for point in ordered)
    return HoldoutComparison(
        points=ordered,
        origin_start=origins[0],
        origin_end=origins[-1],
        target_start=HOLDOUT_TARGET_MONTHS[0],
        target_end=HOLDOUT_TARGET_MONTHS[-1],
        has_intervals=has_intervals,
        empirical_interval_coverage=coverage,
        interval_warning=warning,
        row_count=len(ordered),
    )


def holdout_plot_frame(comparison: HoldoutComparison, state_id: str) -> pd.DataFrame:
    """Actual, Ridge, and seasonal naive by target month. Origins are omitted."""

    if state_id not in DEMO_STATES:
        raise DemoDataError(f"Unknown state {state_id}.")
    rows = [point for point in comparison.points if point.state_id == state_id]
    payload: dict[str, list[object]] = {
        "target_month": [point.target_month for point in rows],
        "actual_observed_cents_per_kwh": [float(point.actual_cents_per_kwh) for point in rows],
        "ridge_closed_prediction_cents_per_kwh": [
            float(point.ridge_prediction_cents_per_kwh) for point in rows
        ],
        "seasonal_naive_closed_prediction_cents_per_kwh": [
            float(point.seasonal_naive_prediction_cents_per_kwh) for point in rows
        ],
    }
    if comparison.has_intervals:
        payload["interval_lower_cents_per_kwh"] = [
            float(point.interval_lower_cents_per_kwh) for point in rows  # type: ignore[arg-type]
        ]
        payload["interval_upper_cents_per_kwh"] = [
            float(point.interval_upper_cents_per_kwh) for point in rows  # type: ignore[arg-type]
        ]
    frame = pd.DataFrame(payload)
    frame = frame.sort_values("target_month", kind="mergesort").reset_index(drop=True)
    if list(frame["target_month"]) != list(HOLDOUT_TARGET_MONTHS):
        raise DemoDataError("Holdout chart months are not the closed target window in order.")
    return frame


def holdout_line_frame(plot: pd.DataFrame) -> pd.DataFrame:
    """Long form for the three closed-evaluation lines. The time key is target month."""

    if "forecast_origin" in plot.columns:
        raise DemoDataError("Holdout plot frame includes forecast origins. Remove them before charting.")
    mapping = (
        ("actual_observed_cents_per_kwh", ACTUAL_SERIES_LABEL, OBSERVED_ROLE),
        ("ridge_closed_prediction_cents_per_kwh", RIDGE_SERIES_LABEL, CLOSED_PREDICTION_ROLE),
        (
            "seasonal_naive_closed_prediction_cents_per_kwh",
            NAIVE_SERIES_LABEL,
            CLOSED_PREDICTION_ROLE,
        ),
    )
    pieces: list[pd.DataFrame] = []
    for column, label, role in mapping:
        pieces.append(
            pd.DataFrame(
                {
                    "target_month": plot["target_month"],
                    "series": label,
                    "role": role,
                    "cents_per_kwh": plot[column],
                }
            )
        )
    return pd.concat(pieces, ignore_index=True)


def holdout_provenance(comparison: HoldoutComparison, banner: HoldoutBanner) -> HoldoutProvenance:
    """Pair the case-file window with the committed summary identity."""

    return HoldoutProvenance(
        origin_start=comparison.origin_start,
        origin_end=comparison.origin_end,
        target_start=comparison.target_start,
        target_end=comparison.target_end,
        extract_id=banner.extract_id,
        summary_source=SUMMARY_SOURCE_LABEL,
        feature_set_id=banner.feature_set_id,
        evaluation_stage=banner.evaluation_stage,
    )


def interval_band_label(coverage: Decimal) -> str:
    """State the stored interval's empirical coverage. Zero stays zero."""

    shown = "0%" if coverage == 0 else f"{coverage}"
    return (
        "Stored Ridge residual interval, nominal 80%. "
        f"Empirical coverage on this closed holdout is {shown}. "
        "Not a forward-looking forecast interval."
    )


def _coverage(
    points: list[HoldoutPoint],
    has_intervals: bool,
) -> tuple[Decimal | None, str | None]:
    if not has_intervals:
        return None, None
    covered = sum(1 for point in points if point.interval_covered)
    coverage = Decimal(covered) / Decimal(len(points))
    return coverage, interval_band_label(coverage)


def _interval_values(
    row: object,
    has_intervals: bool,
) -> tuple[Decimal | None, Decimal | None, bool | None]:
    if not has_intervals:
        return None, None, None
    status = getattr(row, "interval_status")
    if status != "interval":
        raise DemoDataError(
            "A holdout interval status is not the stored residual interval and will not be replaced."
        )
    lower = _require_decimal(getattr(row, "interval_lower"), "interval_lower")
    upper = _require_decimal(getattr(row, "interval_upper"), "interval_upper")
    if lower > upper:
        raise DemoDataError("A stored interval lower bound is above its upper bound.")
    covered = getattr(row, "interval_covered")
    if type(covered).__name__ not in {"bool", "bool_"}:
        raise DemoDataError("interval_covered must be true or false. It will not be inferred.")
    return lower, upper, bool(covered)


def _require_holdout_grid(points: list[HoldoutPoint]) -> None:
    seen: set[tuple[str, str]] = set()
    for point in points:
        key = (point.state_id, point.target_month)
        if key in seen:
            raise DemoDataError(f"Duplicate holdout case {key}.")
        seen.add(key)
    for state_id in DEMO_STATES:
        months = [point.target_month for point in points if point.state_id == state_id]
        if sorted(months) != list(HOLDOUT_TARGET_MONTHS):
            raise DemoDataError(f"{state_id} does not have the 12 closed target months once each.")


def _require_unique_periods(points: list[HistoryPoint]) -> None:
    seen: set[tuple[str, str]] = set()
    for point in points:
        key = (point.state_id, point.period)
        if key in seen:
            raise DemoDataError(f"Duplicate price observation {key}.")
        seen.add(key)


def _require_contiguous_through_end(points: list[HistoryPoint]) -> None:
    for state_id in DEMO_STATES:
        periods = sorted(point.period for point in points if point.state_id == state_id)
        if not periods or periods[-1] != _FROZEN_HISTORY_END:
            raise DemoDataError(f"{state_id} price history does not include 2026-06.")
        indexes = [_month_index(period) for period in periods]
        expected = list(range(indexes[0], indexes[-1] + 1))
        if indexes != expected:
            raise DemoDataError(f"{state_id} price history has a gap and will not be interpolated.")


def _single_text(frame: pd.DataFrame, column: str) -> str | None:
    if column not in frame.columns:
        return None
    values = {str(value) for value in frame[column].dropna().unique()}
    if len(values) != 1:
        raise DemoDataError(f"Price history column {column} is not a single vintage.")
    return next(iter(values))


def _require_month(value: object, label: str) -> str:
    text = str(value)
    if not _MONTH_TEXT.match(text):
        raise DemoDataError(f"{label} is not a month: {value!r}.")
    month = int(text[5:7])
    if month < 1 or month > 12:
        raise DemoDataError(f"{label} is not a month: {value!r}.")
    return text


def _month_index(period: str) -> int:
    year, month = period.split("-")
    return int(year) * 12 + int(month)


def _origin_text(value: object) -> str:
    try:
        return pd.Timestamp(value).date().isoformat()
    except (TypeError, ValueError) as exc:
        raise DemoDataError(f"Holdout origin is not a date: {value!r}.") from exc


def _require_decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise DemoDataError(f"{label} is missing and will not be filled in.")
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError) as exc:
        raise DemoDataError(f"{label} is not a number and will not be filled in.") from exc
    if not number.is_finite():
        raise DemoDataError(f"{label} is not a finite number.")
    return number


def frozen_extract_name() -> str:
    """The only price extract this page charts."""

    return FROZEN_EXTRACT_ID

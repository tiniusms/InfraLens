"""Point-in-time EIA features for the Ridge and tree candidates.

Every observation used below must satisfy
``assumed_available_at <= forecast_origin`` (first day of month m+3).

The target is still commercial price 12 months after the forecast origin.
These features are lagged inputs only. They are not a new target.

Initial set, chosen because each item is knowable at the origin:

* ``price_latest`` — commercial price on the latest EIA month available at
  the origin, for that state.
* ``price_same_month`` — availability-adjusted seasonal-naive price: the
  most recent same calendar month as the target that is already available.
  This reuses the baseline analog. It is not a second seasonal rule.
* ``price_yoy_change`` — ``price_latest`` minus the price 12 months earlier.
  Both months must be present. A missing lag skips the case.
* ``price_trail12_mean`` — mean price over the 12 consecutive calendar months
  ending at the latest available month. A hole in that window skips the case.
  The mean is not computed by skipping the hole or by borrowing a later month.
* ``sales_latest`` / ``sales_yoy_change`` — sales on the same months as the
  latest price and its year-over-year lag.
* ``state_id`` — known geography. Ridge one-hot encodes it inside each
  training fold. The tree model ordinal-encodes it inside each training fold.
* ``target_calendar_month`` — calendar month of the target. The target is
  exactly 12 months after the origin, so this is also the origin month. It
  is a calendar label, not an EIA observation. It is encoded the same way
  as ``state_id``.

Excluded on purpose:

* ``revenue_million_usd`` — EIA price is the published revenue/sales average.
  Revenue is not an extra signal once lagged price and sales are included.
* PJM zonal fields — screening layer only. Not inputs to this EIA model.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from infralens.evaluation.baseline import (
    NoAnalogError,
    availability_adjusted_seasonal_naive,
    available_rows,
    target_period_for_origin,
)

NUMERIC_FEATURES: tuple[str, ...] = (
    "price_latest",
    "price_same_month",
    "price_yoy_change",
    "price_trail12_mean",
    "sales_latest",
    "sales_yoy_change",
)
CATEGORICAL_FEATURES: tuple[str, ...] = ("state_id", "target_calendar_month")
MODEL_FEATURES: tuple[str, ...] = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TRAIL_MONTHS: int = 12


class FeatureGapError(ValueError):
    """Required lagged history is missing at the origin.

    Callers must skip the case. Do not impute the gap from a later month
    or from a neighboring state.
    """


@dataclass(frozen=True)
class OriginFeatures:
    """Feature vector and the observation months that produced it."""

    forecast_origin: pd.Timestamp
    state_id: str
    target_period: str
    target_calendar_month: str
    price_latest: float
    price_same_month: float
    price_yoy_change: float
    price_trail12_mean: float
    sales_latest: float
    sales_yoy_change: float
    latest_period: str
    latest_assumed_available_at: pd.Timestamp
    same_month_period: str
    same_month_assumed_available_at: pd.Timestamp
    yoy_period: str
    yoy_assumed_available_at: pd.Timestamp
    trail_periods: tuple[str, ...]
    trail_assumed_available_at: tuple[pd.Timestamp, ...]

    def source_periods(self) -> tuple[str, ...]:
        """Observation months that entered this vector, in stable order."""
        periods = [
            self.latest_period,
            self.same_month_period,
            self.yoy_period,
            *self.trail_periods,
        ]
        return tuple(dict.fromkeys(periods))

    def source_availability(self) -> tuple[pd.Timestamp, ...]:
        stamps = [
            self.latest_assumed_available_at,
            self.same_month_assumed_available_at,
            self.yoy_assumed_available_at,
            *self.trail_assumed_available_at,
        ]
        return tuple(stamps)


def shift_period(period: str, months: int) -> str:
    """Return the YYYY-MM period ``months`` away from ``period``."""
    start = pd.Timestamp(year=int(period[:4]), month=int(period[5:7]), day=1)
    shifted = start + pd.DateOffset(months=months)
    return f"{shifted.year:04d}-{shifted.month:02d}"


def trailing_periods(end_period: str, n_months: int = TRAIL_MONTHS) -> tuple[str, ...]:
    """Consecutive calendar months ending at ``end_period``, oldest first."""
    if n_months < 1:
        raise ValueError("n_months must be positive.")
    return tuple(shift_period(end_period, -offset) for offset in range(n_months - 1, -1, -1))


def _as_origin(forecast_origin: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(forecast_origin)


def _require_available(stamp: pd.Timestamp, origin: pd.Timestamp, period: str) -> None:
    if pd.Timestamp(stamp) > origin:
        raise FeatureGapError(
            f"Period {period} is not available at {origin.date()} "
            f"(assumed_available_at={pd.Timestamp(stamp).date()})."
        )


def build_origin_features(
    frame: pd.DataFrame,
    *,
    forecast_origin: pd.Timestamp,
    state_id: str,
) -> OriginFeatures:
    """Build one state's feature vector using only rows available at the origin.

    Missing months raise ``FeatureGapError``. This function does not fill
    gaps from later periods, from the target month, or with a sample mean.
    """
    origin = _as_origin(forecast_origin)
    state = state_id.upper()
    target_period = target_period_for_origin(origin)
    usable = available_rows(frame, origin)
    usable = usable.loc[usable["state_id"].astype(str).str.upper() == state].copy()
    if usable.empty:
        raise FeatureGapError(f"No EIA rows available for {state} at {origin.date()}.")
    if usable["period"].duplicated().any():
        raise FeatureGapError(f"Duplicate periods for {state} at {origin.date()}.")
    if (usable["assumed_available_at"] > origin).any():
        raise FeatureGapError("Leakage: available set contains a row after the origin.")

    indexed = usable.set_index("period", drop=False)
    latest_period = str(usable["period"].max())
    latest = _required_observation(
        indexed,
        latest_period,
        origin=origin,
        fields=("price_cents_per_kwh", "sales_million_kwh"),
    )
    yoy_period = shift_period(latest_period, -12)
    yoy = _required_observation(
        indexed,
        yoy_period,
        origin=origin,
        fields=("price_cents_per_kwh", "sales_million_kwh"),
    )
    trail = trailing_periods(latest_period, TRAIL_MONTHS)
    trail_rows = [
        _required_observation(
            indexed,
            period,
            origin=origin,
            fields=("price_cents_per_kwh",),
        )
        for period in trail
    ]
    try:
        analog = availability_adjusted_seasonal_naive(
            frame,
            forecast_origin=origin,
            state_id=state,
        )
    except NoAnalogError as exc:
        raise FeatureGapError(str(exc)) from exc

    same_month_period = str(analog["source_period"])
    same_month_available = pd.Timestamp(analog["source_assumed_available_at"])
    _require_available(same_month_available, origin, same_month_period)
    if same_month_period == target_period or same_month_period >= target_period:
        raise FeatureGapError("Seasonal analog is not strictly before the target month.")

    observed = (latest_period, yoy_period, same_month_period, *trail)
    if any(period >= target_period for period in observed):
        raise FeatureGapError("A feature period is not strictly before the target month.")

    features = OriginFeatures(
        forecast_origin=origin.normalize(),
        state_id=state,
        target_period=target_period,
        target_calendar_month=target_period[5:7],
        price_latest=float(latest["price_cents_per_kwh"]),
        price_same_month=float(analog["prediction_cents_per_kwh"]),
        price_yoy_change=float(latest["price_cents_per_kwh"] - yoy["price_cents_per_kwh"]),
        price_trail12_mean=float(
            sum(float(row["price_cents_per_kwh"]) for row in trail_rows) / len(trail_rows)
        ),
        sales_latest=float(latest["sales_million_kwh"]),
        sales_yoy_change=float(latest["sales_million_kwh"] - yoy["sales_million_kwh"]),
        latest_period=latest_period,
        latest_assumed_available_at=pd.Timestamp(latest["assumed_available_at"]),
        same_month_period=same_month_period,
        same_month_assumed_available_at=same_month_available,
        yoy_period=yoy_period,
        yoy_assumed_available_at=pd.Timestamp(yoy["assumed_available_at"]),
        trail_periods=trail,
        trail_assumed_available_at=tuple(
            pd.Timestamp(row["assumed_available_at"]) for row in trail_rows
        ),
    )
    if any(stamp > origin for stamp in features.source_availability()):
        raise FeatureGapError("Leakage: a feature source is available after the origin.")
    return features


def _required_observation(
    indexed: pd.DataFrame,
    period: str,
    *,
    origin: pd.Timestamp,
    fields: tuple[str, ...],
) -> pd.Series:
    """Return one available month, or raise if it is absent or null.

    Absence is a gap. The caller must not substitute a later period.
    """
    if period not in indexed.index:
        raise FeatureGapError(f"Missing history at period {period}.")
    row = indexed.loc[period]
    if isinstance(row, pd.DataFrame):
        raise FeatureGapError(f"Duplicate period {period}.")
    _require_available(pd.Timestamp(row["assumed_available_at"]), origin, period)
    for field in fields:
        if pd.isna(row[field]):
            raise FeatureGapError(f"Missing {field} at period {period}.")
    return row

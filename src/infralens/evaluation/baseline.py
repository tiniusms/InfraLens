"""Availability-adjusted seasonal-naive baseline (no ML)."""

from __future__ import annotations

import pandas as pd

from infralens.data.availability import add_assumed_available_at


class BaselineError(ValueError):
    """Raised when a leak-free seasonal-naive prediction cannot be formed."""


def target_period_for_origin(forecast_origin: pd.Timestamp) -> str:
    """Calendar month 12 months after the origin's calendar month (YYYY-MM)."""
    origin = pd.Timestamp(forecast_origin)
    origin_month = pd.Timestamp(year=origin.year, month=origin.month, day=1)
    target = origin_month + pd.DateOffset(months=12)
    return f"{target.year:04d}-{target.month:02d}"


def _with_availability(frame: pd.DataFrame) -> pd.DataFrame:
    if "assumed_available_at" in frame.columns:
        out = frame.copy()
        out["assumed_available_at"] = pd.to_datetime(out["assumed_available_at"])
        return out
    return add_assumed_available_at(frame)


def available_rows(frame: pd.DataFrame, forecast_origin: pd.Timestamp) -> pd.DataFrame:
    """Rows with ``assumed_available_at <= forecast_origin``."""
    origin = pd.Timestamp(forecast_origin)
    work = _with_availability(frame)
    selected = work.loc[work["assumed_available_at"] <= origin].copy()
    if (selected["assumed_available_at"] > origin).any():
        raise BaselineError("Leakage: selected rows after forecast origin.")
    return selected


def availability_adjusted_seasonal_naive(
    frame: pd.DataFrame,
    *,
    forecast_origin: pd.Timestamp,
    state_id: str,
) -> dict[str, object]:
    """Predict the 12-month-ahead price using the latest available same calendar month.

    Never uses a row with ``assumed_available_at > forecast_origin``.
    """
    origin = pd.Timestamp(forecast_origin)
    target_period = target_period_for_origin(origin)
    target_month = int(target_period.split("-")[1])
    usable = available_rows(frame, origin)
    usable = usable.loc[usable["state_id"].astype(str).str.upper() == state_id.upper()]
    usable = usable.loc[usable["period"].str[5:7].astype(int) == target_month]
    usable = usable.loc[usable["period"] != target_period]
    usable = usable.dropna(subset=["price_cents_per_kwh"])
    if usable.empty:
        raise BaselineError(
            f"No available same-month analog for {state_id} at {origin.date()} "
            f"(target {target_period})."
        )
    chosen = usable.sort_values("period").iloc[-1]
    if pd.Timestamp(chosen["assumed_available_at"]) > origin:
        raise BaselineError("Leakage: chosen analog is not yet available.")
    return {
        "forecast_origin": origin.normalize(),
        "state_id": state_id.upper(),
        "target_period": target_period,
        "source_period": str(chosen["period"]),
        "prediction_cents_per_kwh": float(chosen["price_cents_per_kwh"]),
        "source_assumed_available_at": pd.Timestamp(chosen["assumed_available_at"]),
    }

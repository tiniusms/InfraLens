"""Expanding-origin, publication-lag-constrained current-vintage backtest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from infralens.data import USER_FACING_STATES, repository_root
from infralens.data.availability import add_assumed_available_at
from infralens.evaluation.baseline import (
    BaselineError,
    NoAnalogError,
    availability_adjusted_seasonal_naive,
    target_period_for_origin,
)

# Last 12 observed target months reserved until model selection (EVALUATION.md).
HOLDOUT_TARGET_START = "2025-07"


@dataclass(frozen=True)
class BacktestResult:
    predictions: pd.DataFrame
    mae_overall: float
    mae_by_state: dict[str, float]
    n_forecasts: int
    n_attempted: int
    n_skipped_no_analog: int
    n_skipped_missing_actual: int
    window: str


def month_end_origins(start: str, end: str) -> list[pd.Timestamp]:
    """Inclusive month-end forecast origins from YYYY-MM through YYYY-MM."""
    start_ts = pd.Timestamp(f"{start}-01") + pd.offsets.MonthEnd(0)
    end_ts = pd.Timestamp(f"{end}-01") + pd.offsets.MonthEnd(0)
    return list(pd.date_range(start=start_ts, end=end_ts, freq="ME"))


def load_price_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    if "assumed_available_at" not in frame.columns:
        frame = add_assumed_available_at(frame)
    else:
        frame = frame.copy()
        frame["assumed_available_at"] = pd.to_datetime(frame["assumed_available_at"])
    return frame


def latest_eia_parquet(project_root: Path | None = None) -> Path:
    root = project_root or repository_root()
    matches = sorted((root / "data" / "interim").glob("eia_retail_sales_monthly_com_*.parquet"))
    if not matches:
        raise FileNotFoundError("No timestamped EIA interim Parquet found under data/interim/.")
    return matches[-1]


def run_expanding_backtest(
    frame: pd.DataFrame,
    *,
    origin_start: str = "2002-01",
    origin_end: str = "2024-06",
    states: tuple[str, ...] = USER_FACING_STATES,
    window: str = "development",
) -> BacktestResult:
    """Score availability-adjusted seasonal-naive forecasts; skip the reserved holdout."""
    work = frame.copy()
    if "assumed_available_at" not in work.columns:
        work = add_assumed_available_at(work)
    work["assumed_available_at"] = pd.to_datetime(work["assumed_available_at"])
    actuals = {
        (str(row.state_id).upper(), str(row.period)): row.price_cents_per_kwh
        for row in work.itertuples(index=False)
    }
    records: list[dict[str, object]] = []
    n_attempted = 0
    n_skipped_no_analog = 0
    n_skipped_missing_actual = 0
    for origin in month_end_origins(origin_start, origin_end):
        target_period = target_period_for_origin(origin)
        if target_period >= HOLDOUT_TARGET_START:
            continue
        for state in states:
            n_attempted += 1
            try:
                pred = availability_adjusted_seasonal_naive(
                    work,
                    forecast_origin=origin,
                    state_id=state,
                )
            except NoAnalogError:
                n_skipped_no_analog += 1
                continue
            actual = actuals.get((state.upper(), target_period))
            if actual is None or pd.isna(actual):
                n_skipped_missing_actual += 1
                continue
            if pd.Timestamp(pred["source_assumed_available_at"]) > origin:
                raise BaselineError("Leakage in backtest output.")
            records.append(
                {
                    **pred,
                    "actual_cents_per_kwh": float(actual),
                    "absolute_error": abs(float(pred["prediction_cents_per_kwh"]) - float(actual)),
                }
            )
    n_scored = len(records)
    if n_attempted != n_scored + n_skipped_no_analog + n_skipped_missing_actual:
        raise BaselineError(
            "Skip accounting invariant failed: attempted != scored + skipped."
        )
    if n_attempted == 0:
        raise BaselineError("Backtest produced no development forecast cells.")
    if not records:
        raise BaselineError("Backtest produced no scored forecasts.")
    predictions = pd.DataFrame.from_records(records)
    leaked = predictions["source_assumed_available_at"] > predictions["forecast_origin"]
    if leaked.any():
        raise BaselineError("Leakage: analog assumed_available_at after forecast_origin.")
    mae_overall = float(predictions["absolute_error"].mean())
    mae_by_state = {
        state: float(group["absolute_error"].mean())
        for state, group in predictions.groupby("state_id")
    }
    return BacktestResult(
        predictions=predictions,
        mae_overall=mae_overall,
        mae_by_state=mae_by_state,
        n_forecasts=n_scored,
        n_attempted=n_attempted,
        n_skipped_no_analog=n_skipped_no_analog,
        n_skipped_missing_actual=n_skipped_missing_actual,
        window=window,
    )


def _print_result(result: BacktestResult, parquet_path: Path) -> None:
    print(f"window: {result.window}")
    print(f"parquet: {parquet_path}")
    print(f"n_attempted: {result.n_attempted}")
    print(f"n_scored: {result.n_forecasts}")
    print(f"n_skipped_no_analog: {result.n_skipped_no_analog}")
    print(f"n_skipped_missing_actual: {result.n_skipped_missing_actual}")
    print(f"n_forecasts: {result.n_forecasts}")
    print(f"mae_overall_cents_per_kwh: {result.mae_overall:.4f}")
    print("mae_by_state_cents_per_kwh:")
    for state, mae in sorted(result.mae_by_state.items()):
        print(f"  {state}: {mae:.4f}")
    print(f"run_at: {datetime.now().isoformat(timespec='seconds')}")


def main() -> int:
    parquet_path = latest_eia_parquet()
    frame = load_price_panel(parquet_path)
    result = run_expanding_backtest(frame)
    _print_result(result, parquet_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

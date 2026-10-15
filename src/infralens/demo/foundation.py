"""Testable inputs for the Streamlit foundation page.

The page is a historical evaluation prototype. A Ridge value taken from the
frozen holdout case file is a closed prediction with an actual, not a
forward forecast. Typed prices stay hypothetical. This module does not
import the evaluation package and does not score the holdout.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pandas as pd

from infralens.data import repository_root
from infralens.finance.annual_cost import (
    AnnualElectricityCost,
    PriceScenario,
    compare_price_scenarios,
)

PROTOTYPE_CAPTION = (
    "Historical evaluation and infrastructure-screening prototype. "
    "Not a live production forecasting system."
)
HOLDOUT_PRICE_LABEL = (
    "Closed holdout Ridge prediction. Not a forward-looking forecast."
)
TYPED_PRICE_LABEL = "Typed hypothetical energy price. Not a model forecast."
PORTABLE_MODE = "portable_summary"
LOCAL_FULL_DATA_MODE = "local_full_data"

_FROZEN_EXTRACT_ID = "eia_retail_sales_monthly_com_20260911T190524Z.parquet"
_OBTAIN_SOURCES = (
    "Full local mode expects files that are not in git. "
    f"Price history: data/interim/{_FROZEN_EXTRACT_ID}. "
    "Holdout cases: data/processed/final_holdout/final_holdout_cases.parquet. "
    "PJM tables: data/raw/pjm/2025-load-report-tables.xlsx and "
    "2026-load-report-tables.xlsx from the public PJM load-forecast pages. "
    "Do not rerun the final EIA holdout to create them. "
    "This page still runs the cost calculator and the committed evaluation summary."
)


class DemoDataError(ValueError):
    """A demonstration file is missing or is not the frozen artifact."""


class PriceSource:
    """Where a scenario price came from. Only the holdout source is model-derived."""

    TYPED_HYPOTHETICAL = "typed_hypothetical"
    HOLDOUT_RIDGE = "holdout_ridge"


@dataclass(frozen=True)
class LocalArtifactPaths:
    """Files the later demo tabs will read. Presence is not a license to score."""

    price_history: Path
    holdout_cases: Path
    pjm_2025_tables: Path
    pjm_2026_tables: Path
    committed_summary: Path


@dataclass(frozen=True)
class ArtifactAssessment:
    """Which cached files exist, and which demonstration mode that allows."""

    price_history_present: bool
    holdout_cases_present: bool
    pjm_2025_present: bool
    pjm_2026_present: bool
    committed_summary_present: bool
    mode: str
    obtain_sources: str


@dataclass(frozen=True)
class HoldoutBanner:
    """Committed one-shot summary. This is an evaluation result, not a forecast."""

    primary_criterion: str
    ridge_mae_cents_per_kwh: Decimal
    paired_baseline_mae_cents_per_kwh: Decimal
    interval_coverage: Decimal
    feature_set_id: str
    extract_id: str
    runner_commit: str
    evaluation_stage: str


@dataclass(frozen=True)
class HoldoutRidgeQuote:
    """One frozen holdout case used only as a labeled historical price."""

    state_id: str
    forecast_origin: str
    target_month: str
    ridge_prediction_cents_per_kwh: Decimal
    actual_cents_per_kwh: Decimal
    seasonal_naive_prediction_cents_per_kwh: Decimal

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.state_id, self.forecast_origin, self.target_month)

    @property
    def choice_label(self) -> str:
        return (
            f"{self.state_id} origin {self.forecast_origin} "
            f"target {self.target_month} | Ridge {self.ridge_prediction_cents_per_kwh} cents/kWh"
        )


def default_artifact_paths(root: Path | None = None) -> LocalArtifactPaths:
    """Return the local cache paths. Missing files stay missing."""
    base = root or repository_root()
    return LocalArtifactPaths(
        price_history=base / "data" / "interim" / _FROZEN_EXTRACT_ID,
        holdout_cases=base / "data" / "processed" / "final_holdout" / "final_holdout_cases.parquet",
        pjm_2025_tables=base / "data" / "raw" / "pjm" / "2025-load-report-tables.xlsx",
        pjm_2026_tables=base / "data" / "raw" / "pjm" / "2026-load-report-tables.xlsx",
        committed_summary=base / "docs" / "final_eia_holdout_oneshot.json",
    )


def assess_artifacts(paths: LocalArtifactPaths) -> ArtifactAssessment:
    """Choose portable or local-full mode from file presence alone."""
    price = paths.price_history.is_file()
    cases = paths.holdout_cases.is_file()
    pjm_2025 = paths.pjm_2025_tables.is_file()
    pjm_2026 = paths.pjm_2026_tables.is_file()
    summary = paths.committed_summary.is_file()
    full = price and cases and pjm_2025 and pjm_2026
    return ArtifactAssessment(
        price_history_present=price,
        holdout_cases_present=cases,
        pjm_2025_present=pjm_2025,
        pjm_2026_present=pjm_2026,
        committed_summary_present=summary,
        mode=LOCAL_FULL_DATA_MODE if full else PORTABLE_MODE,
        obtain_sources=_OBTAIN_SOURCES,
    )


def load_holdout_banner(path: Path) -> HoldoutBanner:
    """Read the committed summary. This does not open the case table or refit Ridge."""
    if not path.is_file():
        raise DemoDataError(f"Committed holdout summary is missing: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    summary = document.get("summary")
    if not isinstance(summary, dict):
        raise DemoDataError("Committed holdout summary has no summary object.")
    try:
        return HoldoutBanner(
            primary_criterion=str(summary["primary_criterion"]),
            ridge_mae_cents_per_kwh=Decimal(str(summary["ridge_mae"])),
            paired_baseline_mae_cents_per_kwh=Decimal(str(summary["paired_baseline_mae"])),
            interval_coverage=Decimal(str(summary["interval_coverage"])),
            feature_set_id=str(summary["feature_set_id"]),
            extract_id=str(summary["extract_id"]),
            runner_commit=str(document["runner_commit"]),
            evaluation_stage=str(summary["evaluation_stage"]),
        )
    except (KeyError, TypeError, ArithmeticError) as exc:
        raise DemoDataError("Committed holdout summary is incomplete.") from exc


def load_holdout_quotes(path: Path) -> tuple[HoldoutRidgeQuote, ...]:
    """Read frozen holdout cases. Missing or duplicate keys fail closed."""
    if not path.is_file():
        raise DemoDataError(
            "Frozen holdout cases are not on this machine. "
            "A Ridge price cannot be typed in as a substitute."
        )
    frame = pd.read_parquet(path)
    required = {
        "evaluation_stage",
        "state_id",
        "forecast_origin",
        "target_month",
        "actual",
        "ridge_prediction",
        "seasonal_naive_prediction",
        "skip_reason",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise DemoDataError(
            "Holdout case file is missing columns: " + ", ".join(sorted(missing))
        )
    if not frame["evaluation_stage"].eq("final_holdout").all():
        raise DemoDataError("Holdout case file is not the final_holdout stage.")
    scored = frame.loc[frame["skip_reason"].isna()]
    quotes: list[HoldoutRidgeQuote] = []
    seen: set[tuple[str, str, str]] = set()
    for row in scored.itertuples(index=False):
        quote = HoldoutRidgeQuote(
            state_id=str(row.state_id),
            forecast_origin=_origin_text(row.forecast_origin),
            target_month=_month_text(row.target_month),
            ridge_prediction_cents_per_kwh=Decimal(str(row.ridge_prediction)),
            actual_cents_per_kwh=Decimal(str(row.actual)),
            seasonal_naive_prediction_cents_per_kwh=Decimal(str(row.seasonal_naive_prediction)),
        )
        if quote.key in seen:
            raise DemoDataError(f"Duplicate holdout case {quote.key}.")
        seen.add(quote.key)
        quotes.append(quote)
    if not quotes:
        raise DemoDataError("Holdout case file has no scored rows.")
    return tuple(quotes)


def is_model_derived_price(source: str) -> bool:
    """True only when the price is a frozen holdout Ridge prediction."""
    if source == PriceSource.HOLDOUT_RIDGE:
        return True
    if source == PriceSource.TYPED_HYPOTHETICAL:
        return False
    raise DemoDataError(f"Unknown price source {source!r}.")


def cost_scenarios(
    *,
    it_capacity_mw: object,
    pue: object,
    utilization: object,
    operating_hours_per_year: object,
    scenarios: tuple[tuple[str, str, object], ...],
    baseline_name: str,
    holdout_quotes: tuple[HoldoutRidgeQuote, ...] = (),
) -> tuple[AnnualElectricityCost, ...]:
    """Price one load. A holdout source must match a frozen case exactly.

    ``scenarios`` entries are ``(name, price_source, typed_or_quote_key)``.
    For a typed source the third item is the cents/kWh value. For a holdout
    source it is ``(state_id, forecast_origin, target_month)``.
    """
    priced: list[PriceScenario] = []
    for name, source, payload in scenarios:
        if not is_model_derived_price(source):
            priced.append(
                PriceScenario(
                    name=str(name),
                    price_cents_per_kwh=payload,  # type: ignore[arg-type]
                    model_derived_eia_price=False,
                )
            )
            continue
        if not isinstance(payload, tuple) or len(payload) != 3:
            raise DemoDataError("A holdout Ridge scenario needs a frozen case key.")
        quote = _quote_for_key(holdout_quotes, payload)
        priced.append(
            PriceScenario(
                name=str(name),
                price_cents_per_kwh=quote.ridge_prediction_cents_per_kwh,
                model_derived_eia_price=True,
            )
        )
    return compare_price_scenarios(
        it_capacity_mw=it_capacity_mw,  # type: ignore[arg-type]
        pue=pue,  # type: ignore[arg-type]
        utilization=utilization,  # type: ignore[arg-type]
        operating_hours_per_year=operating_hours_per_year,  # type: ignore[arg-type]
        scenarios=tuple(priced),
        baseline_name=baseline_name,
    )


def _quote_for_key(
    quotes: tuple[HoldoutRidgeQuote, ...],
    key: tuple[object, object, object],
) -> HoldoutRidgeQuote:
    wanted = (str(key[0]), str(key[1]), str(key[2]))
    matches = [quote for quote in quotes if quote.key == wanted]
    if len(matches) != 1:
        raise DemoDataError(
            "That holdout case is not in the frozen file. "
            "The page will not invent a Ridge price."
        )
    return matches[0]


def _origin_text(value: object) -> str:
    try:
        return pd.Timestamp(value).date().isoformat()
    except (TypeError, ValueError) as exc:
        raise DemoDataError(f"Holdout origin is not a date: {value!r}.") from exc


def _month_text(value: object) -> str:
    text = str(value)
    if len(text) >= 7 and text[4] == "-" and text[5:7].isdigit():
        return text[:7]
    raise DemoDataError(f"Holdout target month is not a month: {value!r}.")

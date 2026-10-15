"""Streamlit demo: closed EIA charts and the electricity-cost form.

Run from the repository root:

    streamlit run src/infralens/demo/app.py

The FAIL banner stays above the tabs. PJM screening is not on this page.
"""

from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from infralens.demo.eia_views import (
    ACTUAL_SERIES_LABEL,
    HOLDOUT_SECTION_LABEL,
    MISSING_HOLDOUT_CHART,
    MISSING_PRICE_HISTORY,
    NAIVE_SERIES_LABEL,
    OBSERVED_PRICE_LABEL,
    RIDGE_SERIES_LABEL,
    HoldoutComparison,
    PriceHistory,
    holdout_line_frame,
    holdout_plot_frame,
    holdout_provenance,
    load_holdout_comparison,
    load_price_history,
    price_plot_frame,
)
from infralens.demo.foundation import (
    FROZEN_EXTRACT_ID,
    HOLDOUT_PRICE_LABEL,
    LOCAL_FULL_DATA_MODE,
    PROTOTYPE_CAPTION,
    TYPED_PRICE_LABEL,
    DemoDataError,
    PriceSource,
    assess_artifacts,
    cost_scenarios,
    default_artifact_paths,
    load_holdout_banner,
    load_holdout_quotes,
)
from infralens.finance.annual_cost import EIA_MODEL_PRICE_WARNING, FinanceInputError

_ACTUAL_COLOR = "#1f4e79"
_RIDGE_COLOR = "#b85c38"
_NAIVE_COLOR = "#2f6f4e"
_BAND_COLOR = "#f0c9b0"


def main() -> None:
    st.set_page_config(page_title="InfraLens", layout="wide")
    st.title("InfraLens")
    st.caption(PROTOTYPE_CAPTION)
    paths = default_artifact_paths()
    try:
        banner = load_holdout_banner(paths.committed_summary)
    except DemoDataError as exc:
        st.error(str(exc))
        st.stop()
    _render_banner(banner)
    assessment = assess_artifacts(paths)
    _render_mode(assessment)
    history_tab, finance_tab = st.tabs(
        ["EIA history and closed holdout", "Financial scenarios"]
    )
    with history_tab:
        _render_history(paths.price_history)
        _render_holdout_chart(paths.holdout_cases, banner)
    with finance_tab:
        quotes: tuple = ()
        if assessment.holdout_cases_present:
            try:
                quotes = load_holdout_quotes(paths.holdout_cases)
            except DemoDataError as exc:
                st.error(str(exc))
                quotes = ()
        _render_cost_form(quotes)


def _render_banner(banner) -> None:
    st.subheader("Closed EIA holdout")
    st.error(
        f"Preregistered primary criterion: {banner.primary_criterion}. "
        "Ridge did not beat the seasonal-naive baseline by 10%. "
        "These rows are historical evaluation results, not a forward forecast."
    )
    left, middle, right = st.columns(3)
    left.metric("Ridge MAE", f"{banner.ridge_mae_cents_per_kwh} ¢/kWh")
    middle.metric("Seasonal-naive MAE", f"{banner.paired_baseline_mae_cents_per_kwh} ¢/kWh")
    right.metric("Interval coverage", f"{banner.interval_coverage}")
    st.caption(
        f"Feature set {banner.feature_set_id}. Extract {banner.extract_id}. "
        f"Stage {banner.evaluation_stage}. Runner {banner.runner_commit}."
    )


def _render_mode(assessment) -> None:
    if assessment.mode == LOCAL_FULL_DATA_MODE:
        st.info(
            "Local full-data files are on this machine. "
            "The history and closed-holdout charts read those files. "
            "PJM screening is not on this page."
        )
        return
    st.warning("Portable demonstration mode. " + assessment.obtain_sources)


def _render_history(path: Path) -> None:
    st.subheader(OBSERVED_PRICE_LABEL)
    if not path.is_file():
        st.warning(MISSING_PRICE_HISTORY)
        return
    try:
        stat = path.stat()
        history = _cached_price_history(str(path), stat.st_size, stat.st_mtime_ns)
    except DemoDataError as exc:
        st.error(str(exc))
        return
    state = st.selectbox("History state", history.states, key="history-state")
    frame = price_plot_frame(history, state)
    st.altair_chart(_history_chart(frame), use_container_width=True)
    retrieved = history.retrieved_at or "not recorded on the file"
    source = history.source_name or "EIA"
    units = history.price_units or "cents/kWh"
    st.caption(
        f"Observed months {history.earliest_period} through {history.latest_period} "
        f"({history.row_count} state-months). Extract {history.extract_id}. "
        f"Retrieved {retrieved}. Source {source}. Units {units}."
    )
    st.caption(history.limitations)
    st.caption("Role: observed. This line is not a model prediction and not a hypothetical price.")


def _render_holdout_chart(path: Path, banner) -> None:
    st.subheader(HOLDOUT_SECTION_LABEL)
    st.caption(
        "Actual, Ridge, and seasonal naive are plotted by target month, July 2025 through June 2026. "
        "Forecast origins stay in the provenance line and are not the chart axis."
    )
    if not path.is_file():
        st.warning(MISSING_HOLDOUT_CHART)
        return
    try:
        stat = path.stat()
        comparison = _cached_holdout_comparison(str(path), stat.st_size, stat.st_mtime_ns)
    except DemoDataError as exc:
        st.error(str(exc))
        return
    state = st.selectbox("Holdout state", _states(comparison), key="holdout-state")
    plot = holdout_plot_frame(comparison, state)
    lines = holdout_line_frame(plot)
    st.altair_chart(_holdout_chart(plot, lines, comparison), use_container_width=True)
    if comparison.interval_warning:
        st.warning(comparison.interval_warning)
    provenance = holdout_provenance(comparison, banner)
    st.caption(
        f"Forecast origins {provenance.origin_start} through {provenance.origin_end}. "
        f"Target months {provenance.target_start} through {provenance.target_end}. "
        f"Chart axis: {provenance.axis}. Extract {provenance.extract_id}. "
        f"Frozen summary {provenance.summary_source}. "
        f"Feature set {provenance.feature_set_id}. Stage {provenance.evaluation_stage}."
    )
    st.caption(
        "Actual is observed. Ridge and seasonal naive are closed predictions from the frozen evaluation. "
        "They are not a forward forecast and not a hypothetical typed price."
    )


def _states(comparison: HoldoutComparison) -> tuple[str, ...]:
    return tuple(dict.fromkeys(point.state_id for point in comparison.points))


def _history_chart(frame: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(frame)
        .mark_line()
        .encode(
            x=alt.X("period:N", sort=list(frame["period"]), title="Observation month"),
            y=alt.Y(
                "observed_commercial_average_price_cents_per_kwh:Q",
                title="cents/kWh",
            ),
            color=alt.Color(
                "series:N",
                scale=alt.Scale(domain=[OBSERVED_PRICE_LABEL], range=[_ACTUAL_COLOR]),
                title="Series",
            ),
            tooltip=[
                "period",
                alt.Tooltip(
                    "observed_commercial_average_price_cents_per_kwh:Q",
                    title=OBSERVED_PRICE_LABEL,
                    format=".2f",
                ),
            ],
        )
    )


def _holdout_chart(
    plot: pd.DataFrame,
    lines: pd.DataFrame,
    comparison: HoldoutComparison,
) -> alt.Chart:
    order = list(plot["target_month"])
    colors = alt.Scale(
        domain=[ACTUAL_SERIES_LABEL, RIDGE_SERIES_LABEL, NAIVE_SERIES_LABEL],
        range=[_ACTUAL_COLOR, _RIDGE_COLOR, _NAIVE_COLOR],
    )
    drawn = (
        alt.Chart(lines)
        .mark_line(point=True)
        .encode(
            x=alt.X("target_month:N", sort=order, title="Target month"),
            y=alt.Y("cents_per_kwh:Q", title="cents/kWh"),
            color=alt.Color("series:N", scale=colors, title="Series"),
            tooltip=["target_month", "series", alt.Tooltip("cents_per_kwh:Q", format=".3f")],
        )
    )
    if not comparison.has_intervals:
        return drawn
    band = (
        alt.Chart(plot)
        .mark_area(opacity=0.35, color=_BAND_COLOR)
        .encode(
            x=alt.X("target_month:N", sort=order, title="Target month"),
            y=alt.Y("interval_lower_cents_per_kwh:Q", title="cents/kWh"),
            y2="interval_upper_cents_per_kwh:Q",
        )
    )
    return band + drawn


@st.cache_data(show_spinner=False)
def _cached_price_history(path_text: str, size_bytes: int, mtime_ns: int) -> PriceHistory:
    """Cache one immutable extract. The size and mtime are part of the key."""

    path = Path(path_text)
    stat = path.stat()
    if stat.st_size != size_bytes or stat.st_mtime_ns != mtime_ns:
        raise DemoDataError("Cached price history no longer matches the file on disk.")
    return load_price_history(path, extract_id=FROZEN_EXTRACT_ID)


@st.cache_data(show_spinner=False)
def _cached_holdout_comparison(path_text: str, size_bytes: int, mtime_ns: int) -> HoldoutComparison:
    """Cache the frozen case table. The size and mtime are part of the key."""

    path = Path(path_text)
    stat = path.stat()
    if stat.st_size != size_bytes or stat.st_mtime_ns != mtime_ns:
        raise DemoDataError("Cached holdout cases no longer match the file on disk.")
    return load_holdout_comparison(path)


def _render_cost_form(quotes) -> None:
    st.subheader("Annual electricity cost")
    st.caption(
        "Defaults are the checked 50 MW example. "
        "A selected holdout Ridge price is filled from the frozen case file and "
        "carries the model warning automatically."
    )
    capacity = st.number_input("IT capacity (MW)", value=50.0, step=1.0)
    pue = st.number_input("PUE", value=1.30, step=0.01, format="%.2f")
    utilization = st.number_input("Average IT utilization (0–1)", value=0.80, step=0.01, format="%.2f")
    hours = st.number_input("Operating hours per year", value=8760.0, step=1.0)
    baseline = _scenario_inputs("Baseline", "baseline", 12.0, quotes)
    comparison = _scenario_inputs("Comparison", "comparison", 10.0, quotes)
    if not st.button("Calculate annual cost"):
        return
    try:
        rows = cost_scenarios(
            it_capacity_mw=capacity,
            pue=pue,
            utilization=utilization,
            operating_hours_per_year=hours,
            baseline_name=baseline[0],
            scenarios=(baseline, comparison),
            holdout_quotes=quotes,
        )
    except (FinanceInputError, DemoDataError) as exc:
        st.error(str(exc))
        return
    for row in rows:
        label = HOLDOUT_PRICE_LABEL if row.model_derived_eia_price else TYPED_PRICE_LABEL
        st.markdown(f"**{row.scenario_name}** — {label}")
        st.write(
            f"Demand {row.facility_average_demand_mw} {row.facility_average_demand_unit}; "
            f"consumption {row.annual_consumption_kwh} {row.annual_consumption_unit}; "
            f"price {row.price_cents_per_kwh} {row.price_unit}; "
            f"annual cost {row.annual_electricity_cost_usd} {row.annual_electricity_cost_unit}; "
            f"difference vs {row.baseline_scenario_name} "
            f"{row.cost_difference_vs_baseline_usd} {row.cost_difference_unit}."
        )
        if row.model_price_warning:
            st.warning(row.model_price_warning)
    if EIA_MODEL_PRICE_WARNING and any(row.model_derived_eia_price for row in rows):
        st.caption("The warning is attached by the finance module because the price source is the frozen holdout.")


def _scenario_inputs(title: str, key: str, default_price: float, quotes):
    st.markdown(f"**{title}**")
    name = st.text_input(f"{title} name", value=title.lower(), key=f"{key}-name")
    sources = [PriceSource.TYPED_HYPOTHETICAL]
    labels = {PriceSource.TYPED_HYPOTHETICAL: "Typed hypothetical cents/kWh"}
    if quotes:
        sources.append(PriceSource.HOLDOUT_RIDGE)
        labels[PriceSource.HOLDOUT_RIDGE] = HOLDOUT_PRICE_LABEL
    source = st.radio(
        f"{title} price source",
        sources,
        format_func=labels.get,
        key=f"{key}-source",
    )
    if source == PriceSource.HOLDOUT_RIDGE:
        by_label = {quote.choice_label: quote for quote in quotes}
        choice = st.selectbox(
            f"{title} frozen holdout case",
            list(by_label),
            key=f"{key}-case",
        )
        quote = by_label[choice]
        st.caption(
            f"Actual {quote.actual_cents_per_kwh} cents/kWh. "
            f"Seasonal naive {quote.seasonal_naive_prediction_cents_per_kwh} cents/kWh. "
            "Shown so this Ridge value stays tied to a scored case."
        )
        return (name, source, quote.key)
    price = st.number_input(
        f"{title} price (cents/kWh)",
        value=default_price,
        step=0.1,
        key=f"{key}-price",
    )
    return (name, source, price)


if __name__ == "__main__":
    main()

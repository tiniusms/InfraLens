"""Streamlit foundation: evaluation banner and electricity-cost form.

Run from the repository root:

    streamlit run src/infralens/demo/app.py

Price charts and the PJM screening tab are not in this page.
"""

from __future__ import annotations

import streamlit as st

from infralens.demo.foundation import (
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
            "This foundation page does not chart prices or open the PJM screening view yet."
        )
        return
    st.warning("Portable demonstration mode. " + assessment.obtain_sources)


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

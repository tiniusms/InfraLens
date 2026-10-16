"""Deterministic tests for the annual electricity-cost calculator."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from infralens.finance.annual_cost import (
    EIA_MODEL_PRICE_WARNING,
    FinanceInputError,
    PriceScenario,
    annual_electricity_cost,
    compare_price_scenarios,
)


def test_documented_50_mw_example_is_exact() -> None:
    result = annual_electricity_cost(
        it_capacity_mw=50,
        pue=1.30,
        utilization=0.80,
        price_cents_per_kwh=12,
        operating_hours_per_year=8760,
    )
    assert result.facility_average_demand_mw == Decimal("52")
    assert result.facility_average_demand_unit == "MW"
    assert result.annual_consumption_kwh == Decimal("455520000")
    assert result.annual_consumption_unit == "kWh"
    assert result.price_cents_per_kwh == Decimal("12")
    assert result.price_unit == "cents/kWh"
    assert result.annual_electricity_cost_usd == Decimal("54662400")
    assert result.annual_electricity_cost_unit == "USD"
    assert result.operating_hours_per_year == Decimal("8760")
    assert result.model_price_warning is None
    assert result.cost_difference_vs_baseline_usd is None


def test_pue_must_be_at_least_one_while_zero_load_stays_valid() -> None:
    with pytest.raises(FinanceInputError, match="pue"):
        annual_electricity_cost(
            it_capacity_mw=50,
            pue=Decimal("0.99"),
            utilization=Decimal("0.80"),
            price_cents_per_kwh=12,
        )
    with pytest.raises(FinanceInputError, match="pue"):
        annual_electricity_cost(
            it_capacity_mw=50,
            pue=float("nan"),
            utilization=Decimal("1"),
            price_cents_per_kwh=12,
        )
    unity = annual_electricity_cost(
        it_capacity_mw=10,
        pue=1,
        utilization=1,
        price_cents_per_kwh=10,
    )
    assert unity.pue == Decimal("1")
    assert unity.facility_average_demand_mw == Decimal("10")
    assert unity.annual_consumption_kwh == Decimal("87600000")
    assert unity.annual_electricity_cost_usd == Decimal("8760000")


def test_zero_capacity_and_zero_utilization_are_zero_consumption() -> None:
    idle = annual_electricity_cost(
        it_capacity_mw=0,
        pue=Decimal("1.2"),
        utilization=Decimal("1"),
        price_cents_per_kwh=Decimal("15.5"),
    )
    unused = annual_electricity_cost(
        it_capacity_mw=Decimal("40"),
        pue=Decimal("1.2"),
        utilization=0,
        price_cents_per_kwh=Decimal("15.5"),
    )
    assert idle.facility_average_demand_mw == 0
    assert idle.annual_consumption_kwh == 0
    assert idle.annual_electricity_cost_usd == 0
    assert unused.annual_consumption_kwh == 0
    assert unused.annual_electricity_cost_usd == 0


def test_fractional_price_is_not_rounded() -> None:
    result = annual_electricity_cost(
        it_capacity_mw=50,
        pue=Decimal("1.30"),
        utilization=Decimal("0.80"),
        price_cents_per_kwh=Decimal("10.333"),
    )
    assert result.annual_consumption_kwh == Decimal("455520000")
    assert result.annual_electricity_cost_usd == Decimal("47068881.6")


def test_price_scenarios_use_one_load_and_exact_differences() -> None:
    rows = compare_price_scenarios(
        it_capacity_mw=50,
        pue=Decimal("1.30"),
        utilization=Decimal("0.80"),
        operating_hours_per_year=8760,
        baseline_name="base",
        scenarios=(
            PriceScenario("low", 10),
            PriceScenario("base", 12),
            PriceScenario("high", Decimal("14"), model_derived_eia_price=True),
        ),
    )
    by_name = {row.scenario_name: row for row in rows}
    assert [row.scenario_name for row in rows] == ["low", "base", "high"]
    assert {row.annual_consumption_kwh for row in rows} == {Decimal("455520000")}
    assert {row.facility_average_demand_mw for row in rows} == {Decimal("52")}
    assert by_name["base"].annual_electricity_cost_usd == Decimal("54662400")
    assert by_name["base"].cost_difference_vs_baseline_usd == 0
    assert by_name["low"].annual_electricity_cost_usd == Decimal("45552000")
    assert by_name["low"].cost_difference_vs_baseline_usd == Decimal("-9110400")
    assert by_name["high"].annual_electricity_cost_usd == Decimal("63772800")
    assert by_name["high"].cost_difference_vs_baseline_usd == Decimal("9110400")
    assert by_name["high"].baseline_scenario_name == "base"
    assert by_name["low"].model_price_warning is None
    assert by_name["high"].model_price_warning == EIA_MODEL_PRICE_WARNING
    assert "FAIL" in EIA_MODEL_PRICE_WARNING
    assert "underpredicted" in EIA_MODEL_PRICE_WARNING
    assert "0%" in EIA_MODEL_PRICE_WARNING
    assert "not a validated investment forecast" in EIA_MODEL_PRICE_WARNING


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"it_capacity_mw": -1}, "it_capacity_mw"),
        ({"it_capacity_mw": True}, "it_capacity_mw"),
        ({"pue": 0}, "pue"),
        ({"pue": -1}, "pue"),
        ({"utilization": Decimal("-0.01")}, "utilization"),
        ({"utilization": Decimal("1.01")}, "utilization"),
        ({"price_cents_per_kwh": -1}, "price_cents_per_kwh"),
        ({"price_cents_per_kwh": float("nan")}, "price_cents_per_kwh"),
        ({"price_cents_per_kwh": float("inf")}, "price_cents_per_kwh"),
        ({"operating_hours_per_year": 0}, "operating_hours_per_year"),
        ({"operating_hours_per_year": -5}, "operating_hours_per_year"),
        ({"operating_hours_per_year": "8,760"}, "operating_hours_per_year"),
    ],
)
def test_invalid_inputs_fail_closed(kwargs: dict[str, object], match: str) -> None:
    base = {
        "it_capacity_mw": 50,
        "pue": Decimal("1.30"),
        "utilization": Decimal("0.80"),
        "price_cents_per_kwh": 12,
    }
    base.update(kwargs)
    with pytest.raises(FinanceInputError, match=match):
        annual_electricity_cost(**base)  # type: ignore[arg-type]


def test_scenario_list_rejects_duplicates_and_a_missing_baseline() -> None:
    load = {
        "it_capacity_mw": 50,
        "pue": Decimal("1.30"),
        "utilization": Decimal("0.80"),
    }
    with pytest.raises(FinanceInputError, match="Duplicate"):
        compare_price_scenarios(
            **load,
            baseline_name="base",
            scenarios=(PriceScenario("base", 12), PriceScenario("base", 10)),
        )
    with pytest.raises(FinanceInputError, match="Baseline"):
        compare_price_scenarios(
            **load,
            baseline_name="missing",
            scenarios=(PriceScenario("base", 12),),
        )
    with pytest.raises(FinanceInputError, match="At least one"):
        compare_price_scenarios(**load, baseline_name="base", scenarios=())


def test_finance_package_does_not_import_models_or_screening() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "infralens" / "finance"
    sources = [path.read_text(encoding="utf-8") for path in root.glob("*.py")]
    assert sources
    combined = "\n".join(sources)
    assert "infralens.evaluation" not in combined
    assert "infralens.screening" not in combined
    assert "capacity_price" not in combined
    assert "risk_score" not in combined

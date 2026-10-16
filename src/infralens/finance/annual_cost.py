"""Annual electricity cost for one hypothetical data-center load.

The identities are:

    facility average demand MW = IT capacity MW × utilization × PUE
    annual consumption kWh = facility average demand MW × 1000 × hours
    annual electricity cost USD = annual consumption kWh × cents/kWh / 100

Hours default to 8760, a non-leap 365-day annualization. A custom hour
count is a positive scenario assumption, not a claim about a calendar year.
PUE must be at least 1. Arithmetic uses ``Decimal`` and does not round
intermediate values. The price is an energy charge only.
Demand charges, tariffs, hedges, taxes, PPAs, network charges, and PJM
capacity prices are not added. A Ridge price is included only when the
caller marks that scenario as model-derived, and then only with the
holdout warning.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Sequence

DEFAULT_OPERATING_HOURS_PER_YEAR = 8760

EIA_MODEL_PRICE_WARNING = (
    "This price is a model-derived EIA scenario, not a validated investment forecast. "
    "The frozen 60-case holdout primary criterion is FAIL. "
    "Both Ridge and the seasonal-naive baseline systematically underpredicted. "
    "Empirical interval coverage was 0%."
)

_DEMAND_UNIT = "MW"
_CONSUMPTION_UNIT = "kWh"
_PRICE_UNIT = "cents/kWh"
_COST_UNIT = "USD"


class FinanceInputError(ValueError):
    """A cost input was missing, nonfinite, or outside the allowed range."""


@dataclass(frozen=True)
class PriceScenario:
    """One named energy price. The load is supplied separately."""

    name: str
    price_cents_per_kwh: Decimal | int | str | float
    model_derived_eia_price: bool = False


@dataclass(frozen=True)
class AnnualElectricityCost:
    """Transparent annual energy-cost result for one price scenario."""

    scenario_name: str
    it_capacity_mw: Decimal
    pue: Decimal
    utilization: Decimal
    operating_hours_per_year: Decimal
    facility_average_demand_mw: Decimal
    annual_consumption_kwh: Decimal
    price_cents_per_kwh: Decimal
    annual_electricity_cost_usd: Decimal
    baseline_scenario_name: str | None
    cost_difference_vs_baseline_usd: Decimal | None
    model_derived_eia_price: bool
    model_price_warning: str | None
    facility_average_demand_unit: str = _DEMAND_UNIT
    annual_consumption_unit: str = _CONSUMPTION_UNIT
    price_unit: str = _PRICE_UNIT
    annual_electricity_cost_unit: str = _COST_UNIT
    cost_difference_unit: str = _COST_UNIT


def annual_electricity_cost(
    *,
    it_capacity_mw: Decimal | int | str | float,
    pue: Decimal | int | str | float,
    utilization: Decimal | int | str | float,
    price_cents_per_kwh: Decimal | int | str | float,
    operating_hours_per_year: Decimal | int | str | float = DEFAULT_OPERATING_HOURS_PER_YEAR,
    scenario_name: str = "scenario",
    model_derived_eia_price: bool = False,
) -> AnnualElectricityCost:
    """Cost one facility load at one energy price.

    ``cost_difference_vs_baseline_usd`` is ``None`` here. Use
    ``compare_price_scenarios`` when a named baseline is required.
    """
    load = _load(it_capacity_mw, pue, utilization, operating_hours_per_year)
    name = _require_name(scenario_name, "scenario_name")
    price = _require_price(price_cents_per_kwh)
    warning = _warning(model_derived_eia_price)
    return _result(
        scenario_name=name,
        load=load,
        price=price,
        baseline_scenario_name=None,
        cost_difference_vs_baseline_usd=None,
        model_derived_eia_price=model_derived_eia_price,
        model_price_warning=warning,
    )


def compare_price_scenarios(
    *,
    it_capacity_mw: Decimal | int | str | float,
    pue: Decimal | int | str | float,
    utilization: Decimal | int | str | float,
    scenarios: Sequence[PriceScenario],
    baseline_name: str,
    operating_hours_per_year: Decimal | int | str | float = DEFAULT_OPERATING_HOURS_PER_YEAR,
) -> tuple[AnnualElectricityCost, ...]:
    """Price one load under several scenarios and subtract the named baseline.

    Every row uses the same capacity, PUE, utilization, and hours. The
    dollar difference is this scenario's annual cost minus the baseline
    annual cost. The baseline row's difference is zero.
    """
    if not scenarios:
        raise FinanceInputError("At least one price scenario is required.")
    load = _load(it_capacity_mw, pue, utilization, operating_hours_per_year)
    baseline = _require_name(baseline_name, "baseline_name")
    named: list[tuple[str, Decimal, bool]] = []
    seen: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, PriceScenario):
            raise FinanceInputError("Each scenario must be a PriceScenario.")
        name = _require_name(scenario.name, "scenario name")
        if name in seen:
            raise FinanceInputError(f"Duplicate price scenario name {name!r}.")
        seen.add(name)
        if not isinstance(scenario.model_derived_eia_price, bool):
            raise FinanceInputError("model_derived_eia_price must be true or false.")
        named.append(
            (name, _require_price(scenario.price_cents_per_kwh), scenario.model_derived_eia_price)
        )
    if baseline not in seen:
        raise FinanceInputError(f"Baseline scenario {baseline!r} is not in the scenario list.")
    costs = {
        name: load.annual_consumption_kwh * price / Decimal(100)
        for name, price, _flag in named
    }
    baseline_cost = costs[baseline]
    return tuple(
        _result(
            scenario_name=name,
            load=load,
            price=price,
            baseline_scenario_name=baseline,
            cost_difference_vs_baseline_usd=costs[name] - baseline_cost,
            model_derived_eia_price=flag,
            model_price_warning=_warning(flag),
        )
        for name, price, flag in named
    )


@dataclass(frozen=True)
class _Load:
    it_capacity_mw: Decimal
    pue: Decimal
    utilization: Decimal
    operating_hours_per_year: Decimal
    facility_average_demand_mw: Decimal
    annual_consumption_kwh: Decimal


def _load(
    it_capacity_mw: object,
    pue: object,
    utilization: object,
    operating_hours_per_year: object,
) -> _Load:
    capacity = _require_decimal(it_capacity_mw, "it_capacity_mw")
    efficiency = _require_decimal(pue, "pue")
    used = _require_decimal(utilization, "utilization")
    hours = _require_decimal(operating_hours_per_year, "operating_hours_per_year")
    if capacity < 0:
        raise FinanceInputError("it_capacity_mw must be zero or positive.")
    if efficiency < 1:
        raise FinanceInputError("pue must be at least 1.")
    if used < 0 or used > 1:
        raise FinanceInputError("utilization must be from 0 through 1.")
    if hours <= 0:
        raise FinanceInputError("operating_hours_per_year must be positive.")
    demand = capacity * used * efficiency
    consumption = demand * Decimal(1000) * hours
    return _Load(
        it_capacity_mw=capacity,
        pue=efficiency,
        utilization=used,
        operating_hours_per_year=hours,
        facility_average_demand_mw=demand,
        annual_consumption_kwh=consumption,
    )


def _result(
    *,
    scenario_name: str,
    load: _Load,
    price: Decimal,
    baseline_scenario_name: str | None,
    cost_difference_vs_baseline_usd: Decimal | None,
    model_derived_eia_price: bool,
    model_price_warning: str | None,
) -> AnnualElectricityCost:
    return AnnualElectricityCost(
        scenario_name=scenario_name,
        it_capacity_mw=load.it_capacity_mw,
        pue=load.pue,
        utilization=load.utilization,
        operating_hours_per_year=load.operating_hours_per_year,
        facility_average_demand_mw=load.facility_average_demand_mw,
        annual_consumption_kwh=load.annual_consumption_kwh,
        price_cents_per_kwh=price,
        annual_electricity_cost_usd=load.annual_consumption_kwh * price / Decimal(100),
        baseline_scenario_name=baseline_scenario_name,
        cost_difference_vs_baseline_usd=cost_difference_vs_baseline_usd,
        model_derived_eia_price=model_derived_eia_price,
        model_price_warning=model_price_warning,
    )


def _warning(model_derived_eia_price: bool) -> str | None:
    if model_derived_eia_price:
        return EIA_MODEL_PRICE_WARNING
    return None


def _require_price(value: object) -> Decimal:
    price = _require_decimal(value, "price_cents_per_kwh")
    if price < 0:
        raise FinanceInputError("price_cents_per_kwh must be zero or positive.")
    return price


def _require_name(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FinanceInputError(f"{field_name} is missing.")
    return value


def _require_decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise FinanceInputError(f"{field_name} is not a number.")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise FinanceInputError(f"{field_name} is not finite.")
        number = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip()
        if text == "" or "," in text:
            raise FinanceInputError(f"{field_name} is not a plain number: {value!r}.")
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise FinanceInputError(f"{field_name} is not a plain number: {value!r}.") from exc
    else:
        raise FinanceInputError(f"{field_name} is not a number.")
    if not number.is_finite():
        raise FinanceInputError(f"{field_name} is not finite.")
    return number

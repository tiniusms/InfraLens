"""Deterministic annual electricity-cost scenarios.

This package does not train a price model and does not read PJM screening
rows. It applies a caller-supplied cents-per-kWh price to a hypothetical
data-center load. See ``docs/finance.md``.
"""

from infralens.finance.annual_cost import (
    DEFAULT_OPERATING_HOURS_PER_YEAR,
    EIA_MODEL_PRICE_WARNING,
    AnnualElectricityCost,
    FinanceInputError,
    PriceScenario,
    annual_electricity_cost,
    compare_price_scenarios,
)

__all__ = [
    "DEFAULT_OPERATING_HOURS_PER_YEAR",
    "EIA_MODEL_PRICE_WARNING",
    "AnnualElectricityCost",
    "FinanceInputError",
    "PriceScenario",
    "annual_electricity_cost",
    "compare_price_scenarios",
]

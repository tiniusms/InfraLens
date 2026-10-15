# Annual electricity-cost calculator

`src/infralens/finance/` turns a hypothetical data-center IT load and a caller-supplied energy price into an annual electricity cost. It does not train the EIA price model, does not read PJM screening rows, and does not discount cash flows.

## Identities

```
facility average demand MW = IT capacity MW × utilization × PUE
annual consumption kWh = facility average demand MW × 1000 × operating hours
annual electricity cost USD = annual consumption kWh × price cents/kWh / 100
```

`operating_hours_per_year` defaults to **8760**, a non-leap 365 × 24 annualization. A custom value must be positive and finite. It is a scenario assumption supplied by the caller. It is not checked against the hours in any calendar year.

Arithmetic uses `Decimal`. Intermediate values are not rounded to cents. Float inputs are read through Python's shortest decimal string, so `1.30` and `0.80` stay `1.3` and `0.8`.

Checked example: 50 MW IT, PUE 1.30, utilization 0.80, 8760 hours, 12 cents/kWh.

- Facility average demand = 52 MW
- Annual consumption = 455,520,000 kWh
- Annual electricity cost = $54,662,400

Zero IT capacity and zero utilization are valid and produce zero consumption. A zero price is a valid zero energy charge. PUE must be at least 1, including exactly 1. Negative capacity, PUE below 1, nonfinite PUE, utilization outside 0–1, a negative or nonfinite price, and nonpositive or nonfinite hours raise `FinanceInputError`. Malformed numbers are not coerced into a cost.

## Price scenarios

`compare_price_scenarios` keeps one load and applies each named price. `cost_difference_vs_baseline_usd` is that scenario's annual cost minus the named baseline's annual cost. The baseline difference is zero. Scenario values are not averaged.

## What the price is

The price is an energy charge in cents per kWh. The result does not add demand charges, a tariff, a hedge, a tax, a PPA structure, a network charge, or a contract term. It does not add a PJM wholesale capacity price on top of an EIA retail price.

A number is not treated as a Ridge prediction unless the caller sets `model_derived_eia_price=True`. The future demo must set that flag automatically for every model-derived EIA price. The flag attaches this warning and does not change the arithmetic:

> This price is a model-derived EIA scenario, not a validated investment forecast. The frozen 60-case holdout primary criterion is FAIL. Both Ridge and the seasonal-naive baseline systematically underpredicted. Empirical interval coverage was 0%.

## Not in this calculator

- No discounted multi-year cost, WACC, or delay sensitivity.
- No risk score and no utility-tariff engine.
- No claim that EIA commercial cents/kWh are a data-center tariff.
- PUE below 1 is rejected. The calculator does not substitute 1.

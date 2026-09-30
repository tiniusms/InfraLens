"""The development model choice stays on the recorded Ridge specification."""

from __future__ import annotations

import pandas as pd

from infralens.evaluation.backtest import HOLDOUT_TARGET_START
from infralens.evaluation.linear import ALPHA_GRID, INNER_VALIDATION_ORIGINS, MIN_FIT_ORIGINS
from infralens.evaluation.selection import (
    FEATURE_SET_ID,
    FROZEN_FEATURES,
    SELECTED_MODEL,
)
from infralens.evaluation.tree import TREE_GRID


def test_ridge_feature_set_and_penalty_procedure_stay_frozen() -> None:
    assert SELECTED_MODEL == "ridge"
    assert FEATURE_SET_ID == "eia_commercial_price_v1"
    assert FROZEN_FEATURES == (
        "price_latest",
        "price_same_month",
        "price_yoy_change",
        "price_trail12_mean",
        "sales_latest",
        "sales_yoy_change",
        "state_id",
        "target_calendar_month",
    )
    assert "revenue_million_usd" not in FROZEN_FEATURES
    assert ALPHA_GRID == (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
    assert INNER_VALIDATION_ORIGINS == 12
    assert MIN_FIT_ORIGINS == 12
    assert HOLDOUT_TARGET_START == "2025-07"
    assert len(TREE_GRID) == 6


def test_freeze_module_does_not_name_a_holdout_score() -> None:
    """The selection module has no holdout metric to update after a future run."""
    import infralens.evaluation.selection as selection

    public = {
        name: getattr(selection, name)
        for name in dir(selection)
        if name.isupper()
    }
    for value in public.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            raise AssertionError(f"Selection freeze should not store a metric: {value}")
        if isinstance(value, pd.Timestamp):
            raise AssertionError("Selection freeze should not store an evaluation date.")

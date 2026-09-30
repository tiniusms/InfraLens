"""Development model-selection freeze for the EIA price forecast.

These names record the 2026-09-29 decision. They do not score the final
holdout and they do not choose a new penalty or feature.
"""

from __future__ import annotations

from infralens.evaluation.features import MODEL_FEATURES

FEATURE_SET_ID: str = "eia_commercial_price_v1"
SELECTED_MODEL: str = "ridge"
NEGATIVE_EVIDENCE_MODEL: str = "hist_gradient_boosting"
FROZEN_FEATURES: tuple[str, ...] = MODEL_FEATURES
DEVELOPMENT_STAGE: str = "development"
FINAL_HOLDOUT_STAGE: str = "final_holdout"

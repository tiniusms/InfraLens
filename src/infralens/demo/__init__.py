"""Historical demonstration foundation.

This package does not train a price model and does not run the final EIA
holdout. The Streamlit page is a prototype over frozen evaluation results
and caller-supplied cost assumptions.
"""

from infralens.demo.foundation import (
    HOLDOUT_PRICE_LABEL,
    PORTABLE_MODE,
    PROTOTYPE_CAPTION,
    TYPED_PRICE_LABEL,
    ArtifactAssessment,
    DemoDataError,
    HoldoutBanner,
    HoldoutRidgeQuote,
    LocalArtifactPaths,
    PriceSource,
    assess_artifacts,
    cost_scenarios,
    default_artifact_paths,
    is_model_derived_price,
    load_holdout_banner,
    load_holdout_quotes,
)

__all__ = [
    "HOLDOUT_PRICE_LABEL",
    "PORTABLE_MODE",
    "PROTOTYPE_CAPTION",
    "TYPED_PRICE_LABEL",
    "ArtifactAssessment",
    "DemoDataError",
    "HoldoutBanner",
    "HoldoutRidgeQuote",
    "LocalArtifactPaths",
    "PriceSource",
    "assess_artifacts",
    "cost_scenarios",
    "default_artifact_paths",
    "is_model_derived_price",
    "load_holdout_banner",
    "load_holdout_quotes",
]

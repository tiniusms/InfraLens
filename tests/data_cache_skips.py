"""The one way a test may skip: a named missing cache from the data policy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_POLICY = Path(__file__).resolve().parents[1] / "data" / "distribution_policy.json"


def skip_missing_cache(cache: str) -> None:
    """Skip with the policy's reason. An unknown cache name fails the test."""

    __tracebackhide__ = True
    reasons = json.loads(_POLICY.read_text(encoding="utf-8"))["skip_reasons"]
    pytest.skip(reasons[cache])

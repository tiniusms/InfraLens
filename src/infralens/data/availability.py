"""Conservative EIA publication-lag assumption for evaluation (not an EIA field)."""

from __future__ import annotations

import re

import pandas as pd

_PERIOD_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

# First day of month m+3. Conservative InfraLens rule, not an EIA timestamp.
PUBLICATION_LAG_MONTHS = 3


def assumed_available_at(period: str) -> pd.Timestamp:
    """Return the assumed availability date for EIA observation month ``period``.

    For ``period='YYYY-MM'`` this is the first day of month *m+3*.
    """
    text = str(period).strip()
    if not _PERIOD_PATTERN.match(text):
        raise ValueError(f"Period is not monthly YYYY-MM: {period!r}.")
    year, month = (int(part) for part in text.split("-"))
    return pd.Timestamp(year=year, month=month, day=1) + pd.DateOffset(
        months=PUBLICATION_LAG_MONTHS
    )


def add_assumed_available_at(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with ``assumed_available_at`` derived from ``period``."""
    out = frame.copy()
    out["assumed_available_at"] = [
        assumed_available_at(period) for period in out["period"]
    ]
    return out

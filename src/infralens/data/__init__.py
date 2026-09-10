"""Shared constants and path helpers for public-data ingestion."""

from pathlib import Path

USER_FACING_STATES: tuple[str, ...] = ("VA", "PA", "OH", "MD", "NJ")

EIA_RETAIL_SALES_DATA_URL = "https://api.eia.gov/v2/electricity/retail-sales/data/"
EIA_RETAIL_SALES_ROUTE = "/v2/electricity/retail-sales/data/"
EIA_FREQUENCY = "monthly"
EIA_SECTOR_ID = "COM"
EIA_START_PERIOD = "2001-01"
EIA_DATA_COLUMNS: tuple[str, ...] = ("price", "sales", "revenue")
EIA_PAGE_LENGTH = 5000


def repository_root() -> Path:
    """Return the git/project root (parent of ``src/``)."""
    return Path(__file__).resolve().parents[3]

"""EIA API v2 retrieval for retail electricity sales.

Does not normalize observations. API keys are read from ``EIA_API_KEY`` and
are never written to logs, stdout, or raw artifacts.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from infralens.data import (
    EIA_DATA_COLUMNS,
    EIA_FREQUENCY,
    EIA_PAGE_LENGTH,
    EIA_RETAIL_SALES_DATA_URL,
    EIA_SECTOR_ID,
    EIA_START_PERIOD,
    USER_FACING_STATES,
    repository_root,
)

_REDACTED = "<redacted>"


class EiaApiError(RuntimeError):
    """Raised when the EIA API cannot be queried successfully."""


def load_eia_api_key() -> str:
    """Load ``EIA_API_KEY`` from the environment (and optional ``.env``)."""
    load_dotenv(repository_root() / ".env")
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        raise EiaApiError("EIA_API_KEY is not set.")
    return key


def redact_secrets(payload: Any) -> Any:
    """Return a deep copy with API keys removed from EIA-style documents."""
    cloned = copy.deepcopy(payload)
    _redact_in_place(cloned)
    return cloned


def _redact_in_place(node: Any) -> None:
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key.lower() in {"api_key", "apikey"} and isinstance(value, str):
                node[key] = _REDACTED
            else:
                _redact_in_place(value)
    elif isinstance(node, list):
        for item in node:
            _redact_in_place(item)


def _query_params(
    api_key: str,
    *,
    states: tuple[str, ...],
    offset: int,
    length: int,
    start: str,
) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = [
        ("api_key", api_key),
        ("frequency", EIA_FREQUENCY),
        ("facets[sectorid][]", EIA_SECTOR_ID),
        ("start", start),
        ("offset", str(offset)),
        ("length", str(length)),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "asc"),
        ("sort[1][column]", "stateid"),
        ("sort[1][direction]", "asc"),
    ]
    for column in EIA_DATA_COLUMNS:
        params.append(("data[]", column))
    for state in states:
        params.append(("facets[stateid][]", state))
    return params


def fetch_retail_sales_pages(
    *,
    api_key: str | None = None,
    states: tuple[str, ...] = USER_FACING_STATES,
    start: str = EIA_START_PERIOD,
    timeout_seconds: float = 60.0,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Download all EIA retail-sales pages for the feasibility slice.

    Returns the JSON objects as received, except callers must redact before
    persisting. Does not print request URLs (they contain the API key).
    """
    key = api_key if api_key is not None else load_eia_api_key()
    owns_client = client is None
    http_client = client or httpx.Client(timeout=timeout_seconds)
    pages: list[dict[str, Any]] = []
    offset = 0
    try:
        while True:
            try:
                response = http_client.get(
                    EIA_RETAIL_SALES_DATA_URL,
                    params=_query_params(
                        key,
                        states=states,
                        offset=offset,
                        length=EIA_PAGE_LENGTH,
                        start=start,
                    ),
                )
            except httpx.HTTPError as exc:
                raise EiaApiError("EIA retail-sales request failed.") from exc
            if response.status_code != 200:
                raise EiaApiError(
                    f"EIA retail-sales request failed with HTTP {response.status_code}."
                )
            try:
                page: dict[str, Any] = response.json()
            except ValueError as exc:
                raise EiaApiError("EIA retail-sales response was not valid JSON.") from exc
            if page.get("error"):
                raise EiaApiError("EIA retail-sales API returned an error.")
            pages.append(page)
            body = page.get("response") or {}
            rows = body.get("data") or []
            try:
                total = int(body.get("total", len(rows)))
            except (TypeError, ValueError):
                total = offset + len(rows)
            offset += len(rows)
            if not rows or offset >= total:
                break
    finally:
        if owns_client:
            http_client.close()
    if not pages:
        raise EiaApiError("EIA retail-sales returned no pages.")
    return pages


def write_raw_eia_artifact(
    pages: list[dict[str, Any]],
    destination: Path,
    *,
    retrieved_at: datetime,
    states: tuple[str, ...],
    start: str,
) -> Path:
    """Write an immutable, key-redacted raw JSON bundle. Refuses to overwrite."""
    if destination.exists():
        raise FileExistsError(f"Raw EIA artifact already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "retrieved_at": retrieved_at.astimezone(timezone.utc).isoformat(),
        "source": "U.S. Energy Information Administration",
        "source_route": "/v2/electricity/retail-sales/data/",
        "endpoint": EIA_RETAIL_SALES_DATA_URL,
        "frequency": EIA_FREQUENCY,
        "sectorid": EIA_SECTOR_ID,
        "states": list(states),
        "start": start,
        "data_columns": list(EIA_DATA_COLUMNS),
        "page_count": len(pages),
        "pages": redact_secrets(pages),
    }
    destination.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return destination

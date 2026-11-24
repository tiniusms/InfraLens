"""Save one immutable raw EIA retail-sales snapshot (Version 2 Phase 2, criterion 5).

Owner-run only; CI never runs this. It needs ``EIA_API_KEY`` and network access:

    python scripts/eia_snapshot.py --epm-release-date 2026-11-24 --epm-data-month 2026-09

It writes one new directory under ``data/raw/eia/vintages/<UTC timestamp>/`` and
prints the entry to add to ``data/eia_vintage_ledger.json``. It refuses to
overwrite, never records the API key, and writes nothing to ``data/interim/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.parse
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

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
from infralens.data.eia_client import _query_params, load_eia_api_key

ROUTE_URL = "https://api.eia.gov/v2/electricity/retail-sales/"
BULK_MANIFEST_URL = "https://www.eia.gov/opendata/bulk/manifest.txt"
METADATA_FILE = "snapshot_metadata.json"
TIER = "tier_1_observed_real_time"
_REDACTED = b"<redacted>"
_KEPT_HEADERS = re.compile(
    r"(^date$|modified|etag|update|period|version|cache|^age$|expires|"
    r"content-type|content-encoding|content-length|^server$)",
    re.I,
)
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class SnapshotError(RuntimeError):
    """A snapshot could not be taken. Messages never contain a request URL."""


def _utc_text(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def scrub_key(body: bytes, api_key: str) -> tuple[bytes, int]:
    """Replace any echoed API key. All other bytes stay as received."""

    count = 0
    for form in {api_key.encode(), urllib.parse.quote(api_key, safe="").encode()}:
        count += body.count(form)
        body = body.replace(form, _REDACTED)
    return body, count


def payload_sha256(pages: list[dict[str, Any]]) -> str:
    """Hash the data rows in a stable order, independent of paging and metadata."""

    rows = [row for page in pages for row in page["response"]["data"]]
    rows.sort(key=lambda row: (row["period"], row["stateid"], row["sectorid"]))
    text = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_params(params: list[tuple[str, str]]) -> list[list[str]]:
    return [[name, value] for name, value in params if name != "api_key"]


def _safe_url(url: str, params: list[tuple[str, str]]) -> str:
    kept = [(name, value) for name, value in params if name != "api_key"]
    return f"{url}?{urllib.parse.urlencode(kept)}" if kept else url


def _kept_headers(response: httpx.Response, api_key: str) -> dict[str, str]:
    kept = {name.lower(): value for name, value in response.headers.items() if _KEPT_HEADERS.search(name)}
    if any(api_key in value for value in kept.values()):
        raise SnapshotError("A response header contained the API key. Nothing was written.")
    return kept


def _get(client: httpx.Client, url: str, params: list[tuple[str, str]], label: str) -> httpx.Response:
    try:
        response = client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise SnapshotError(f"{label} request failed: {type(exc).__name__}.") from None
    if response.status_code != 200:
        raise SnapshotError(f"{label} request returned HTTP {response.status_code}.")
    return response


def _bulk_state(client: httpx.Client, clock: Callable[[], datetime]) -> dict[str, str | None]:
    response = _get(client, BULK_MANIFEST_URL, [], "Bulk manifest")
    try:
        entry = json.loads(response.text)["dataset"]["ELEC"]
    except (ValueError, KeyError, TypeError):
        raise SnapshotError("The bulk manifest has no ELEC entry.") from None
    return {
        "last_updated": entry.get("last_updated"),
        "modified": entry.get("modified"),
        "checked_at": _utc_text(clock()),
    }


def _parse(body: bytes, label: str) -> dict[str, Any]:
    try:
        document = json.loads(body)
        if not isinstance(document["response"], dict):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        raise SnapshotError(f"{label} response was not the expected JSON.") from None
    return document


def _validate_release(release_date: str, data_month: str) -> None:
    try:
        date.fromisoformat(release_date)
    except ValueError:
        raise SnapshotError("--epm-release-date must be YYYY-MM-DD.") from None
    if not _MONTH.match(data_month):
        raise SnapshotError("--epm-data-month must be YYYY-MM.")


def take_snapshot(
    *,
    root: Path,
    api_key: str,
    client: httpx.Client,
    epm_release_date: str,
    epm_data_month: str,
    clock: Callable[[], datetime] = _now,
) -> dict[str, Any]:
    """Fetch the panel, write one new directory, and return its ledger entry."""

    _validate_release(epm_release_date, epm_data_month)
    if not api_key:
        raise SnapshotError("EIA_API_KEY is not set.")
    started = clock()
    stamp = started.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    vintages = root / "data" / "raw" / "eia" / "vintages"
    target = vintages / stamp
    if target.exists():
        raise SnapshotError(f"Snapshot {stamp} already exists and will not be overwritten.")

    before = _bulk_state(client, clock)
    files: dict[str, bytes] = {}
    requests: list[dict[str, Any]] = []

    response = _get(client, ROUTE_URL, [("api_key", api_key)], "Route metadata")
    body, replaced = scrub_key(response.content, api_key)
    route = _parse(body, "Route metadata")["response"]
    files["route_metadata.json"] = body
    requests.append(
        {
            "file": "route_metadata.json",
            "purpose": "route metadata; the only API source of the latest-period field",
            "method": "GET",
            "url": ROUTE_URL,
            "params": [],
            "url_without_api_key": ROUTE_URL,
            "http_status": response.status_code,
            "retrieved_at": _utc_text(clock()),
            "headers": _kept_headers(response, api_key),
            "api_key_occurrences_replaced": replaced,
        }
    )

    pages: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None
    while True:
        params = _query_params(
            api_key,
            states=USER_FACING_STATES,
            offset=offset,
            length=EIA_PAGE_LENGTH,
            start=EIA_START_PERIOD,
        )
        response = _get(client, EIA_RETAIL_SALES_DATA_URL, params, "Data page")
        body, replaced = scrub_key(response.content, api_key)
        document = _parse(body, "Data page")
        try:
            page_total = int(document["response"]["total"])
        except (KeyError, TypeError, ValueError):
            raise SnapshotError("Data page has no valid response.total.") from None
        total = page_total if total is None else total
        if page_total != total:
            raise SnapshotError("response.total changed between pages. Nothing was written.")
        rows = document["response"].get("data") or []
        if not rows:
            raise SnapshotError("EIA returned an empty page before response.total. Nothing was written.")
        pages.append(document)
        name = f"data_page_{len(pages):04d}.json"
        files[name] = body
        requests.append(
            {
                "file": name,
                "purpose": "retail-sales data page",
                "method": "GET",
                "url": EIA_RETAIL_SALES_DATA_URL,
                "params": _safe_params(params),
                "url_without_api_key": _safe_url(EIA_RETAIL_SALES_DATA_URL, params),
                "http_status": response.status_code,
                "retrieved_at": _utc_text(clock()),
                "headers": _kept_headers(response, api_key),
                "row_count": len(rows),
                "response_total": page_total,
                "api_version": document.get("apiVersion"),
                "api_key_occurrences_replaced": replaced,
            }
        )
        offset += len(rows)
        if offset >= total:
            break
    completed = clock()
    after = _bulk_state(client, clock)
    if (before["last_updated"], before["modified"]) != (after["last_updated"], after["modified"]):
        raise SnapshotError("EIA updated the dataset during retrieval. Nothing was written. Run it again.")
    if offset != total:
        raise SnapshotError("The snapshot is incomplete. Nothing was written.")
    periods = sorted({row["period"] for page in pages for row in page["response"]["data"]})
    if periods[-1] != epm_data_month:
        raise SnapshotError(
            f"The API's latest period is {periods[-1]}, not EPM data month {epm_data_month}. Nothing was written."
        )

    listed = [
        {"file": name, "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}
        for name, content in files.items()
    ]
    metadata = {
        "snapshot_kind": "forward archive snapshot (Phase 2 criterion 5)",
        "retrieval_started_at_utc": _utc_text(started),
        "retrieval_completed_at_utc": _utc_text(completed),
        "source": "U.S. Energy Information Administration API v2",
        "route": "/v2/electricity/retail-sales/data/",
        "selection": {
            "frequency": EIA_FREQUENCY,
            "sectorid": EIA_SECTOR_ID,
            "stateid": list(USER_FACING_STATES),
            "start": EIA_START_PERIOD,
            "data": list(EIA_DATA_COLUMNS),
        },
        "api_latest_period_field": {
            "source": "route metadata response.endPeriod",
            "endPeriod": route.get("endPeriod"),
            "startPeriod": route.get("startPeriod"),
            "defaultFrequency": route.get("defaultFrequency"),
        },
        "data_latest_period_in_pages": periods[-1],
        "data_earliest_period_in_pages": periods[0],
        "row_count": offset,
        "response_total": total,
        "page_count": len(pages),
        "follows_epm_release": {"release_date": epm_release_date, "data_month": epm_data_month},
        "bulk_manifest_elec_before": before,
        "bulk_manifest_elec_after": after,
        "raw_fidelity_note": (
            "Response bytes are saved as received, except that any occurrence of the API key "
            "echoed by EIA is replaced with <redacted>. Replacement counts are listed per request."
        ),
        "requests": requests,
        "files": listed,
    }
    metadata_bytes = (json.dumps(metadata, indent=2) + "\n").encode("utf-8")
    if any(api_key.encode() in content for content in (*files.values(), metadata_bytes)):
        raise SnapshotError("The API key was found in the output. Nothing was written.")

    vintages.mkdir(parents=True, exist_ok=True)
    temporary = vintages / f".incomplete-{stamp}-{os.getpid()}"
    temporary.mkdir()
    try:
        for name, content in {**files, METADATA_FILE: metadata_bytes}.items():
            path = temporary / name
            path.write_bytes(content)
            path.chmod(0o444)
        if target.exists():
            raise SnapshotError(f"Snapshot {stamp} already exists and will not be overwritten.")
        os.rename(temporary, target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        "id": stamp,
        "path": f"data/raw/eia/vintages/{stamp}",
        "retrieved_at": _utc_text(started),
        "retrieval_completed_at": _utc_text(completed),
        "files": sorted(
            [
                *listed,
                {
                    "file": METADATA_FILE,
                    "sha256": hashlib.sha256(metadata_bytes).hexdigest(),
                    "size_bytes": len(metadata_bytes),
                },
            ],
            key=lambda item: item["file"],
        ),
        "payload_sha256": payload_sha256(pages),
        "row_count": offset,
        "earliest_period": periods[0],
        "latest_period": periods[-1],
        "follows_epm_release": {"release_date": epm_release_date, "data_month": epm_data_month},
        "bulk_manifest_elec_last_updated": after["last_updated"],
        "tier": TIER,
        "capture": "after_release",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Save one immutable raw EIA retail-sales snapshot.")
    parser.add_argument("--epm-release-date", required=True, help="EPM release this follows, YYYY-MM-DD.")
    parser.add_argument("--epm-data-month", required=True, help="Latest data month in that release, YYYY-MM.")
    arguments = parser.parse_args(argv)
    try:
        api_key = load_eia_api_key()
        with httpx.Client(timeout=60.0, follow_redirects=False) as client:
            entry = take_snapshot(
                root=repository_root(),
                api_key=api_key,
                client=client,
                epm_release_date=arguments.epm_release_date,
                epm_data_month=arguments.epm_data_month,
            )
    except Exception as exc:
        message = str(exc) if isinstance(exc, SnapshotError) else f"Snapshot failed: {type(exc).__name__}."
        print(message, file=sys.stderr)
        return 1
    print("Add this entry to data/eia_vintage_ledger.json under snapshots:")
    print(json.dumps(entry, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

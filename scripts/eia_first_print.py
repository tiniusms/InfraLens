"""Rebuild EIA first-print prices and publication timing (Phase 2 criterion 5, PR B).

Owner-run only; CI never runs this.

    python scripts/eia_first_print.py fetch    # download EPM back-issue ZIPs, record metadata
    python scripts/eia_first_print.py build    # parse 730 first-print values, local-only
    python scripts/eia_first_print.py timing   # write the committed dates-only timing table
    python scripts/eia_first_print.py checks   # year-ago, outlier, and revision checks

ZIPs and parsed values stay local-only. Only metadata and dates are committed.
Reference months from 2024-07 on are never parsed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pyarrow.parquet as pq

from infralens.data import repository_root
from infralens.data.epm_first_print import (
    FIRST_REFERENCE_MONTH,
    LAST_REFERENCE_MONTH,
    LAST_TIMING_REFERENCE_MONTH,
    STATE_NAMES,
    add_months,
    final_data_years,
    first_print_issue_months,
    issue_archive_stem,
    parse_issue,
    price_table_metadata,
    read_price_table,
    reference_month_for_issue,
    timing_issue_months,
    timing_row,
    timing_summary,
)

ARCHIVE_URL = "https://www.eia.gov/electricity/monthly/archive"
INDEX_URL = "https://www.eia.gov/electricity/monthly/backissues.php"
ZIP_DIRECTORY = "data/raw/eia/epm_backissues"
OUTPUT_DIRECTORY = "data/processed/eia_first_print"
FIRST_PRINT_FILE = "first_print_commercial_price.parquet"
GAPS_FILE = "first_print_gaps.json"
CHECKS_FILE = "first_print_checks.json"
SOURCES_FILE = "data/epm_backissue_sources.json"
TIMING_FILE = "data/epm_publication_timing.csv"
YEAR_AGO_FILE = "data/epm_year_ago_differences.csv"
YEAR_AGO_COLUMNS = [
    "state",
    "reference_month",
    "first_print_issue",
    "year_ago_issue",
    "year_ago_cell",
    "difference_cents_per_kwh",
    "year_ago_class",
    "year_ago_class_refined",
]
FROZEN_EXTRACT = "data/interim/eia_retail_sales_monthly_com_20260911T190524Z.parquet"
USER_AGENT = "research-data-client/1.0"
_RETRIES = 5
_PAUSE_SECONDS = 1.0


class FetchError(RuntimeError):
    """An EPM file could not be retrieved."""


def _utc_text(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def empty_sources() -> dict[str, Any]:
    return {
        "metadata_version": 1,
        "description": (
            "Source metadata for archived Electric Power Monthly issues (Phase 2 criterion 5, PR B). "
            "ZIPs and parsed values are local-only. File dates are proxies: a server date is an upper "
            "bound on first publication because files can be re-uploaded, and a table's internal "
            "timestamp shows when it was built."
        ),
        "decision": "DECISIONS.md, 2026-11-23, EIA vintage policy and forward archive",
        "publisher": "U.S. Energy Information Administration",
        "index_url": INDEX_URL,
        "local_directory": f"{ZIP_DIRECTORY}/",
        "first_print_window": {"first": FIRST_REFERENCE_MONTH, "last": LAST_REFERENCE_MONTH},
        "timing_window": {"first": FIRST_REFERENCE_MONTH, "last": LAST_TIMING_REFERENCE_MONTH},
        "issues": [],
    }


def _request(client: httpx.Client, method: str, url: str, sleep: Callable[[float], None]) -> httpx.Response:
    last = "no response"
    for attempt in range(_RETRIES):
        try:
            response = client.request(method, url)
        except httpx.HTTPError as exc:
            last = type(exc).__name__
        else:
            if response.status_code < 500:
                return response
            last = f"HTTP {response.status_code}"
        sleep(2.0 * (attempt + 1))
    raise FetchError(f"{method} {url} failed after {_RETRIES} attempts: {last}")


def _last_modified(response: httpx.Response, url: str) -> str:
    header = response.headers.get("last-modified")
    if not header:
        raise FetchError(f"{url} has no Last-Modified header.")
    return _utc_text(parsedate_to_datetime(header))


def fetch_issue(
    root: Path,
    issue_month: str,
    client: httpx.Client,
    clock: Callable[[], datetime] = _now,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Download one issue ZIP once and return its metadata. Never overwrites."""

    stem = issue_archive_stem(issue_month)
    relative = f"{ZIP_DIRECTORY}/{stem}.zip"
    target = root / relative
    if target.exists():
        raise FetchError(f"{relative} exists but has no metadata entry; refusing to overwrite it.")
    url = f"{ARCHIVE_URL}/{stem}.zip"
    response = _request(client, "GET", url, sleep)
    if response.status_code != 200:
        raise FetchError(f"GET {url} returned HTTP {response.status_code}.")
    retrieved_at = clock()
    body = response.content
    declared = response.headers.get("content-length")
    if declared is not None and int(declared) != len(body):
        raise FetchError(f"{url} was truncated.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".zip.tmp")
    temporary.write_bytes(body)
    try:
        table = price_table_metadata(temporary)
        pdf_url = f"{ARCHIVE_URL}/{stem}.pdf"
        pdf = _request(client, "HEAD", pdf_url, sleep)
        pdf_date = _last_modified(pdf, pdf_url) if pdf.status_code == 200 else None
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    in_window = reference_month_for_issue(issue_month) <= LAST_REFERENCE_MONTH
    return {
        "issue_month": issue_month,
        "reference_month": reference_month_for_issue(issue_month),
        "reference_month_basis": "pending_table_header" if in_window else "issue_month_minus_2_not_opened",
        "source_url": url,
        "local_path": relative,
        "server_last_modified_utc": _last_modified(response, url),
        "pdf_url": pdf_url if pdf_date else None,
        "pdf_server_last_modified_utc": pdf_date,
        "retrieved_at": _utc_text(retrieved_at),
        "size_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "price_table": table,
    }


def command_fetch(root: Path) -> int:
    path = root / SOURCES_FILE
    sources = json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty_sources()
    done = {item["issue_month"] for item in sources["issues"]}
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=120.0, follow_redirects=False) as client:
        for issue_month in timing_issue_months():
            if issue_month in done:
                continue
            sources["issues"].append(fetch_issue(root, issue_month, client))
            sources["issues"].sort(key=lambda item: item["issue_month"])
            _write_json(path, sources)
            print(f"fetched {issue_month} ({len(sources['issues'])}/171)", flush=True)
            time.sleep(_PAUSE_SECONDS)
    return 0


def _verified_sources(root: Path) -> dict[str, Any]:
    sources = json.loads((root / SOURCES_FILE).read_text(encoding="utf-8"))
    for item in sources["issues"]:
        data = (root / item["local_path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise FetchError(f"{item['local_path']} does not match its recorded SHA-256.")
    return sources


def command_build(root: Path) -> int:
    sources = _verified_sources(root)
    by_issue = {item["issue_month"]: item for item in sources["issues"]}
    rows: list[dict[str, Any]] = []
    for issue_month in first_print_issue_months():
        item = by_issue[issue_month]
        records = parse_issue(root / item["local_path"], issue_month)
        if {record.table_sha256 for record in records} != {item["price_table"]["sha256"]}:
            raise FetchError(f"{issue_month}: parsed table does not match the recorded SHA-256.")
        rows.extend(record.as_row() for record in records)
        item["reference_month_basis"] = "table_header"
    frame = pd.DataFrame(rows).sort_values(["reference_month", "state"]).reset_index(drop=True)
    if frame["reference_month"].max() > LAST_REFERENCE_MONTH:
        raise FetchError("A reference month after the window reached the output.")
    output = root / OUTPUT_DIRECTORY
    output.mkdir(parents=True, exist_ok=True)
    target = output / FIRST_PRINT_FILE
    if target.exists() and not pd.read_parquet(target).equals(frame):
        raise FetchError(f"{target} exists with different content; refusing to overwrite it.")
    if not target.exists():
        frame.to_parquet(target, index=False)
    gaps = frame.loc[frame["gap_reason"].notna(), ["state", "reference_month", "issue_month", "cell", "gap_reason"]]
    _write_json(output / GAPS_FILE, {"gap_count": len(gaps), "gaps": gaps.to_dict("records")})
    _write_json(root / SOURCES_FILE, sources)
    print(f"parsed {len(frame)} rows, {frame['price_cents_per_kwh'].notna().sum()} values, {len(gaps)} gaps")
    return 0


def command_timing(root: Path) -> int:
    sources = _verified_sources(root)
    rows = [timing_row(item) for item in sources["issues"]]
    with (root / TIMING_FILE).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(timing_summary(rows), indent=2))
    return 0


def _frozen_prices(root: Path) -> pd.DataFrame:
    """Frozen-extract prices for the window only; later rows are filtered at read time."""

    table = pq.read_table(
        root / FROZEN_EXTRACT,
        columns=["period", "state_id", "sector_id", "price_cents_per_kwh"],
        filters=[("period", "<=", LAST_REFERENCE_MONTH), ("period", ">=", FIRST_REFERENCE_MONTH)],
    )
    frame = table.to_pandas()
    frame = frame[(frame["sector_id"] == "COM") & frame["state_id"].isin(list(STATE_NAMES))]
    frame = frame.rename(
        columns={"period": "reference_month", "state_id": "state", "price_cents_per_kwh": "current_price"}
    )
    frame["current_price"] = pd.to_numeric(frame["current_price"], errors="coerce")
    return frame[["reference_month", "state", "current_price"]]


def year_ago_check(frame: pd.DataFrame) -> dict[str, Any]:
    first = frame[["state", "reference_month", "price_cents_per_kwh", "issue_month"]].rename(
        columns={
            "reference_month": "year_ago_month",
            "price_cents_per_kwh": "earlier_first_print",
            "issue_month": "earlier_issue",
        }
    )
    pairs = frame.merge(first, on=["state", "year_ago_month"], how="inner")
    pairs = pairs[pairs["earlier_first_print"].notna() & pairs["year_ago_price_cents_per_kwh"].notna()].copy()
    pairs["difference"] = (pairs["year_ago_price_cents_per_kwh"] - pairs["earlier_first_print"]).round(2)
    differ = pairs[pairs["difference"] != 0].copy()
    differ["absolute"] = differ["difference"].abs()
    differ = differ.sort_values(["absolute", "reference_month", "state"], ascending=[False, True, True])
    columns = [
        "state",
        "year_ago_month",
        "issue_month",
        "year_ago_cell",
        "year_ago_price_cents_per_kwh",
        "earlier_issue",
        "earlier_first_print",
        "difference",
    ]
    return {
        "compared": len(pairs),
        "matched": int((pairs["difference"] == 0).sum()),
        "match_rate": float((pairs["difference"] == 0).mean()),
        "mismatched": len(differ),
        "mean_absolute_difference": float(differ["absolute"].mean()) if len(differ) else 0.0,
        "by_state": {
            state: {
                "compared": int((pairs["state"] == state).sum()),
                "mismatched": int((differ["state"] == state).sum()),
            }
            for state in STATE_NAMES
        },
        "by_year_ago_year": {
            str(year): {
                "compared": int((pairs["year_ago_month"].str[:4] == str(year)).sum()),
                "mismatched": int((differ["year_ago_month"].str[:4] == str(year)).sum()),
            }
            for year in sorted({int(month[:4]) for month in pairs["year_ago_month"]})
        },
        "mismatches": differ[columns].to_dict("records"),
    }


def revision_statistics(frame: pd.DataFrame, current: pd.DataFrame) -> dict[str, Any]:
    joined = frame.merge(current, on=["reference_month", "state"], how="left", validate="one_to_one")
    joined = joined[joined["price_cents_per_kwh"].notna() & joined["current_price"].notna()].copy()
    joined["change"] = joined["current_price"] - joined["price_cents_per_kwh"]
    joined["absolute"] = joined["change"].abs()
    joined["percent"] = joined["absolute"] / joined["price_cents_per_kwh"] * 100

    def _block(part: pd.DataFrame) -> dict[str, float]:
        return {
            "values": int(len(part)),
            "mean_absolute": round(float(part["absolute"].mean()), 3),
            "p95_absolute": round(float(part["absolute"].quantile(0.95)), 3),
            "max_absolute": round(float(part["absolute"].max()), 2),
            "mean_absolute_percent": round(float(part["percent"].mean()), 2),
        }

    outliers = {("MD", "2014-09"), ("MD", "2022-08")}
    keep = [(state, month) not in outliers for state, month in zip(joined["state"], joined["reference_month"])]
    return {
        "all": _block(joined),
        "by_state": {state: _block(joined[joined["state"] == state]) for state in STATE_NAMES},
        "share_unchanged": round(float((joined["absolute"].round(6) == 0).mean()), 4),
        "share_within_0_10": round(float((joined["absolute"].round(6) <= 0.10).mean()), 4),
        "mean_signed_change": round(float(joined["change"].mean()), 3),
        "excluding_two_md_outliers": _block(joined[keep]),
    }


def outlier_report(frame: pd.DataFrame, current: pd.DataFrame) -> list[dict[str, Any]]:
    joined = frame.merge(current, on=["reference_month", "state"], how="left", validate="one_to_one")
    report = []
    for month in ("2014-09", "2022-08"):
        row = joined[(joined["state"] == "MD") & (joined["reference_month"] == month)].iloc[0]
        neighbours = [add_months(month, offset) for offset in (-2, -1, 1, 2)]
        around = joined[(joined["state"] == "MD") & joined["reference_month"].isin(neighbours)]
        report.append(
            {
                "state": "MD",
                "reference_month": month,
                "issue_month": row["issue_month"],
                "cell": row["cell"],
                "first_print": row["price_cents_per_kwh"],
                "current_frozen_extract": row["current_price"],
                "neighbour_first_prints": dict(zip(around["reference_month"], around["price_cents_per_kwh"])),
                "neighbour_current": dict(zip(around["reference_month"], around["current_price"])),
                "year_ago_column_12_issues_later": _year_ago_value(frame, "MD", month),
                "action": "reported unchanged",
            }
        )
    return report


def _year_ago_value(frame: pd.DataFrame, state: str, month: str) -> dict[str, Any] | None:
    later = frame[(frame["state"] == state) & (frame["year_ago_month"] == month)]
    if later.empty:
        return None
    row = later.iloc[0]
    return {
        "issue_month": row["issue_month"],
        "cell": row["year_ago_cell"],
        "value": row["year_ago_price_cents_per_kwh"],
    }


def year_ago_versus_current(frame: pd.DataFrame, current: pd.DataFrame) -> dict[str, Any]:
    """How often the year-ago column already equals the frozen extract, split by first-print agreement."""

    later = frame[["state", "year_ago_month", "year_ago_price_cents_per_kwh"]].rename(
        columns={"year_ago_month": "reference_month", "year_ago_price_cents_per_kwh": "year_ago"}
    )
    first = frame[["state", "reference_month", "price_cents_per_kwh"]].rename(
        columns={"price_cents_per_kwh": "first_print"}
    )
    joined = later.merge(first, on=["state", "reference_month"]).merge(current, on=["state", "reference_month"])
    joined = joined.dropna(subset=["year_ago", "first_print", "current_price"])
    differs = joined["year_ago"].round(2) != joined["first_print"].round(2)
    equals_current = joined["year_ago"].round(2) == joined["current_price"].round(2)
    return {
        "compared": int(len(joined)),
        "year_ago_equals_current": int(equals_current.sum()),
        "differs_from_first_print": int(differs.sum()),
        "differs_from_first_print_and_equals_current": int((differs & equals_current).sum()),
    }


def annual_final_releases(root: Path, sources: dict[str, Any]) -> dict[int, dict[str, str]]:
    """The first in-window issue whose Table 5.6.A notes label each data year final."""

    releases: dict[int, dict[str, str]] = {}
    for item in sources["issues"]:
        if item["reference_month"] > LAST_REFERENCE_MONTH:
            continue
        _, table, _ = read_price_table(root / item["local_path"])
        for year, cell in final_data_years(table, item["issue_month"]).items():
            releases.setdefault(
                year,
                {
                    "issue_month": item["issue_month"],
                    "note_cell": cell,
                    "table_name": item["price_table"]["name"],
                    "server_date_proxy": item["server_last_modified_utc"][:10],
                    "table_built_date_proxy": item["price_table"]["internal_modified_utc"][:10],
                },
            )
    return releases


def classify_year_ago(
    frame: pd.DataFrame, current: pd.DataFrame, releases: dict[int, dict[str, str]]
) -> pd.DataFrame:
    """Classify each comparison. Class (c) needs the data year's final-labelled issue.

    ``d_has_revised_preliminary_step`` is a sensitivity only: an issue labelling the
    prior year final lies after the first print and no later than the year-ago issue.
    """

    first = frame[["state", "reference_month", "price_cents_per_kwh", "issue_month", "cell"]].rename(
        columns={
            "reference_month": "year_ago_month",
            "price_cents_per_kwh": "first_print",
            "issue_month": "first_print_issue",
            "cell": "first_print_cell",
        }
    )
    pairs = frame[["state", "year_ago_month", "issue_month", "year_ago_cell", "year_ago_price_cents_per_kwh"]].merge(
        first, on=["state", "year_ago_month"], how="inner"
    )
    pairs = pairs.rename(columns={"issue_month": "year_ago_issue", "year_ago_price_cents_per_kwh": "year_ago"})
    pairs = pairs.merge(
        current.rename(columns={"reference_month": "year_ago_month"}),
        on=["state", "year_ago_month"],
        how="left",
        validate="one_to_one",
    )
    if pairs[["first_print", "year_ago", "current_price"]].isna().any().any():
        raise FetchError("A year-ago comparison is missing a value.")
    classes, sensitivity = [], []
    for row in pairs.itertuples(index=False):
        year = int(row.year_ago_month[:4])
        final = releases.get(year)
        prior = releases.get(year - 1)
        if round(row.year_ago, 2) == round(row.first_print, 2):
            label = "a"
        elif round(row.year_ago, 2) == round(row.current_price, 2):
            label = "b"
        elif final is not None and row.year_ago_issue >= final["issue_month"]:
            label = "c"
        else:
            label = "d"
        classes.append(label)
        sensitivity.append(
            label == "d"
            and prior is not None
            and row.first_print_issue < prior["issue_month"] <= row.year_ago_issue
        )
    pairs["year_ago_class"] = classes
    pairs["d_has_revised_preliminary_step"] = sensitivity
    # Refined reading (owner decision, 2026-11-23, after the strict results): the
    # revised-preliminary step counts as an annual release for class (c).
    pairs["year_ago_class_refined"] = ["c" if step else label for label, step in zip(classes, sensitivity)]
    pairs["difference"] = (pairs["year_ago"] - pairs["first_print"]).round(2)
    return pairs.sort_values(["year_ago_month", "state"]).reset_index(drop=True)


def year_ago_class_summary(pairs: pd.DataFrame) -> dict[str, Any]:
    labels = ["a", "b", "c", "d"]

    def counts(part: pd.DataFrame, column: str = "year_ago_class") -> dict[str, int]:
        return {label: int((part[column] == label).sum()) for label in labels}

    refined = "year_ago_class_refined"
    remaining = pairs[pairs[refined] == "d"]

    d_cases = pairs[pairs["year_ago_class"] == "d"].copy()
    d_cases["absolute"] = d_cases["difference"].abs()
    d_cases = d_cases.sort_values(["absolute", "year_ago_month", "state"], ascending=[False, True, True])
    with_step = int(d_cases["d_has_revised_preliminary_step"].sum())
    return {
        "compared": int(len(pairs)),
        "counts": counts(pairs),
        "by_state": {state: counts(pairs[pairs["state"] == state]) for state in STATE_NAMES},
        "by_data_year": {
            year: counts(pairs[pairs["year_ago_month"].str[:4] == year])
            for year in sorted(pairs["year_ago_month"].str[:4].unique())
        },
        "refined_counts": counts(pairs, refined),
        "refined_by_state": {state: counts(pairs[pairs["state"] == state], refined) for state in STATE_NAMES},
        "refined_by_data_year": {
            year: counts(pairs[pairs["year_ago_month"].str[:4] == year], refined)
            for year in sorted(pairs["year_ago_month"].str[:4].unique())
        },
        "refined_d_cases": remaining[
            [
                "state",
                "year_ago_month",
                "first_print_issue",
                "first_print_cell",
                "first_print",
                "year_ago_issue",
                "year_ago_cell",
                "year_ago",
                "current_price",
                "difference",
            ]
        ].to_dict("records"),
        "tick_limit_d": 13,
        "d_with_revised_preliminary_step": with_step,
        "d_without_any_annual_step": int(len(d_cases) - with_step),
        "d_cases": d_cases[
            [
                "state",
                "year_ago_month",
                "first_print_issue",
                "first_print_cell",
                "first_print",
                "year_ago_issue",
                "year_ago_cell",
                "year_ago",
                "current_price",
                "difference",
                "d_has_revised_preliminary_step",
            ]
        ].to_dict("records"),
    }


def revised_preliminary_test(pairs: pd.DataFrame, releases: dict[int, dict[str, str]]) -> dict[str, Any]:
    """Compare change rates with and without a prior-year final release in between.

    Only comparisons whose year-ago issue precedes the data year's own final label
    are used, so the final release itself cannot explain a change.
    """

    def group(row: Any) -> str | None:
        year = int(row.year_ago_month[:4])
        final, prior = releases.get(year), releases.get(year - 1)
        if final is not None and row.year_ago_issue >= final["issue_month"]:
            return None
        if prior is not None and row.first_print_issue < prior["issue_month"] <= row.year_ago_issue:
            return "prior_year_final_in_between"
        return "no_annual_release_in_between"

    frame = pairs.copy()
    frame["group"] = [group(row) for row in frame.itertuples(index=False)]
    frame = frame[frame["group"].notna()]
    frame["changed"] = frame["year_ago_class"] != "a"

    def block(part: pd.DataFrame) -> dict[str, Any]:
        compared = int(len(part))
        changed = int(part["changed"].sum())
        return {"compared": compared, "changed": changed, "change_rate": round(changed / compared, 4) if compared else None}

    return {
        name: {
            **block(frame[frame["group"] == name]),
            "by_data_year": {
                year: block(part)
                for year, part in frame[frame["group"] == name].groupby(frame["year_ago_month"].str[:4])
            },
        }
        for name in ("prior_year_final_in_between", "no_annual_release_in_between")
    }


def write_year_ago_differences(path: Path, pairs: pd.DataFrame) -> None:
    """Commit every difference and its class without committing a price level."""

    rows = pairs[pairs["year_ago_class"] != "a"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(YEAR_AGO_COLUMNS)
        for item in rows.itertuples(index=False):
            writer.writerow(
                [
                    item.state,
                    item.year_ago_month,
                    item.first_print_issue,
                    item.year_ago_issue,
                    item.year_ago_cell,
                    f"{item.difference:.2f}",
                    item.year_ago_class,
                    item.year_ago_class_refined,
                ]
            )


def command_checks(root: Path) -> int:
    frame = pd.read_parquet(root / OUTPUT_DIRECTORY / FIRST_PRINT_FILE)
    current = _frozen_prices(root)
    if current["reference_month"].max() > LAST_REFERENCE_MONTH:
        raise FetchError("A frozen-extract row after the window was read.")
    releases = annual_final_releases(root, _verified_sources(root))
    pairs = classify_year_ago(frame, current, releases)
    payload = {
        "year_ago": year_ago_check(frame),
        "year_ago_versus_current": year_ago_versus_current(frame, current),
        "annual_final_releases": {str(year): releases[year] for year in sorted(releases)},
        "year_ago_classes": year_ago_class_summary(pairs),
        "revised_preliminary_test": revised_preliminary_test(pairs, releases),
        "revisions": revision_statistics(frame, current),
        "md_outliers": outlier_report(frame, current),
    }
    _write_json(root / OUTPUT_DIRECTORY / CHECKS_FILE, payload)
    write_year_ago_differences(root / YEAR_AGO_FILE, pairs)
    summary = {key: value for key, value in payload["year_ago"].items() if key != "mismatches"}
    print(json.dumps({**payload, "year_ago": summary}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["fetch", "build", "timing", "checks"])
    arguments = parser.parse_args(argv)
    root = repository_root()
    commands = {"fetch": command_fetch, "build": command_build, "timing": command_timing, "checks": command_checks}
    try:
        return commands[arguments.command](root)
    except FetchError as exc:
        print(f"eia_first_print: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

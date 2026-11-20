"""Provenance and lineage manifest checks (Version 2 Phase 2, criterion 1).

Every test here always runs and never skips. Gitignored data files that are
not on this machine are listed in the test output (``pytest -rP``) instead of
producing a skip, so the clean-clone skip count is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from infralens.data import repository_root
from infralens.data.eia_normalize import normalize_retail_sales
from infralens.demo.foundation import FROZEN_EXTRACT_ID, default_artifact_paths
from infralens.screening.pjm_sources import TABLE_B1_SOURCES

_ROOT = repository_root()
_MANIFEST_PATH = _ROOT / "data" / "manifest.json"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_UTC_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")

_RAW_KEYS = {
    "id",
    "path",
    "filename",
    "source_url",
    "source_request",
    "publisher",
    "retrieved_at",
    "retrieval_receipt",
    "observed_local_time",
    "publication",
    "sha256",
    "size_bytes",
    "licensing_note",
    "git_status",
}
_DERIVED_KEYS = {"id", "path", "filename", "producer", "inputs", "output", "feeds", "git_status"}
_RETRIEVAL_STATUSES = {"recorded", "unrecorded", "not_applicable"}
_PUBLICATION_STATUSES = {"verified", "unverified", "not_applicable"}
_COMMIT_STATUSES = {"recorded", "unrecorded"}
_FINGERPRINT_STATUSES = {"recorded_at_production", "computed_after_production"}
_GIT_STATUSES = {"tracked", "gitignored"}


def _manifest() -> dict:
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def _entries(manifest: dict) -> list[dict]:
    return [*manifest["raw_sources"], *manifest["derived_artifacts"]]


def _fingerprint(entry: dict) -> tuple[str, int]:
    if "output" in entry:
        return entry["output"]["sha256"], entry["output"]["size_bytes"]
    return entry["sha256"], entry["size_bytes"]


def _require_utc(value: str, label: str) -> None:
    assert isinstance(value, str) and _UTC_STAMP.match(value), f"{label} is not a UTC timestamp ending in Z: {value!r}"
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def _require_text(value: object, label: str) -> None:
    assert isinstance(value, str) and value.strip(), f"{label} must be non-empty text"


def _require_relative_path(path: str, label: str) -> None:
    assert isinstance(path, str) and path, label
    assert not path.startswith("/") and ".." not in Path(path).parts, f"{label} must be repository-relative: {path}"


def test_manifest_schema_and_provenance_rules() -> None:
    manifest = _manifest()
    assert manifest["manifest_version"] == 1
    assert manifest["fingerprint_algorithm"] == "sha256"
    assert manifest["raw_sources"] and manifest["derived_artifacts"]

    entries = _entries(manifest)
    ids = [entry["id"] for entry in entries]
    paths = [entry["path"] for entry in entries]
    assert len(ids) == len(set(ids)), "manifest ids must be unique"
    assert len(paths) == len(set(paths)), "manifest paths must be unique"

    for raw in manifest["raw_sources"]:
        label = raw.get("id", "<raw entry>")
        assert set(raw) == _RAW_KEYS, f"{label} keys differ: {sorted(set(raw) ^ _RAW_KEYS)}"
        _require_relative_path(raw["path"], f"{label} path")
        assert raw["filename"] == Path(raw["path"]).name
        assert _SHA256.match(raw["sha256"]), f"{label} sha256"
        assert isinstance(raw["size_bytes"], int) and raw["size_bytes"] > 0
        assert raw["git_status"] in _GIT_STATUSES
        _require_text(raw["publisher"], f"{label} publisher")
        _require_text(raw["licensing_note"], f"{label} licensing_note")

        retrieved = raw["retrieved_at"]
        assert set(retrieved) == {"value", "status", "evidence"}
        assert retrieved["status"] in _RETRIEVAL_STATUSES
        _require_text(retrieved["evidence"], f"{label} retrieved_at evidence")
        if retrieved["status"] == "recorded":
            _require_utc(retrieved["value"], f"{label} retrieved_at")
        else:
            # Never infer a retrieval time: only a recorded one may fill the value.
            assert retrieved["value"] is None, f"{label} has a retrieved_at value without a recorded time"

        if retrieved["status"] == "not_applicable":
            assert raw["source_url"] is None
        else:
            assert isinstance(raw["source_url"], str) and raw["source_url"].startswith("https://")

        receipt = raw["retrieval_receipt"]
        if receipt is not None:
            assert retrieved["status"] == "recorded"
            _require_utc(receipt["started_at"], f"{label} receipt started_at")
            _require_utc(receipt["completed_at"], f"{label} receipt completed_at")
            assert receipt["completed_at"] == retrieved["value"]
            assert receipt["started_at"] <= receipt["completed_at"]
            assert receipt["http_status"] == 200
            assert receipt["content_length"] == raw["size_bytes"]
            assert receipt["sha256_matches_stored_file"] is True
            assert receipt["copy_retained"] is False

        observed = raw["observed_local_time"]
        if observed is not None:
            assert set(observed) == {"value", "kind", "observed_on", "note"}
            _require_utc(observed["value"], f"{label} observed_local_time")
            date.fromisoformat(observed["observed_on"])
            assert "evidence only" in observed["note"].lower()
            assert observed["value"] != retrieved["value"], f"{label} uses a file-system time as retrieved_at"

        publication = raw["publication"]
        assert set(publication) == {"original_release_date", "revision_date", "status", "evidence"}
        assert publication["status"] in _PUBLICATION_STATUSES
        assert publication["evidence"] and all(isinstance(item, str) and item for item in publication["evidence"])
        if publication["status"] == "verified":
            date.fromisoformat(publication["original_release_date"])
            if publication["revision_date"] is not None:
                assert date.fromisoformat(publication["revision_date"]) >= date.fromisoformat(
                    publication["original_release_date"]
                )
        else:
            assert publication["original_release_date"] is None and publication["revision_date"] is None

    fingerprints = {entry["id"]: _fingerprint(entry) for entry in entries}
    for derived in manifest["derived_artifacts"]:
        label = derived.get("id", "<derived entry>")
        assert set(derived) == _DERIVED_KEYS, f"{label} keys differ: {sorted(set(derived) ^ _DERIVED_KEYS)}"
        _require_relative_path(derived["path"], f"{label} path")
        assert derived["filename"] == Path(derived["path"]).name
        assert derived["git_status"] in _GIT_STATUSES
        assert derived["feeds"] and all(isinstance(item, str) and item for item in derived["feeds"])

        producer = derived["producer"]
        assert set(producer) == {"script", "function", "git_commit", "git_commit_status", "evidence"}
        script = _ROOT / producer["script"]
        assert script.is_file(), f"{label} producer script is missing: {producer['script']}"
        assert re.search(rf"^def {re.escape(producer['function'])}\(", script.read_text(encoding="utf-8"), re.M), (
            f"{label} producer function {producer['function']} is not defined in {producer['script']}"
        )
        assert producer["git_commit_status"] in _COMMIT_STATUSES
        _require_text(producer["evidence"], f"{label} producer evidence")
        if producer["git_commit_status"] == "recorded":
            assert _COMMIT.match(producer["git_commit"]), f"{label} git_commit"
        else:
            assert producer["git_commit"] is None

        assert derived["inputs"], f"{label} needs at least one input"
        for item in derived["inputs"]:
            assert set(item) == {"id", "sha256", "fingerprint_status", "note"}
            assert item["id"] in fingerprints, f"{label} input {item['id']} is not in the manifest"
            assert item["id"] != derived["id"]
            assert item["fingerprint_status"] in _FINGERPRINT_STATUSES
            assert item["sha256"] == fingerprints[item["id"]][0], f"{label} input {item['id']} fingerprint differs"

        assert _SHA256.match(derived["output"]["sha256"])
        assert isinstance(derived["output"]["size_bytes"], int) and derived["output"]["size_bytes"] > 0


def test_manifest_matches_code_and_committed_evidence() -> None:
    manifest = _manifest()
    by_path = {entry["path"]: entry for entry in _entries(manifest)}

    paths = default_artifact_paths(_ROOT)
    for path in (
        paths.price_history,
        paths.holdout_cases,
        paths.pjm_2025_tables,
        paths.pjm_2026_tables,
        paths.committed_summary,
    ):
        assert path.relative_to(_ROOT).as_posix() in by_path, f"{path} is read by the app but not in the manifest"
    assert by_path[f"data/interim/{FROZEN_EXTRACT_ID}"]["filename"] == FROZEN_EXTRACT_ID

    for source in TABLE_B1_SOURCES:
        entry = by_path[f"data/raw/pjm/{source.source_file}"]
        assert entry["source_url"] == source.source_url
        publication = entry["publication"]
        assert publication["original_release_date"] == source.original_release_date.isoformat()
        expected_revision = None if source.revision_date is None else source.revision_date.isoformat()
        assert publication["revision_date"] == expected_revision
        assert (publication["revision_date"] or publication["original_release_date"]) == (
            source.vintage_available_at.isoformat()
        )

    committed = by_path["docs/final_eia_holdout_oneshot.json"]
    pinned = re.search(
        r'PINNED_SUMMARY_SHA256\s*=\s*"([0-9a-f]{64})"',
        (_ROOT / "deploy" / "ci_portable_image.py").read_text(encoding="utf-8"),
    )
    assert pinned is not None
    assert committed["output"]["sha256"] == pinned.group(1)

    document = json.loads((_ROOT / "docs" / "final_eia_holdout_oneshot.json").read_text(encoding="utf-8"))
    summary = document["summary"]
    for holdout_path in (
        "data/processed/final_holdout/final_holdout_cases.parquet",
        "data/processed/final_holdout/final_holdout_summary.json",
        "docs/final_eia_holdout_oneshot.json",
    ):
        assert by_path[holdout_path]["producer"]["git_commit"] == summary["git_commit"] == document["runner_commit"]
    assert summary["extract_id"] == FROZEN_EXTRACT_ID

    interim = by_path[f"data/interim/{FROZEN_EXTRACT_ID}"]
    raw_ids = {item["id"] for item in interim["inputs"]}
    raw = next(entry for entry in manifest["raw_sources"] if entry["id"] in raw_ids)
    stamp = FROZEN_EXTRACT_ID.removeprefix("eia_retail_sales_monthly_com_").removesuffix(".parquet")
    assert raw["filename"] == f"retail_sales_monthly_com_{stamp}.json"
    recorded = datetime.fromisoformat(raw["retrieved_at"]["value"].replace("Z", "+00:00"))
    assert recorded.strftime("%Y%m%dT%H%M%SZ") == stamp


def test_listed_files_match_manifest_fingerprints() -> None:
    manifest = _manifest()
    checked: list[str] = []
    absent: list[str] = []
    for entry in _entries(manifest):
        path = _ROOT / entry["path"]
        if not path.is_file():
            assert entry["git_status"] == "gitignored", f"tracked file {entry['path']} is missing"
            absent.append(entry["path"])
            continue
        data = path.read_bytes()
        expected_sha, expected_size = _fingerprint(entry)
        assert len(data) == expected_size, f"{entry['path']} size {len(data)} != manifest {expected_size}"
        assert hashlib.sha256(data).hexdigest() == expected_sha, f"{entry['path']} SHA-256 differs from the manifest"
        checked.append(entry["path"])

    assert "tests/fixtures/eia_retail_sales_sample.json" in checked
    assert "docs/final_eia_holdout_oneshot.json" in checked
    print(f"data manifest: verified {len(checked)} file(s): {', '.join(checked)}")
    if absent:
        print(f"data manifest: not on this machine (gitignored, not verified): {', '.join(absent)}")
    else:
        print("data manifest: every listed file is present and verified")


def test_eia_interim_parquet_rederives_from_raw_when_present() -> None:
    manifest = _manifest()
    interim = next(e for e in manifest["derived_artifacts"] if e["filename"] == FROZEN_EXTRACT_ID)
    raw = next(e for e in manifest["raw_sources"] if e["id"] == interim["inputs"][0]["id"])
    raw_path = _ROOT / raw["path"]
    interim_path = _ROOT / interim["path"]
    missing = [p.relative_to(_ROOT).as_posix() for p in (raw_path, interim_path) if not p.is_file()]
    if missing:
        print(f"EIA lineage check: not run, missing {', '.join(missing)}")
        return

    bundle = json.loads(raw_path.read_text(encoding="utf-8"))
    rebuilt, _ = normalize_retail_sales(
        bundle["pages"],
        retrieved_at=datetime.fromisoformat(bundle["retrieved_at"]),
        expected_states=tuple(bundle["states"]),
        require_all_expected_states=True,
    )
    stored = pd.read_parquet(interim_path)
    # Columns added to the normalizer after the extract was written are not part of the stored artifact.
    assert set(stored.columns) <= set(rebuilt.columns)
    pd.testing.assert_frame_equal(
        rebuilt[list(stored.columns)].reset_index(drop=True),
        stored.reset_index(drop=True),
        check_dtype=False,
    )
    print(f"EIA lineage check: {interim['path']} equals the normalization of {raw['path']} on {len(stored.columns)} columns")

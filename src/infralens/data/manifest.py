"""Read ``data/manifest.json``, the provenance and lineage manifest.

This module only reads the committed manifest. It never writes it, never
downloads a file, and never fills in a time that the manifest does not record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infralens.data import repository_root

RECORDED = "recorded"


class ManifestError(ValueError):
    """The manifest is missing, unreadable, or has no usable entry."""


class ManifestFileMismatch(ManifestError):
    """A local file's SHA-256 or size differs from its manifest entry."""


@dataclass(frozen=True)
class RecordedRetrieval:
    """A retrieval time recorded at download time for one raw source file."""

    filename: str
    retrieved_at: datetime
    evidence: str
    byte_identical_recheck: bool


def default_manifest_path(root: Path | None = None) -> Path:
    return (root or repository_root()) / "data" / "manifest.json"


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError("The data manifest is missing or unreadable.") from exc
    if not isinstance(document, dict) or not isinstance(document.get("raw_sources"), list):
        raise ManifestError("The data manifest has no raw_sources list.")
    return document


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def recorded_retrieval(manifest_path: Path, local_file: Path) -> RecordedRetrieval:
    """Return the recorded retrieval time for ``local_file``.

    The file must be listed under ``raw_sources`` by its path relative to the
    manifest's repository root, its SHA-256 and size must match, and the
    entry's ``retrieved_at.status`` must be ``recorded``. Anything else raises.
    """

    manifest = load_manifest(manifest_path)
    root = manifest_path.resolve().parent.parent
    try:
        relative = local_file.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ManifestError(f"{local_file.name} is not under the manifest's root.") from exc
    entries = [entry for entry in manifest["raw_sources"] if isinstance(entry, dict) and entry.get("path") == relative]
    if len(entries) != 1:
        raise ManifestError(f"{local_file.name} has no single entry in the data manifest.")
    entry = entries[0]

    expected_sha = entry.get("sha256")
    expected_size = entry.get("size_bytes")
    if not isinstance(expected_sha, str) or not isinstance(expected_size, int):
        raise ManifestError(f"{local_file.name} has no fingerprint in the data manifest.")
    if local_file.stat().st_size != expected_size or sha256_file(local_file) != expected_sha:
        raise ManifestFileMismatch(f"{local_file.name} does not match its data manifest fingerprint.")

    retrieved = entry.get("retrieved_at")
    if not isinstance(retrieved, dict) or retrieved.get("status") != RECORDED:
        raise ManifestError(f"{local_file.name} has no recorded retrieval time.")
    value = retrieved.get("value")
    evidence = retrieved.get("evidence")
    if not isinstance(value, str) or not value.endswith("Z") or not isinstance(evidence, str) or not evidence:
        raise ManifestError(f"{local_file.name} has an incomplete retrieval record.")
    try:
        stamp = datetime.fromisoformat(value.removesuffix("Z") + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise ManifestError(f"{local_file.name} has an unreadable retrieval time.") from exc

    receipt = entry.get("retrieval_receipt")
    recheck = isinstance(receipt, dict) and receipt.get("sha256_matches_stored_file") is True
    return RecordedRetrieval(
        filename=local_file.name,
        retrieved_at=stamp,
        evidence=evidence,
        byte_identical_recheck=recheck,
    )

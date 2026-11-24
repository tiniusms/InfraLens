"""Check the data-distribution policy (Version 2 Phase 2, criterion 4).

Standard library only. CI runs ``check-skips`` on the pytest JUnit report. The
other functions are used by ``tests/test_data_distribution_policy.py``.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
VALID_CLASSES = {"committed", "reproducibly_fetched", "local_only", "unavailable"}
MAX_SKIPS = 14
CACHE_DIRECTORIES = ("data/raw/", "data/interim/", "data/processed/")
BLOCKED_SUFFIXES = (".parquet", ".xlsx")
HELPER = "skip_missing_cache"
# Never collected by the regression suite, and not edited by this policy.
UNSCANNED = {"tests/test_final_holdout.py", "tests/data_cache_skips.py"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy(root: Path = ROOT) -> dict:
    return load_json(root / "data" / "distribution_policy.json")


def load_manifest(root: Path = ROOT) -> dict:
    return load_json(root / "data" / "manifest.json")


def manifest_entries(manifest: dict) -> list[dict]:
    return [*manifest["raw_sources"], *manifest["derived_artifacts"]]


def class_violations(manifest: dict, policy: dict) -> list[str]:
    ids = {entry["id"] for entry in manifest_entries(manifest)}
    classes = policy["classes"]
    problems = [f"{item} has no distribution class" for item in sorted(ids - set(classes))]
    problems += [f"{item} is not in the manifest" for item in sorted(set(classes) - ids)]
    problems += [
        f"{item} has invalid class {value!r}" for item, value in sorted(classes.items()) if value not in VALID_CLASSES
    ]
    return problems


def local_only_paths(manifest: dict, policy: dict) -> list[str]:
    listed = {
        entry["path"] for entry in manifest_entries(manifest) if policy["classes"].get(entry["id"]) == "local_only"
    }
    return sorted(listed | set(policy["cache_paths"]))


def tracked_files(root: Path = ROOT) -> list[str]:
    """Tracked paths. A git failure raises, so the check cannot pass silently."""

    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True)
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def tracked_violations(tracked: list[str], manifest: dict, policy: dict) -> list[str]:
    present = set(tracked)
    problems = [f"local-only file is tracked: {path}" for path in local_only_paths(manifest, policy) if path in present]
    for entry in manifest_entries(manifest):
        if policy["classes"].get(entry["id"]) == "committed" and entry["path"] not in present:
            problems.append(f"committed file is not tracked: {entry['path']}")
    for path in sorted(present):
        name = PurePosixPath(path).name
        if path.startswith(CACHE_DIRECTORIES) and name != ".gitkeep":
            problems.append(f"file is tracked under a cache directory: {path}")
        elif path.endswith(BLOCKED_SUFFIXES):
            problems.append(f"data file type is tracked: {path}")
    return list(dict.fromkeys(problems))


def ignore_violations(root: Path, paths: list[str]) -> list[str]:
    """Paths .gitignore no longer covers. Any git error raises."""

    problems = []
    for path in paths:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", "--", path], cwd=root, capture_output=True
        )
        if result.returncode == 1:
            problems.append(f".gitignore does not cover: {path}")
        elif result.returncode != 0:
            raise RuntimeError(f"git check-ignore failed for {path}: {result.stderr.decode('utf-8', 'replace')}")
    return problems


def source_skip_violations(sources: dict[str, str], policy: dict) -> list[str]:
    """Every skip must be one helper call in an allowlisted test, with its cache."""

    problems: list[str] = []
    found: dict[str, str] = {}
    for relative, text in sorted(sources.items()):
        if relative in UNSCANNED:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                base = node.value
                if isinstance(base, ast.Name) and base.id == "pytest" and node.attr in {"skip", "xfail", "importorskip"}:
                    problems.append(f"{relative}:{node.lineno} uses pytest.{node.attr}")
                if isinstance(base, ast.Attribute) and base.attr == "mark" and node.attr in {"skip", "skipif", "xfail"}:
                    problems.append(f"{relative}:{node.lineno} uses a {node.attr} marker")
        inside: set[int] = set()
        for function in tree.body:
            if not isinstance(function, ast.FunctionDef):
                continue
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == HELPER:
                    inside.add(id(node))
                    key = f"{relative}::{function.name}"
                    argument = node.args[0] if node.args else None
                    if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                        problems.append(f"{key} must name its cache as a string")
                    elif key in found:
                        problems.append(f"{key} calls {HELPER} more than once")
                    else:
                        found[key] = argument.value
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == HELPER
                and id(node) not in inside
            ):
                problems.append(f"{relative}:{node.lineno} calls {HELPER} outside a test")
    allowed = policy["allowed_skips"]
    problems += [f"skip is not on the allowlist: {key}" for key in sorted(set(found) - set(allowed))]
    problems += [f"allowlisted skip has no helper call: {key}" for key in sorted(set(allowed) - set(found))]
    problems += [
        f"{key} uses cache {value!r}, allowlist says {allowed[key]!r}"
        for key, value in sorted(found.items())
        if key in allowed and value != allowed[key]
    ]
    return problems


def junit_skips(path: Path) -> list[tuple[str, str]]:
    skips = []
    for case in ET.parse(path).getroot().iter("testcase"):
        skipped = case.find("skipped")
        if skipped is not None:
            module = case.attrib.get("classname", "").replace(".", "/")
            skips.append((f"{module}.py::{case.attrib.get('name', '')}", skipped.attrib.get("message", "")))
    return skips


def skip_violations(skips: list[tuple[str, str]], policy: dict) -> list[str]:
    """CI has no caches, so the skipped tests must be exactly the allowlist."""

    allowed = policy["allowed_skips"]
    reasons = policy["skip_reasons"]
    problems = []
    if len(skips) > MAX_SKIPS:
        problems.append(f"{len(skips)} skips exceed the limit of {MAX_SKIPS}")
    seen = set()
    for node, message in skips:
        seen.add(node)
        if node not in allowed:
            problems.append(f"skip is not on the allowlist: {node} ({message})")
        elif message != reasons[allowed[node]]:
            problems.append(f"{node} skipped with an unexpected reason: {message}")
    problems += [f"allowlisted test did not skip: {node}" for node in sorted(set(allowed) - seen)]
    return problems


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 2 or arguments[0] != "check-skips":
        print("usage: python scripts/data_policy.py check-skips <pytest-junit.xml>", file=sys.stderr)
        return 2
    skips = junit_skips(Path(arguments[1]))
    problems = skip_violations(skips, load_policy())
    for problem in problems:
        print(f"data policy: {problem}", file=sys.stderr)
    if problems:
        return 1
    print(f"data policy: {len(skips)} skips, all on the named missing-cache allowlist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

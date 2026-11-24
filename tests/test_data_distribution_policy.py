"""Machine-enforced data-distribution policy (Version 2 Phase 2, criterion 4).

These tests never skip. They read committed files and git's index only.
"""

from __future__ import annotations

import copy
import importlib.util
import subprocess
from pathlib import Path

import pytest

from infralens.data import repository_root

_ROOT = repository_root()
_spec = importlib.util.spec_from_file_location("data_policy", _ROOT / "scripts" / "data_policy.py")
assert _spec is not None and _spec.loader is not None
policy_tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policy_tools)


def _test_sources() -> dict[str, str]:
    return {
        path.relative_to(_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((_ROOT / "tests").glob("*.py"))
    }


def _ci_skips(policy: dict) -> list[tuple[str, str]]:
    return [(node, policy["skip_reasons"][cache]) for node, cache in policy["allowed_skips"].items()]


def test_every_manifest_entry_has_a_valid_class() -> None:
    manifest, policy = policy_tools.load_manifest(), policy_tools.load_policy()
    assert policy_tools.class_violations(manifest, policy) == []
    assert set(policy["cache_paths"]) <= set(policy_tools.local_only_paths(manifest, policy))
    assert len(policy["classes"]) == 8


def test_no_local_only_file_is_tracked() -> None:
    manifest, policy = policy_tools.load_manifest(), policy_tools.load_policy()
    assert policy_tools.tracked_violations(policy_tools.tracked_files(_ROOT), manifest, policy) == []


def test_gitignore_covers_every_local_only_path() -> None:
    manifest, policy = policy_tools.load_manifest(), policy_tools.load_policy()
    paths = policy_tools.local_only_paths(manifest, policy)
    assert len(paths) == 6
    assert policy_tools.ignore_violations(_ROOT, paths) == []


def test_every_skip_call_matches_the_named_allowlist() -> None:
    policy = policy_tools.load_policy()
    assert policy_tools.source_skip_violations(_test_sources(), policy) == []
    counts = {cache: list(policy["allowed_skips"].values()).count(cache) for cache in policy["skip_reasons"]}
    assert counts == {"eia_history": 2, "holdout_cases": 3, "pjm_workbooks": 9}


def test_ci_enforces_the_skip_policy_after_the_locked_install() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    install = "python -m pip install --require-hashes --no-deps --only-binary :all: -r requirements-lock.txt"
    run = "--ignore=tests/test_final_holdout.py -rs --junitxml=pytest-results.xml"
    check = "python scripts/data_policy.py check-skips pytest-results.xml"
    assert workflow.index(install) < workflow.index(run) < workflow.index(check)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("data/raw/pjm/2026-load-report-tables.xlsx", "local-only file is tracked"),
        ("data/processed/final_holdout/final_holdout_summary.json", "local-only file is tracked"),
        ("data/raw/eia/other_pull.json", "tracked under a cache directory"),
        ("tests/fixtures/excerpt.parquet", "data file type is tracked"),
        ("docs/excerpt.xlsx", "data file type is tracked"),
    ],
)
def test_tracking_a_blocked_path_is_reported(path: str, expected: str) -> None:
    manifest, policy = policy_tools.load_manifest(), policy_tools.load_policy()
    tracked = [*policy_tools.tracked_files(_ROOT), path]
    assert any(expected in item for item in policy_tools.tracked_violations(tracked, manifest, policy))


def test_a_missing_committed_file_is_reported() -> None:
    manifest, policy = policy_tools.load_manifest(), policy_tools.load_policy()
    tracked = [item for item in policy_tools.tracked_files(_ROOT) if item != "docs/final_eia_holdout_oneshot.json"]
    assert any("committed file is not tracked" in item for item in policy_tools.tracked_violations(tracked, manifest, policy))


def test_missing_or_invalid_classes_are_reported() -> None:
    manifest, policy = policy_tools.load_manifest(), policy_tools.load_policy()
    missing = copy.deepcopy(policy)
    del missing["classes"]["final_holdout_cases"]
    invalid = copy.deepcopy(policy)
    invalid["classes"]["final_holdout_cases"] = "public"
    assert any("no distribution class" in item for item in policy_tools.class_violations(manifest, missing))
    assert any("invalid class" in item for item in policy_tools.class_violations(manifest, invalid))


def test_git_failures_and_lost_ignore_rules_do_not_pass(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        policy_tools.tracked_files(tmp_path)
    with pytest.raises(RuntimeError):
        policy_tools.ignore_violations(tmp_path, ["data/raw/pjm/2026-load-report-tables.xlsx"])
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    problems = policy_tools.ignore_violations(tmp_path, ["data/raw/pjm/2026-load-report-tables.xlsx"])
    assert problems == [".gitignore does not cover: data/raw/pjm/2026-load-report-tables.xlsx"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import pytest\ndef test_x():\n    pytest.skip('no')\n", "uses pytest.skip"),
        ("import pytest\n@pytest.mark.skipif(True, reason='no')\ndef test_x():\n    pass\n", "skipif marker"),
        ("import pytest\n@pytest.mark.xfail\ndef test_x():\n    pass\n", "xfail marker"),
        ("def test_x():\n    skip_missing_cache('eia_history')\n", "not on the allowlist"),
    ],
)
def test_unapproved_skip_in_source_is_reported(source: str, expected: str) -> None:
    policy = policy_tools.load_policy()
    sources = {**_test_sources(), "tests/test_new.py": source}
    assert any(expected in item for item in policy_tools.source_skip_violations(sources, policy))


def test_a_skip_with_the_wrong_cache_is_reported() -> None:
    policy = copy.deepcopy(policy_tools.load_policy())
    node = "tests/test_pjm_view.py::test_official_aep_2026_view_matches_workbook_columns"
    policy["allowed_skips"][node] = "eia_history"
    assert any("allowlist says" in item for item in policy_tools.source_skip_violations(_test_sources(), policy))


def test_ci_skip_check_accepts_only_the_exact_allowlist() -> None:
    policy = policy_tools.load_policy()
    good = _ci_skips(policy)
    assert policy_tools.skip_violations(good, policy) == []
    extra = [*good, ("tests/test_new.py::test_x", "no reason")]
    assert any("exceed the limit" in item for item in policy_tools.skip_violations(extra, policy))
    assert any("not on the allowlist" in item for item in policy_tools.skip_violations(extra, policy))
    changed = [(good[0][0], "some other reason"), *good[1:]]
    assert any("unexpected reason" in item for item in policy_tools.skip_violations(changed, policy))
    assert any("did not skip" in item for item in policy_tools.skip_violations(good[1:], policy))


def test_ci_skip_command_reads_junit_and_sets_its_exit_code(tmp_path: Path) -> None:
    policy = policy_tools.load_policy()
    cases = "".join(
        f'<testcase classname="{node.split("::")[0].removesuffix(".py").replace("/", ".")}" '
        f'name="{node.split("::")[1]}"><skipped type="pytest.skip" message="{reason}" /></testcase>'
        for node, reason in _ci_skips(policy)
    )
    good = tmp_path / "good.xml"
    good.write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>", encoding="utf-8")
    bad = tmp_path / "bad.xml"
    bad.write_text("<testsuites><testsuite /></testsuites>", encoding="utf-8")
    assert policy_tools.main(["check-skips", str(good)]) == 0
    assert policy_tools.main(["check-skips", str(bad)]) == 1
    assert policy_tools.main([]) == 2

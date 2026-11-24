"""Checks on the locked Python environment (Version 2 Phase 2, criterion 3).

These read committed files only. They never skip, install, or use the network.
"""

from __future__ import annotations

import re
import tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from infralens.data import repository_root

_ROOT = repository_root()
_LOCK = _ROOT / "requirements-lock.txt"
_INSTALL = (
    "python -m pip install --require-hashes --no-deps --only-binary :all: -r requirements-lock.txt",
    "python -m pip install --no-deps --no-build-isolation -e .",
    "python -m pip check",
)
_DARWIN = {"sys_platform": "darwin", "platform_system": "Darwin", "os_name": "posix", "platform_machine": "arm64"}
_LINUX = {"sys_platform": "linux", "platform_system": "Linux", "os_name": "posix", "platform_machine": "x86_64"}


def _locked() -> dict[str, tuple[Requirement, list[str]]]:
    text = re.sub(r"\\\n\s*", " ", _LOCK.read_text(encoding="utf-8"))
    entries: dict[str, tuple[Requirement, list[str]]] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        spec, *hashes = re.split(r"\s+--hash=", line.strip())
        requirement = Requirement(spec)
        name = canonicalize_name(requirement.name)
        assert name not in entries, f"{name} is locked twice"
        entries[name] = (requirement, hashes)
    return entries


def _version(requirement: Requirement) -> str:
    specifiers = list(requirement.specifier)
    assert len(specifiers) == 1 and specifiers[0].operator == "==", f"{requirement} is not an exact pin"
    return specifiers[0].version


def test_every_locked_package_is_pinned_with_sha256_hashes() -> None:
    locked = _locked()
    assert locked
    for name, (requirement, hashes) in locked.items():
        _version(requirement)
        assert requirement.url is None, name
        assert hashes, f"{name} has no hash"
        assert all(re.fullmatch(r"sha256:[0-9a-f]{64}", item) for item in hashes), name


def test_lock_covers_declared_dependencies_and_build_tools() -> None:
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = list(project["project"]["dependencies"])
    for extra in ("dev", "demo", "api"):
        declared.extend(project["project"]["optional-dependencies"][extra])
    declared.extend(project["build-system"]["requires"])
    locked = _locked()
    for item in declared:
        requirement = Requirement(item)
        name = canonicalize_name(requirement.name)
        assert name in locked, f"{name} is declared but not locked"
        assert Version(_version(locked[name][0])) in requirement.specifier, item
    for line in (_ROOT / "requirements-lock.in").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            tool = Requirement(line)
            assert _version(locked[canonicalize_name(tool.name)][0]) == _version(tool), line


def test_api_pins_equal_the_lock() -> None:
    locked = _locked()
    pins = [
        line
        for line in (_ROOT / "requirements-api.txt").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert len(pins) == 18
    for line in pins:
        name, version = line.split("==")
        assert _version(locked[canonicalize_name(name)][0]) == version, line


def test_platform_specific_packages_follow_their_markers() -> None:
    locked = _locked()
    appnope = locked["appnope"][0].marker
    watchdog = locked["watchdog"][0].marker
    assert appnope is not None and appnope.evaluate(_DARWIN) and not appnope.evaluate(_LINUX)
    assert watchdog is not None and watchdog.evaluate(_LINUX) and not watchdog.evaluate(_DARWIN)
    for name in ("colorama", "pywinpty"):
        marker = locked[name][0].marker
        assert marker is not None and not marker.evaluate(_DARWIN) and not marker.evaluate(_LINUX), name


def test_ci_and_readme_install_from_the_lock() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    for text in (workflow, readme):
        for command in _INSTALL:
            assert command in text, command
        assert "-c requirements-api.txt" not in text
        assert "pip install --upgrade pip" not in text

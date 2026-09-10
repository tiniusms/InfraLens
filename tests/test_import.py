"""Smoke test that the package is installable and importable."""

from infralens import __version__


def test_package_imports() -> None:
    assert __version__ == "0.1.0"

"""Deployment-package checks. They do not build an image or score the holdout."""

from __future__ import annotations

import fnmatch
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infralens.api.app import create_app
from infralens.data import repository_root

_ROOT = repository_root()
_DOCKERIGNORE = _ROOT / ".dockerignore"
_DOCKERFILE = _ROOT / "Dockerfile"
_PROHIBITED = (
    "data/interim/eia_retail_sales_monthly_com_20260911T190524Z.parquet",
    "data/processed/final_holdout/final_holdout_cases.parquet",
    "data/raw/pjm/2025-load-report-tables.xlsx",
    "data/raw/pjm/2026-load-report-tables.xlsx",
)
_INCLUDED = (
    "docs/final_eia_holdout_oneshot.json",
    "src/infralens/api/app.py",
    "requirements-api.txt",
    "deploy/start_api.sh",
    "README.md",
)
_COPY_SOURCES = (
    "requirements-api.txt",
    "pyproject.toml",
    "README.md",
    "src",
    "docs/final_eia_holdout_oneshot.json",
    "deploy/start_api.sh",
)


def _rules() -> list[str]:
    return [
        line.strip()
        for line in _DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _ignored(relative: str) -> bool:
    """Last matching dockerignore rule wins. Patterns have no directory slash."""

    ignored = False
    parts = relative.split("/")
    for rule in _rules():
        negate = rule.startswith("!")
        pattern = rule[1:] if negate else rule
        assert "/" not in pattern
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            ignored = not negate
    return ignored


def _portable_root(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "final_eia_holdout_oneshot.json"
    target.write_bytes((_ROOT / "docs" / "final_eia_holdout_oneshot.json").read_bytes())
    return tmp_path


def test_dockerignore_and_dockerfile_omit_local_artifacts() -> None:
    for path in _PROHIBITED:
        assert _ignored(path), path
    for path in _INCLUDED:
        assert not _ignored(path), path
    text = _DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY . " not in text
    assert "COPY ./" not in text
    for source in _COPY_SOURCES:
        assert source in text
    for path in _PROHIBITED:
        assert path not in text
        assert Path(path).name not in text or path.endswith(".json")
    assert "python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c" in text
    assert "--no-deps" in text
    assert "USER infralens" in text


def test_start_script_binds_all_interfaces_and_ignores_proxy_headers() -> None:
    text = (_ROOT / "deploy" / "start_api.sh").read_text(encoding="utf-8")
    assert "--host 0.0.0.0" in text
    assert '--port "$port"' in text
    assert "--no-proxy-headers" in text
    assert "--limit-concurrency 16" in text
    assert "printenv" not in text
    assert "EIA_API_KEY" not in text


def test_frontend_rewrites_do_not_capture_api_paths() -> None:
    import json

    config = json.loads((_ROOT / "frontend" / "vercel.json").read_text(encoding="utf-8"))
    assert config["installCommand"] == "npm ci"
    assert config["buildCommand"] == "npm run build"
    assert config["outputDirectory"] == "dist"
    sources = [item["source"] for item in config["rewrites"]]
    assert sources == ["/electricity", "/finance", "/pjm"]
    assert all(not source.startswith("/api") for source in sources)
    blob = json.dumps(config)
    assert "EIA_API_KEY" not in blob
    assert "*" not in blob


def test_render_blueprint_is_manual_and_has_no_secret() -> None:
    text = (_ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "healthCheckPath: /api/v1/status" in text
    assert "runtime: docker" in text
    assert "autoDeploy: false" in text
    assert "EIA_API_KEY" not in text
    assert "INFRALENS_CORS_ORIGINS" in text
    assert "sync: false" in text


def test_requirements_pin_the_api_runtime_without_scientific_extras() -> None:
    pins = {}
    for line in (_ROOT / "requirements-api.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==")
        pins[name] = version
    assert pins["fastapi"] == "0.143.3"
    assert pins["uvicorn"] == "0.54.0"
    assert pins["starlette"] == "1.8.0"
    assert pins["pydantic"] == "2.14.1"
    assert pins["pandas"] == "3.0.5"
    assert "scikit-learn" not in pins
    assert "pyarrow" not in pins
    assert "duckdb" not in pins
    assert "httpx" not in pins


def test_packaged_files_have_no_local_paths_or_filled_secrets() -> None:
    files = [
        _DOCKERFILE,
        _DOCKERIGNORE,
        _ROOT / "render.yaml",
        _ROOT / "requirements-api.txt",
        _ROOT / "deploy" / "start_api.sh",
        _ROOT / "frontend" / "vercel.json",
        _ROOT / "docs" / "portable_deployment.md",
        _ROOT / ".env.example",
        _ROOT / "frontend" / ".env.example",
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "/Users/" not in text
        assert "sk-" not in text
        for line in text.splitlines():
            if line.startswith("EIA_API_KEY="):
                assert line.removeprefix("EIA_API_KEY=").strip() == ""


def test_unexpected_errors_do_not_log_the_exception_payload() -> None:
    source = (_ROOT / "src" / "infralens" / "api" / "errors.py").read_text(encoding="utf-8")
    assert "exc_info" not in source


def test_render_host_allowlist_accepts_platform_and_local_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "infralens-api.onrender.com")
    monkeypatch.delenv("INFRALENS_ALLOWED_HOSTS", raising=False)
    app = create_app(root=_portable_root(tmp_path), cors_origins=[])
    with TestClient(app, base_url="http://infralens-api.onrender.com") as client:
        allowed = client.get("/api/v1/status")
    assert allowed.status_code == 200
    assert allowed.json()["presence_mode"] == "portable_summary"
    with TestClient(app, base_url="http://localhost") as client:
        local = client.get("/api/v1/status")
    assert local.status_code == 200
    with TestClient(app, base_url="http://evil.example") as client:
        rejected = client.get("/api/v1/status")
    assert rejected.status_code == 400
    assert rejected.text == "Invalid host header"


def test_host_checks_stay_off_without_render_and_reject_a_wildcard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _portable_root(tmp_path)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
    monkeypatch.delenv("INFRALENS_ALLOWED_HOSTS", raising=False)
    app = create_app(root=root, cors_origins=[])
    with TestClient(app, base_url="http://evil.example") as client:
        open_local = client.get("/api/v1/status")
    assert open_local.status_code == 200

    monkeypatch.setenv("INFRALENS_ALLOWED_HOSTS", "*")
    with pytest.raises(ValueError, match="wildcard"):
        create_app(root=root, cors_origins=[])

    monkeypatch.delenv("INFRALENS_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
    with pytest.raises(ValueError, match="RENDER_EXTERNAL_HOSTNAME"):
        create_app(root=root, cors_origins=[])

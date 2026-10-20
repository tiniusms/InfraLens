"""Deployment-package checks. They do not build an image or score the holdout."""

from __future__ import annotations

import fnmatch
import time
from pathlib import Path

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infralens.api.app import create_app
from infralens.api.request_timeout import RequestTimeout
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
    checked = text.split("pip install --no-cache-dir --no-deps -r requirements-api.txt", 1)[1]
    assert checked.index("pip check") < checked.index("pip install --no-cache-dir --no-deps .")


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
    assert "type: pserv" in text
    assert "type: web" not in text
    assert "healthCheckPath" not in text
    assert "plan: 0.5c-512mb" in text
    assert "runtime: docker" in text
    assert "autoDeploy: false" in text
    assert "autoDeployTrigger: off" in text
    assert "dockerCommand: /app/deploy/start_private.sh" in text
    assert 'value: "10000"' in text
    assert "EIA_API_KEY" not in text
    assert "INFRALENS_CORS_ORIGINS" in text
    assert "INFRALENS_ALLOWED_HOSTS" in text
    assert "TUNNEL_TOKEN" in text
    assert text.count("sync: false") >= 3
    service = text.split("services:", 1)[1]
    assert "onrender.com" not in service
    assert "eyJ" not in text


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
    assert pins["opentelemetry-api"] == "1.45.1"
    assert "opentelemetry-sdk" not in pins
    assert "opentelemetry-exporter-otlp-proto-http" not in pins
    assert "scikit-learn" not in pins
    assert "pyarrow" not in pins
    assert "duckdb" not in pins
    assert "httpx" not in pins


def test_pinned_runtime_metadata_has_no_missing_requirement() -> None:
    """Each unconditional requirement of a pinned distribution is itself pinned."""

    import importlib.metadata as metadata
    from packaging.requirements import Requirement
    from packaging.version import Version

    pins: dict[str, str] = {}
    for line in (_ROOT / "requirements-api.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==")
        pins[name.lower().replace("_", "-")] = version
    for name, version in pins.items():
        dist = metadata.metadata(name)
        assert dist["Version"] == version
        for declared in dist.get_all("Requires-Dist") or []:
            requirement = Requirement(declared)
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            dependency = requirement.name.lower().replace("_", "-")
            assert dependency in pins, declared
            assert Version(pins[dependency]) in requirement.specifier, declared


def test_packaged_files_have_no_local_paths_or_filled_secrets() -> None:
    files = [
        _DOCKERFILE,
        _DOCKERIGNORE,
        _ROOT / "render.yaml",
        _ROOT / "requirements-api.txt",
        _ROOT / "deploy" / "start_api.sh",
        _ROOT / "deploy" / "start_private.sh",
        _ROOT / "deploy" / "supervise_private.py",
        _ROOT / "deploy" / "ci_private_image.py",
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


def _ci_module():
    import importlib.util

    path = _ROOT / "deploy" / "ci_portable_image.py"
    spec = importlib.util.spec_from_file_location("ci_portable_image", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_portable_image_workflow_is_local_and_read_only() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "portable-image.yml").read_text(encoding="utf-8")
    script = (_ROOT / "deploy" / "ci_portable_image.py").read_text(encoding="utf-8")
    private_script = (_ROOT / "deploy" / "ci_private_image.py").read_text(encoding="utf-8")
    assert "runs-on: ubuntu-latest" in workflow
    assert "timeout-minutes: 20" in workflow
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "persist-credentials: false" in workflow
    assert "docker build --pull --target portable -t infralens-api:ci ." in workflow
    assert "docker build --target private -t infralens-api:private ." in workflow
    assert "python3 deploy/ci_portable_image.py" in workflow
    assert "python3 deploy/ci_private_image.py" in workflow
    assert "if: always()" in workflow
    assert "docker rm -f infralens-api-ci" in workflow
    combined = "\n".join((workflow, script, private_script))
    for forbidden in (
        "docker push",
        "docker login",
        "${{ secrets",
        "final_holdout",
        "eia.gov",
        "pjm.com",
        "scikit-learn",
        "/Users/",
    ):
        assert forbidden not in combined
    assert "EIA_API_KEY=" not in workflow
    assert "10001:10001" in script
    assert "/app/deploy/start_api.sh" in script
    assert "portable_summary" in script
    assert "455520000" in script
    assert "54662400" in script
    assert "45552000" in script
    assert "-9110400" in script
    assert "request_too_large" in script
    assert "artifact_missing" in script


def test_image_checks_match_the_portable_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    import json

    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
    monkeypatch.delenv("INFRALENS_ALLOWED_HOSTS", raising=False)
    checker = _ci_module()
    digest = hashlib.sha256((_ROOT / "docs" / "final_eia_holdout_oneshot.json").read_bytes()).hexdigest()
    assert checker.PINNED_SUMMARY_SHA256 == digest
    app = create_app(root=_portable_root(tmp_path), cors_origins=[])
    with TestClient(app) as client:
        status = client.get("/api/v1/status")
        summary = client.get("/api/v1/evaluation/summary")
        finance = client.post("/api/v1/finance/scenarios", json=checker.finance_payload())
        history = client.get("/api/v1/eia/history")
        holdout = client.get("/api/v1/eia/holdout")
        cases = client.get("/api/v1/eia/holdout/cases")
        screen = client.get("/api/v1/pjm/screen", params={"pjm_zone": "AEP", "forecast_year": 2026, "as_of": "2026-02-06"})
        catalog = client.get("/api/v1/pjm/catalog")
        oversized = client.post("/api/v1/finance/scenarios", content=b"x" * 8193, headers={"content-type": "application/json"})
        three = checker.finance_payload()
        three["scenarios"] = [
            *three["scenarios"],
            {"name": "extra", "source": "typed_hypothetical", "price_cents_per_kwh": "11"},
        ]
        rejected = client.post("/api/v1/finance/scenarios", json=three)
    assert status.status_code == 200
    checker.check_status(status.json())
    assert summary.status_code == 200
    checker.check_evaluation(summary.json())
    assert finance.status_code == 200
    checker.check_finance(finance.json())
    checker.check_missing(history.status_code, history.json(), "price_history")
    checker.check_missing(holdout.status_code, holdout.json(), "holdout_cases")
    checker.check_missing(cases.status_code, cases.json(), "holdout_cases")
    checker.check_missing(screen.status_code, screen.json(), "pjm_2025_tables")
    assert catalog.status_code == 200
    checker.check_catalog(catalog.json())
    checker.check_too_large(oversized.status_code, oversized.json())
    checker.check_three_scenarios(rejected.status_code, json.loads(rejected.text))


def test_private_render_allowlist_accepts_the_tunnel_host_and_local_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
    monkeypatch.setenv("INFRALENS_ALLOWED_HOSTS", "api.example.com,")
    monkeypatch.delenv("INFRALENS_REQUEST_TIMEOUT_SECONDS", raising=False)
    root = _portable_root(tmp_path)
    app = create_app(root=root, cors_origins=[])
    for base in ("http://api.example.com", "http://localhost", "http://127.0.0.1"):
        with TestClient(app, base_url=base) as client:
            response = client.get("/api/v1/status")
        assert response.status_code == 200, base
        assert response.json()["presence_mode"] == "portable_summary"
    with TestClient(app, base_url="http://evil.example") as client:
        rejected = client.get("/api/v1/status")
    assert rejected.status_code == 400
    assert rejected.text == "Invalid host header"
    with pytest.raises(ValueError, match="Wildcard"):
        create_app(root=root, cors_origins=["*"])


@pytest.mark.parametrize(
    "raw",
    ["*", "*.example.com", "https://api.example.com", "api.example.com/status", "api example.com", ""],
)
def test_malformed_or_empty_host_entries_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
    monkeypatch.setenv("INFRALENS_ALLOWED_HOSTS", raw)
    with pytest.raises(ValueError, match="Allowed hosts|RENDER_EXTERNAL_HOSTNAME"):
        create_app(root=_portable_root(tmp_path), cors_origins=[])


def test_private_image_pin_is_separate_from_the_portable_target() -> None:
    text = _DOCKERFILE.read_text(encoding="utf-8")
    portable, private = text.split("FROM portable AS private", 1)
    assert "cloudflared-linux-amd64" not in portable
    assert "/usr/local/bin/cloudflared" not in portable
    assert "CMD [\"/app/deploy/start_api.sh\"]" in portable
    assert "2026.10.1" in private
    assert "3bfc539f45d2620c71debb7a86be0efa737ed5ccbad9eb85c787116900e5c586" in private
    assert "cloudflared-linux-amd64" in private
    assert "CMD [\"/app/deploy/start_private.sh\"]" in private
    assert "TUNNEL_TOKEN=" not in text
    standalone = (_ROOT / "deploy" / "start_api.sh").read_text(encoding="utf-8")
    assert "TUNNEL_TOKEN" not in standalone
    assert "cloudflared" not in standalone


def test_request_timeout_is_off_until_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("INFRALENS_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("INFRALENS_REQUEST_TIMEOUT_SECONDS", raising=False)
    root = _portable_root(tmp_path)
    plain = create_app(root=root, cors_origins=[])
    assert all(getattr(item, "cls", None) is not RequestTimeout for item in plain.user_middleware)
    monkeypatch.setenv("INFRALENS_REQUEST_TIMEOUT_SECONDS", "30")
    bounded = create_app(root=root, cors_origins=[])
    assert any(getattr(item, "cls", None) is RequestTimeout for item in bounded.user_middleware)
    with TestClient(bounded) as client:
        assert client.get("/api/v1/status").status_code == 200
    for raw in ("nope", "0", "-1", "121", "nan"):
        monkeypatch.setenv("INFRALENS_REQUEST_TIMEOUT_SECONDS", raw)
        with pytest.raises(ValueError, match="INFRALENS_REQUEST_TIMEOUT_SECONDS"):
            create_app(root=root, cors_origins=[])


def test_request_timeout_returns_504_and_is_not_keep_alive() -> None:
    app = FastAPI()

    @app.get("/slow")
    async def slow() -> dict[str, bool]:
        await anyio.sleep(2)
        return {"ok": True}

    app.add_middleware(RequestTimeout, seconds=0.05)
    started = time.monotonic()
    with TestClient(app) as client:
        response = client.get("/slow")
    elapsed = time.monotonic() - started
    assert response.status_code == 504
    assert response.json()["code"] == "request_timeout"
    assert elapsed < 1
    script = (_ROOT / "deploy" / "start_api.sh").read_text(encoding="utf-8")
    assert "--timeout-keep-alive 5" in script
    assert "request_timeout" not in script

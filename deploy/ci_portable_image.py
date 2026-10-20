"""Exercise the portable image on a Linux runner.

This file runs on the GitHub-hosted runner. It does not train, ingest, score,
or download EIA or PJM data. The pinned base image is the only network fetch,
and that fetch happens in the workflow's docker build step.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

IMAGE = "infralens-api:ci"
CONTAINER = "infralens-api-ci"
HOST = "127.0.0.1"
HOST_PORT = 8000
PINNED_SUMMARY_SHA256 = "5b116d9d0eaba5269f5afab71f60c826f4553174fb330e6e8fe80dfb6eba1393"
ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "docs" / "final_eia_holdout_oneshot.json"

STATE_MAE = {
    "MD": ("3.385474686685759", "3.608333333333333", 12),
    "NJ": ("2.726084766988411", "3.178333333333333", 12),
    "OH": ("2.3859318296585297", "2.1574999999999998", 12),
    "PA": ("2.344845390825365", "2.3425000000000007", 12),
    "VA": ("2.3500265777547478", "1.7816666666666672", 12),
}
GEOGRAPHIC_WARNING = (
    "PJM zones and US states are not interchangeable. Some zones cross state borders. "
    "This tab does not join a zone to an EIA state, allocate MW to a state, or rank locations."
)
LARGE_LOAD_WARNING = (
    "B-9 above-embedded MW and B-9b total-associated MW are separate forecast adjustment measures. "
    "Neither is isolated data-center MW, and neither is a verified realized load. "
    "They are not added together."
)
ZONES = (
    "AE",
    "BGE",
    "DPL",
    "JCPL",
    "METED",
    "PECO",
    "PENLC",
    "PEPCO",
    "PL",
    "PS",
    "RECO",
    "UGI",
    "AEP",
    "APS",
    "ATSI",
    "COMED",
    "DAYTON",
    "DEOK",
    "DLCO",
    "EKPC",
    "OVEC",
    "DOM",
)

_IMPORT_PROBE = r"""
import os
import sys
assert os.getuid() == 10001, os.getuid()
assert sys.version.startswith("3.12."), sys.version
for name in ("fastapi", "starlette", "uvicorn", "pydantic", "pandas", "numpy"):
    __import__(name)
print("imports-ok")
"""

_AUDIT_PROBE = r"""
import hashlib
import os
import sys
from pathlib import Path

summary = Path("/app/docs/final_eia_holdout_oneshot.json")
if not summary.is_file():
    raise SystemExit("missing committed summary")
print(hashlib.sha256(summary.read_bytes()).hexdigest())
hits = []
for directory in (Path("/app/frontend"), Path("/app/data"), Path("/app/node_modules"), Path("/app/dist")):
    if directory.exists():
        hits.append(str(directory))
skip = ("/proc", "/sys", "/dev")
secret_roots = ("/app", "/home", "/root", "/tmp")
for dirpath, dirnames, filenames in os.walk("/"):
    if dirpath.startswith(skip):
        dirnames.clear()
        continue
    for name in filenames:
        path = Path(dirpath) / name
        if path.suffix in {".parquet", ".xlsx"}:
            hits.append(str(path))
        if not str(path).startswith(secret_roots):
            continue
        if name == ".env" or name.startswith(".env.") or path.suffix == ".pem":
            hits.append(str(path))
        if name in {"credentials.json", "id_rsa", "id_ed25519"}:
            hits.append(str(path))
for path in Path("/app").rglob("*"):
    if not path.is_file() or path.suffix == ".pyc":
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    local_prefix = "/Users" + "/"
    if local_prefix in text:
        hits.append("local-path " + str(path))
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("EIA_API_KEY=") and stripped.split("=", 1)[1].strip():
            hits.append("filled-key " + str(path))
if hits:
    print("\n".join(hits))
    raise SystemExit(1)
print("artifact-exclusion-ok")
"""


def check_status(body: dict) -> None:
    if body.get("presence_mode") != "portable_summary":
        raise AssertionError(body.get("presence_mode"))
    reports = {item["artifact_id"]: item for item in body["artifacts"]}
    summary = reports["committed_summary"]
    if summary["status"] != "valid" or summary["validation"] != "validated":
        raise AssertionError(summary)
    for artifact_id in ("price_history", "holdout_cases", "pjm_2025_tables", "pjm_2026_tables"):
        report = reports[artifact_id]
        if report["status"] != "missing":
            raise AssertionError(report)


def check_evaluation(body: dict) -> None:
    summary = body["summary"]
    if summary["primary_criterion"] != "FAIL":
        raise AssertionError(summary["primary_criterion"])
    expected = {
        "ridge_mae": "2.6384726503825626",
        "paired_baseline_mae": "2.6136666666666666",
        "mae_improvement_percent": "-0.9490875034777213",
        "interval_coverage": "0.0",
        "nominal_interval_coverage": "0.8",
    }
    for key, value in expected.items():
        if summary[key] != value:
            raise AssertionError((key, summary[key]))
    if summary["primary_threshold_percent"] != 10:
        raise AssertionError(summary["primary_threshold_percent"])
    for state, (ridge, baseline, scored) in STATE_MAE.items():
        row = summary["mae_by_state"][state]
        if row["ridge_mae"] != ridge or row["paired_baseline_mae"] != baseline or row["n_scored"] != scored:
            raise AssertionError((state, row))


def check_finance(body: dict) -> None:
    rows = {row["scenario_name"]: row for row in body["scenarios"]}
    baseline = rows["baseline"]
    comparison = rows["comparison"]
    if baseline["annual_consumption_kwh"] != "455520000":
        raise AssertionError(baseline["annual_consumption_kwh"])
    if comparison["annual_consumption_kwh"] != "455520000":
        raise AssertionError(comparison["annual_consumption_kwh"])
    if baseline["annual_electricity_cost_usd"] != "54662400":
        raise AssertionError(baseline["annual_electricity_cost_usd"])
    if comparison["annual_electricity_cost_usd"] != "45552000":
        raise AssertionError(comparison["annual_electricity_cost_usd"])
    if comparison["cost_difference_vs_baseline_usd"] != "-9110400":
        raise AssertionError(comparison["cost_difference_vs_baseline_usd"])
    if baseline["price_source"] != "typed_hypothetical" or comparison["price_source"] != "typed_hypothetical":
        raise AssertionError("finance source changed")


def check_missing(status: int, body: dict, artifact_id: str) -> None:
    if status != 404 or body.get("code") != "artifact_missing" or body.get("artifact_id") != artifact_id:
        raise AssertionError((status, body))
    message = str(body.get("message", ""))
    if "/" in message or "\\" in message:
        raise AssertionError(message)


def check_catalog(body: dict) -> None:
    if body.get("zones") != list(ZONES):
        raise AssertionError(body.get("zones"))
    years = body["forecast_years"]
    if years[0] != 2025 or years[-1] != 2046 or len(years) != 22:
        raise AssertionError((years[0], years[-1], len(years)))
    if body.get("geographic_warning") != GEOGRAPHIC_WARNING:
        raise AssertionError(body.get("geographic_warning"))
    if body.get("large_load_warning") != LARGE_LOAD_WARNING:
        raise AssertionError(body.get("large_load_warning"))


def check_too_large(status: int, body: dict) -> None:
    if status != 413 or body.get("code") != "request_too_large":
        raise AssertionError((status, body))
    if body.get("message") != "The finance request body exceeds 8192 bytes.":
        raise AssertionError(body.get("message"))


def check_three_scenarios(status: int, body: dict) -> None:
    if status != 422 or body.get("code") != "validation_error" or body.get("field") != "scenarios":
        raise AssertionError((status, body))


def finance_payload() -> dict[str, object]:
    return {
        "it_capacity_mw": "50",
        "pue": "1.30",
        "utilization": "0.80",
        "operating_hours_per_year": "8760",
        "baseline_name": "baseline",
        "scenarios": [
            {"name": "baseline", "source": "typed_hypothetical", "price_cents_per_kwh": "12"},
            {"name": "comparison", "source": "typed_hypothetical", "price_cents_per_kwh": "10"},
        ],
    }


def _request(method: str, path: str, payload: bytes | None = None) -> tuple[int, dict]:
    data = payload
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"http://{HOST}:{HOST_PORT}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
        return exc.code, parsed


def _run(command: list[str], *, stdin: str | None = None) -> str:
    completed = subprocess.run(
        command,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "command failed")
    return completed.stdout


def _logs() -> None:
    completed = subprocess.run(
        ["docker", "logs", CONTAINER],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout)
    if completed.stderr:
        print(completed.stderr)


def exercise_http() -> None:
    status_code, status_body = _request("GET", "/api/v1/status")
    if status_code != 200:
        raise AssertionError(status_code)
    check_status(status_body)
    summary_code, summary_body = _request("GET", "/api/v1/evaluation/summary")
    if summary_code != 200:
        raise AssertionError(summary_code)
    check_evaluation(summary_body)
    finance_code, finance_body = _request(
        "POST",
        "/api/v1/finance/scenarios",
        json.dumps(finance_payload()).encode("utf-8"),
    )
    if finance_code != 200:
        raise AssertionError((finance_code, finance_body))
    check_finance(finance_body)
    oversized_code, oversized_body = _request("POST", "/api/v1/finance/scenarios", b"x" * 8193)
    check_too_large(oversized_code, oversized_body)
    three = finance_payload()
    scenarios = list(three["scenarios"])  # type: ignore[arg-type]
    scenarios.append({"name": "extra", "source": "typed_hypothetical", "price_cents_per_kwh": "11"})
    three["scenarios"] = scenarios
    three_code, three_body = _request("POST", "/api/v1/finance/scenarios", json.dumps(three).encode("utf-8"))
    check_three_scenarios(three_code, three_body)
    history_code, history_body = _request("GET", "/api/v1/eia/history")
    check_missing(history_code, history_body, "price_history")
    holdout_code, holdout_body = _request("GET", "/api/v1/eia/holdout")
    check_missing(holdout_code, holdout_body, "holdout_cases")
    cases_code, cases_body = _request("GET", "/api/v1/eia/holdout/cases")
    check_missing(cases_code, cases_body, "holdout_cases")
    screen_code, screen_body = _request(
        "GET",
        "/api/v1/pjm/screen?pjm_zone=AEP&forecast_year=2026&as_of=2026-02-06",
    )
    check_missing(screen_code, screen_body, "pjm_2025_tables")
    catalog_code, catalog_body = _request("GET", "/api/v1/pjm/catalog")
    if catalog_code != 200:
        raise AssertionError(catalog_code)
    check_catalog(catalog_body)


def main() -> None:
    checkout_hash = hashlib.sha256(SUMMARY.read_bytes()).hexdigest()
    if checkout_hash != PINNED_SUMMARY_SHA256:
        raise SystemExit("checkout summary hash does not match the pinned evaluation")
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "10001:10001",
            "--entrypoint",
            "python",
            IMAGE,
            "-c",
            _IMPORT_PROBE,
        ]
    )
    audit = _run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "0:0",
            "--entrypoint",
            "python",
            IMAGE,
            "-c",
            _AUDIT_PROBE,
        ]
    )
    image_hash = audit.splitlines()[0].strip()
    if image_hash != PINNED_SUMMARY_SHA256:
        raise SystemExit("image summary hash does not match the pinned evaluation")
    if "artifact-exclusion-ok" not in audit:
        raise SystemExit(audit)
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True, check=False)
    _run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER,
            "--user",
            "10001:10001",
            "-p",
            f"{HOST}:{HOST_PORT}:8000",
            "-e",
            "INFRALENS_ROOT=/app",
            "-e",
            "PORT=8000",
            IMAGE,
        ]
    )
    try:
        user = _run(["docker", "inspect", "-f", "{{.Config.User}}", CONTAINER]).strip()
        command = _run(["docker", "inspect", "-f", "{{json .Config.Cmd}}", CONTAINER]).strip()
        if user != "10001:10001":
            raise SystemExit(f"container user is {user}")
        if command != '["/app/deploy/start_api.sh"]':
            raise SystemExit(f"container command is {command}")
        deadline = time.monotonic() + 45
        last_error = "startup timed out"
        while time.monotonic() < deadline:
            running = _run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER]).strip()
            if running != "true":
                last_error = "container exited during startup"
                break
            try:
                code, _body = _request("GET", "/api/v1/status")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                time.sleep(1)
                continue
            if code == 200:
                exercise_http()
                print("portable-image-ok")
                return
            last_error = f"status {code}"
            time.sleep(1)
        _logs()
        raise SystemExit(last_error)
    except BaseException:
        _logs()
        raise
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True, check=False)


if __name__ == "__main__":
    main()

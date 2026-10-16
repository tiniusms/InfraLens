"""Contract tests for the read-only API. They do not score the holdout."""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from infralens.api.app import create_app
from infralens.data import repository_root
from infralens.demo.eia_views import DEMO_STATES, HOLDOUT_TARGET_MONTHS
from infralens.demo.foundation import default_artifact_paths
from infralens.demo.pjm_screen import workbook_paths
from infralens.finance.annual_cost import EIA_MODEL_PRICE_WARNING
from infralens.screening.pjm_sources import EXPECTED_B1_ZONE_CODES
from infralens.screening.pjm_view import PjmViewError

_API_ROOT = Path(__file__).resolve().parents[1] / "src" / "infralens" / "api"
_SUMMARY = repository_root() / "docs" / "final_eia_holdout_oneshot.json"
_BANNED_API_TEXT = (
    "final_holdout",
    "eia_ingest",
    "eia_client",
    "run_final_holdout",
    "relative_improvement",
    "fit_ridge",
)


def _client(root: Path | None = None, origins: list[str] | None = None) -> TestClient:
    return TestClient(create_app(root=root, cors_origins=origins or []))


def _json(response) -> dict:
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def _assert_public(payload: object, *forbidden: str) -> None:
    text = json.dumps(payload)
    assert "Traceback" not in text
    assert "api_key" not in text.lower()
    for item in forbidden:
        assert item not in text


def _finance_body(**overrides: object) -> dict:
    body: dict[str, object] = {
        "it_capacity_mw": "50",
        "pue": "1.3",
        "utilization": "0.8",
        "operating_hours_per_year": "8760",
        "baseline_name": "baseline",
        "scenarios": [
            {
                "name": "baseline",
                "source": "typed_hypothetical",
                "price_cents_per_kwh": "12",
            },
            {
                "name": "comparison",
                "source": "typed_hypothetical",
                "price_cents_per_kwh": "10",
            },
        ],
    }
    body.update(overrides)
    return body


def test_api_package_does_not_reference_scoring_or_ingest() -> None:
    modules: set[str] = set()
    for path in sorted(_API_ROOT.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for banned in _BANNED_API_TEXT:
            assert banned not in source, f"{path.name} contains {banned}"
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
    banned_modules = {
        "infralens.evaluation.final_holdout",
        "infralens.data.eia_ingest",
        "infralens.data.eia_client",
        "infralens.evaluation",
    }
    assert modules.isdisjoint(banned_modules)


def test_routes_do_not_expose_scoring_or_downloads() -> None:
    app = create_app(root=repository_root(), cors_origins=[])
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/status",
        "/api/v1/evaluation/summary",
        "/api/v1/eia/history",
        "/api/v1/eia/holdout",
        "/api/v1/eia/holdout/cases",
        "/api/v1/finance/scenarios",
        "/api/v1/pjm/catalog",
        "/api/v1/pjm/screen",
    }
    assert expected <= paths
    joined = " ".join(paths)
    for banned in ("train", "ingest", "download"):
        assert banned not in joined


def test_wildcard_cors_is_rejected() -> None:
    with pytest.raises(ValueError, match="Wildcard"):
        create_app(cors_origins=["*"])


def test_cors_allowlist_echoes_only_the_configured_origin() -> None:
    with _client(repository_root(), ["https://app.example"]) as client:
        allowed = client.get("/api/v1/pjm/catalog", headers={"Origin": "https://app.example"})
        rejected = client.get("/api/v1/pjm/catalog", headers={"Origin": "https://other.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://app.example"
    assert rejected.headers.get("access-control-allow-origin") is None


def test_catalog_lists_zones_and_years_without_a_state_join() -> None:
    with _client() as client:
        response = client.get("/api/v1/pjm/catalog")
    assert response.status_code == 200
    body = _json(response)
    assert body["claim_boundary"] == "pjm_zonal_planning"
    assert body["zones"] == list(EXPECTED_B1_ZONE_CODES)
    assert body["forecast_year_min"] == 2025
    assert body["forecast_year_max"] == 2046
    assert body["forecast_years"][0] == 2025
    assert body["forecast_years"][-1] == 2046
    assert 2024 not in body["forecast_years"]
    assert "state_id" not in body
    assert "not interchangeable" in body["geographic_warning"]
    assert "not added" in body["large_load_warning"]
    assert body["measure_unit"] == "MW"


def test_committed_summary_is_read_and_unchanged() -> None:
    before = hashlib.sha256(_SUMMARY.read_bytes()).hexdigest()
    stored = json.loads(_SUMMARY.read_text(encoding="utf-8"), parse_float=Decimal)
    with _client(repository_root()) as client:
        response = client.get("/api/v1/evaluation/summary")
    after = hashlib.sha256(_SUMMARY.read_bytes()).hexdigest()
    assert before == after
    assert response.status_code == 200
    body = _json(response)
    _assert_public(body, str(repository_root()))
    summary = body["summary"]
    assert body["claim_boundary"] == "closed_historical_evaluation"
    assert body["source_label"] == "docs/final_eia_holdout_oneshot.json"
    assert summary["primary_criterion"] == "FAIL"
    assert summary["ridge_mae"] == "2.6384726503825626"
    assert summary["paired_baseline_mae"] == "2.6136666666666666"
    assert summary["mae_improvement_percent"] == "-0.9490875034777213"
    assert round(Decimal(summary["mae_improvement_percent"]), 4) == Decimal("-0.9491")
    assert summary["primary_threshold_percent"] == 10
    assert summary["primary_threshold_ratio"] == "0.1"
    assert summary["interval_coverage"] == "0.0"
    assert summary["mae_difference"] == stored_decimal_text(stored["summary"]["mae_difference"])
    assert summary["mae_improvement_ratio"] == stored_decimal_text(stored["summary"]["mae_improvement_ratio"])
    assert Decimal(summary["ridge_mae"]) == stored["summary"]["ridge_mae"]
    assert Decimal(summary["paired_baseline_mae"]) == stored["summary"]["paired_baseline_mae"]
    assert body["runner_commit"] == stored["runner_commit"]
    assert "production forecast" in body["limitations"]
    assert body["units"]["mae"] == "cents/kWh"
    assert body["units"]["threshold"] == "percent"


def stored_decimal_text(value: Decimal) -> str:
    return format(value, "f")


def test_status_on_the_repository_separates_validation_from_presence() -> None:
    paths = default_artifact_paths()
    with _client(repository_root()) as client:
        body = _json(client.get("/api/v1/status"))
    by_id = {item["artifact_id"]: item for item in body["artifacts"]}
    assert body["claim_boundary"] is None
    assert body["presence_mode_meaning"] == "file_existence_only"
    assert "Historical evaluation" in body["prototype_caption"]
    summary = by_id["committed_summary"]
    assert summary["status"] == "valid"
    assert summary["validation"] == "validated"
    if paths.price_history.is_file():
        assert by_id["price_history"]["status"] == "valid"
    else:
        assert by_id["price_history"]["status"] == "missing"
    if paths.holdout_cases.is_file():
        assert by_id["holdout_cases"]["status"] == "valid"
    else:
        assert by_id["holdout_cases"]["status"] == "missing"
    for artifact_id, path in (
        ("pjm_2025_tables", paths.pjm_2025_tables),
        ("pjm_2026_tables", paths.pjm_2026_tables),
    ):
        if path.is_file():
            assert by_id[artifact_id]["status"] == "present_unvalidated"
            assert by_id[artifact_id]["validation"] == "deferred"
        else:
            assert by_id[artifact_id]["status"] == "missing"
    if all(item["status"] != "missing" for item in body["artifacts"]):
        assert body["presence_mode"] == "local_full_data"
    else:
        assert body["presence_mode"] == "portable_summary"


def test_portable_root_serves_summary_and_typed_finance_only(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "final_eia_holdout_oneshot.json"
    target.write_bytes(_SUMMARY.read_bytes())
    with _client(tmp_path) as client:
        status = _json(client.get("/api/v1/status"))
        summary = client.get("/api/v1/evaluation/summary")
        history = client.get("/api/v1/eia/history")
        holdout = client.get("/api/v1/eia/holdout")
        cases = client.get("/api/v1/eia/holdout/cases")
        screen = client.get(
            "/api/v1/pjm/screen",
            params={"pjm_zone": "AEP", "forecast_year": 2026, "as_of": "2026-02-06"},
        )
        finance = client.post("/api/v1/finance/scenarios", json=_finance_body())
    assert status["presence_mode"] == "portable_summary"
    assert {item["artifact_id"]: item["status"] for item in status["artifacts"]} == {
        "committed_summary": "valid",
        "price_history": "missing",
        "holdout_cases": "missing",
        "pjm_2025_tables": "missing",
        "pjm_2026_tables": "missing",
    }
    assert summary.status_code == 200
    assert _json(summary)["summary"]["primary_criterion"] == "FAIL"
    for missing, artifact_id in (
        (history, "price_history"),
        (holdout, "holdout_cases"),
        (cases, "holdout_cases"),
        (screen, "pjm_2025_tables"),
    ):
        assert missing.status_code == 404
        body = _json(missing)
        assert body["code"] == "artifact_missing"
        assert body["artifact_id"] == artifact_id
        _assert_public(body, str(tmp_path))
    assert _json(history)["message"].startswith("EIA commercial price history is not on this machine")
    assert finance.status_code == 200
    rows = {row["scenario_name"]: row for row in _json(finance)["scenarios"]}
    assert rows["baseline"]["annual_consumption_kwh"] == "455520000"
    assert rows["baseline"]["annual_electricity_cost_usd"] == "54662400"
    assert rows["baseline"]["facility_average_demand_mw"] == "52"
    assert rows["baseline"]["cost_difference_vs_baseline_usd"] == "0"
    assert rows["comparison"]["annual_electricity_cost_usd"] == "45552000"
    assert rows["comparison"]["cost_difference_vs_baseline_usd"] == "-9110400"
    assert rows["baseline"]["model_price_warning"] is None
    assert rows["comparison"]["model_price_warning"] is None
    assert rows["baseline"]["price_unit"] == "cents/kWh"
    assert rows["baseline"]["annual_electricity_cost_unit"] == "USD"
    assert _json(finance)["claim_boundary"] == "hypothetical_energy_cost"
    assert _json(finance)["closed_holdout_limitation"] is None


def test_typed_inputs_use_decimal_strings_and_reject_numbers(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        numeric = client.post(
            "/api/v1/finance/scenarios",
            json=_finance_body(it_capacity_mw=50),
        )
        scaled = client.post(
            "/api/v1/finance/scenarios",
            json=_finance_body(pue="1.30", utilization="0.80"),
        )
    assert numeric.status_code == 422
    assert _json(numeric)["code"] == "validation_error"
    assert scaled.status_code == 200
    row = _json(scaled)["scenarios"][0]
    assert Decimal(row["annual_consumption_kwh"]) == Decimal("455520000")
    assert Decimal(row["annual_electricity_cost_usd"]) == Decimal("54662400")


@pytest.mark.parametrize(
    ("field_name", "value", "expected_field"),
    [
        ("pue", "0.99", "pue"),
        ("utilization", "1.2", "utilization"),
        ("utilization", "-0.1", "utilization"),
        ("operating_hours_per_year", "0", "operating_hours_per_year"),
        ("it_capacity_mw", "-1", "it_capacity_mw"),
    ],
)
def test_finance_range_errors_name_the_field(
    tmp_path: Path,
    field_name: str,
    value: str,
    expected_field: str,
) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/v1/finance/scenarios", json=_finance_body(**{field_name: value}))
    assert response.status_code == 422
    body = _json(response)
    assert body["code"] == "validation_error"
    assert body["field"] == expected_field


def test_negative_price_and_client_controlled_model_flag_are_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        negative = client.post(
            "/api/v1/finance/scenarios",
            json=_finance_body(
                scenarios=[
                    {
                        "name": "baseline",
                        "source": "typed_hypothetical",
                        "price_cents_per_kwh": "-1",
                    }
                ],
                baseline_name="baseline",
            ),
        )
        flagged = client.post(
            "/api/v1/finance/scenarios",
            json=_finance_body(
                scenarios=[
                    {
                        "name": "baseline",
                        "source": "typed_hypothetical",
                        "price_cents_per_kwh": "12",
                        "model_derived_eia_price": True,
                    }
                ]
            ),
        )
        supplied = client.post(
            "/api/v1/finance/scenarios",
            json={
                "it_capacity_mw": "50",
                "pue": "1.3",
                "utilization": "0.8",
                "baseline_name": "baseline",
                "scenarios": [
                    {
                        "name": "baseline",
                        "source": "holdout_ridge",
                        "price_cents_per_kwh": "12",
                        "case_key": {
                            "state_id": "VA",
                            "forecast_origin": "2024-07-31",
                            "target_month": "2025-07",
                        },
                    }
                ],
            },
        )
        missing_cases = client.post(
            "/api/v1/finance/scenarios",
            json={
                "it_capacity_mw": "50",
                "pue": "1.3",
                "utilization": "0.8",
                "baseline_name": "baseline",
                "scenarios": [
                    {
                        "name": "baseline",
                        "source": "holdout_ridge",
                        "case_key": {
                            "state_id": "VA",
                            "forecast_origin": "2024-07-31",
                            "target_month": "2025-07",
                        },
                    }
                ],
            },
        )
    assert negative.status_code == 422
    assert _json(negative)["field"] == "price_cents_per_kwh"
    assert flagged.status_code == 422
    assert _json(flagged)["code"] == "validation_error"
    assert supplied.status_code == 422
    assert _json(supplied)["field"] == "price_cents_per_kwh"
    assert "client-supplied" in _json(supplied)["message"]
    assert missing_cases.status_code == 404
    assert _json(missing_cases)["code"] == "artifact_missing"
    assert _json(missing_cases)["artifact_id"] == "holdout_cases"
    _assert_public(_json(missing_cases), str(tmp_path))


def test_invalid_summary_is_artifact_invalid_without_a_path(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "final_eia_holdout_oneshot.json").write_text("{", encoding="utf-8")
    with _client(tmp_path) as client:
        status = _json(client.get("/api/v1/status"))
        response = client.get("/api/v1/evaluation/summary")
    summary = next(item for item in status["artifacts"] if item["artifact_id"] == "committed_summary")
    assert summary["status"] == "invalid"
    assert summary["validation"] == "failed"
    assert response.status_code == 500
    body = _json(response)
    assert body["code"] == "artifact_invalid"
    assert body["artifact_id"] == "committed_summary"
    _assert_public(body, str(tmp_path))


def test_present_but_unreadable_caches_stay_distinct_from_missing(tmp_path: Path) -> None:
    interim = tmp_path / "data" / "interim"
    interim.mkdir(parents=True)
    extract = interim / "eia_retail_sales_monthly_com_20260911T190524Z.parquet"
    extract.write_text("not parquet", encoding="utf-8")
    raw = tmp_path / "data" / "raw" / "pjm"
    raw.mkdir(parents=True)
    for name in ("2025-load-report-tables.xlsx", "2026-load-report-tables.xlsx"):
        (raw / name).write_bytes(b"")
    with _client(tmp_path) as client:
        before = _json(client.get("/api/v1/status"))
        history = client.get("/api/v1/eia/history", params={"state_id": "PA"})
        screen = client.get(
            "/api/v1/pjm/screen",
            params={"pjm_zone": "AEP", "forecast_year": 2026, "as_of": "2026-02-06"},
        )
        after = _json(client.get("/api/v1/status"))
    before_status = {item["artifact_id"]: item["status"] for item in before["artifacts"]}
    after_status = {item["artifact_id"]: item["status"] for item in after["artifacts"]}
    assert before_status["price_history"] == "invalid"
    assert before_status["pjm_2025_tables"] == "present_unvalidated"
    assert before_status["pjm_2026_tables"] == "present_unvalidated"
    assert history.status_code == 500
    assert _json(history)["code"] == "artifact_invalid"
    assert screen.status_code == 500
    assert _json(screen)["code"] == "artifact_invalid"
    assert after_status["pjm_2025_tables"] == "invalid"
    assert after_status["pjm_2026_tables"] == "invalid"
    _assert_public(_json(history), str(tmp_path))
    _assert_public(_json(screen), str(tmp_path))


def test_query_validation_rejects_unknown_state_and_bad_dates(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        state = client.get("/api/v1/eia/history", params={"state_id": "TX"})
        bad_date = client.get(
            "/api/v1/pjm/screen",
            params={"pjm_zone": "AEP", "forecast_year": 2026, "as_of": "2025-13-01"},
        )
        bad_zone = client.get(
            "/api/v1/pjm/screen",
            params={"pjm_zone": "NOPE", "forecast_year": 2026, "as_of": "2026-02-06"},
        )
        bad_year = client.get(
            "/api/v1/pjm/screen",
            params={"pjm_zone": "AEP", "forecast_year": 1999, "as_of": "2026-02-06"},
        )
    for response in (state, bad_date, bad_zone, bad_year):
        assert response.status_code == 422
        assert _json(response)["code"] == "validation_error"


def test_malformed_vintage_is_conflict_and_does_not_substitute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = tmp_path / "data" / "raw" / "pjm"
    raw.mkdir(parents=True)
    for name in ("2025-load-report-tables.xlsx", "2026-load-report-tables.xlsx"):
        (raw / name).write_bytes(b"placeholder")

    def _loaded(_raw_dir: Path):
        return ([], [], SimpleNamespace(note="patched"))

    def _boom(*_args, **_kwargs):
        raise PjmViewError("public vintage is incomplete")

    monkeypatch.setattr("infralens.api.readers.load_screening_tables", _loaded)
    monkeypatch.setattr("infralens.api.readers.screen_cached_zone", _boom)
    with _client(tmp_path) as client:
        response = client.get(
            "/api/v1/pjm/screen",
            params={"pjm_zone": "AEP", "forecast_year": 2026, "as_of": "2026-02-06"},
        )
    assert response.status_code == 409
    body = _json(response)
    assert body["code"] == "malformed_vintage"
    assert "summer_peak_mw" not in body
    assert "incomplete" in body["message"]
    _assert_public(body, str(tmp_path))


def test_observed_history_uses_the_loader_roles() -> None:
    path = default_artifact_paths().price_history
    if not path.is_file():
        pytest.skip("Frozen EIA price history is not on this machine.")
    with _client(repository_root()) as client:
        response = client.get("/api/v1/eia/history", params={"state_id": "PA"})
    assert response.status_code == 200
    body = _json(response)
    assert body["claim_boundary"] == "observed_history"
    assert body["returned_row_count"] == 306
    assert body["extract_row_count"] == 1530
    assert body["unit"] == "cents/kWh"
    assert body["points"][0]["period"] == "2001-01"
    assert body["points"][-1]["period"] == "2026-06"
    assert {point["state_id"] for point in body["points"]} == {"PA"}
    assert {point["role"] for point in body["points"]} == {"observed"}
    Decimal(body["points"][0]["observed_price_cents_per_kwh"])
    assert "not a forecast" in body["limitations"]


def test_holdout_series_keeps_origins_in_provenance() -> None:
    path = default_artifact_paths().holdout_cases
    if not path.is_file():
        pytest.skip("Frozen holdout cases are not on this machine.")
    with _client(repository_root()) as client:
        response = client.get("/api/v1/eia/holdout", params={"state_id": "VA"})
        cases = client.get("/api/v1/eia/holdout/cases")
    assert response.status_code == 200
    body = _json(response)
    assert body["claim_boundary"] == "closed_historical_evaluation"
    assert body["window"]["axis"] == "target_month"
    assert [point["target_month"] for point in body["points"]] == list(HOLDOUT_TARGET_MONTHS)
    assert body["points"][0]["provenance"]["forecast_origin"] == "2024-07-31"
    assert body["points"][-1]["provenance"]["forecast_origin"] == "2025-06-30"
    assert {point["actual"]["role"] for point in body["points"]} == {"observed"}
    assert {point["ridge"]["role"] for point in body["points"]} == {"closed_prediction"}
    assert {point["seasonal_naive"]["role"] for point in body["points"]} == {"closed_prediction"}
    assert all(point["interval"]["covered"] is False for point in body["points"])
    assert "0%" in body["window"]["interval_warning"]
    assert "nominal 80%" in body["window"]["interval_warning"]
    assert "forecast_origin" not in body["points"][0]
    assert cases.status_code == 200
    case_body = _json(cases)
    assert case_body["row_count"] == 60
    assert {item["state_id"] for item in case_body["cases"]} == set(DEMO_STATES)


def test_holdout_ridge_price_comes_from_the_case_file() -> None:
    path = default_artifact_paths().holdout_cases
    if not path.is_file():
        pytest.skip("Frozen holdout cases are not on this machine.")
    with _client(repository_root()) as client:
        cases = _json(client.get("/api/v1/eia/holdout/cases"))
        quote = cases["cases"][0]
        response = client.post(
            "/api/v1/finance/scenarios",
            json={
                "it_capacity_mw": "50",
                "pue": "1.3",
                "utilization": "0.8",
                "operating_hours_per_year": "8760",
                "baseline_name": "typed",
                "scenarios": [
                    {
                        "name": "typed",
                        "source": "typed_hypothetical",
                        "price_cents_per_kwh": "12",
                    },
                    {
                        "name": "ridge",
                        "source": "holdout_ridge",
                        "case_key": {
                            "state_id": quote["state_id"],
                            "forecast_origin": quote["forecast_origin"],
                            "target_month": quote["target_month"],
                        },
                    },
                ],
            },
        )
        unknown = client.post(
            "/api/v1/finance/scenarios",
            json={
                "it_capacity_mw": "50",
                "pue": "1.3",
                "utilization": "0.8",
                "baseline_name": "ridge",
                "scenarios": [
                    {
                        "name": "ridge",
                        "source": "holdout_ridge",
                        "case_key": {
                            "state_id": "VA",
                            "forecast_origin": "1900-01-01",
                            "target_month": "1901-01",
                        },
                    }
                ],
            },
        )
    assert response.status_code == 200
    body = _json(response)
    rows = {row["scenario_name"]: row for row in body["scenarios"]}
    assert rows["typed"]["model_derived_eia_price"] is False
    assert rows["typed"]["model_price_warning"] is None
    assert rows["ridge"]["model_derived_eia_price"] is True
    assert rows["ridge"]["model_price_warning"] == EIA_MODEL_PRICE_WARNING
    assert Decimal(rows["ridge"]["price_cents_per_kwh"]) == Decimal(quote["ridge_prediction_cents_per_kwh"])
    assert body["closed_holdout_limitation"] == EIA_MODEL_PRICE_WARNING
    assert body["closed_holdout_claim_boundary"] == "closed_historical_evaluation"
    assert unknown.status_code == 422
    assert _json(unknown)["code"] == "validation_error"
    assert "invent" in _json(unknown)["message"] or "not in the frozen file" in _json(unknown)["message"]


def test_pjm_published_and_unpublished_boundaries_match_the_workbooks() -> None:
    raw_dir = default_artifact_paths().pjm_2025_tables.parent
    if not all(path.is_file() for path in workbook_paths(raw_dir)):
        pytest.skip("Official PJM Tables workbooks are not in data/raw/pjm.")
    with _client(repository_root()) as client:
        before = _json(client.get("/api/v1/status"))
        early = client.get(
            "/api/v1/pjm/screen",
            params={"pjm_zone": "AEP", "forecast_year": 2026, "as_of": "2025-06-30"},
        )
        listing = client.get(
            "/api/v1/pjm/screen",
            params={"pjm_zone": "AEP", "forecast_year": 2026, "as_of": "2026-01-14"},
        )
        current = client.get(
            "/api/v1/pjm/screen",
            params={"pjm_zone": "AEP", "forecast_year": 2026, "as_of": "2026-02-06"},
        )
        unpublished = client.get(
            "/api/v1/pjm/screen",
            params={"pjm_zone": "AEP", "forecast_year": 2026, "as_of": "2025-01-23"},
        )
        after = _json(client.get("/api/v1/status"))
    assert before["artifacts"][3]["status"] == "present_unvalidated"
    early_body = _json(early)
    listing_body = _json(listing)
    current_body = _json(current)
    unpublished_body = _json(unpublished)
    assert early.status_code == listing.status_code == current.status_code == 200
    for body in (early_body, listing_body):
        assert body["available"] is True
        assert body["claim_boundary"] == "pjm_zonal_planning"
        assert body["ltlf_vintage_year"] == 2025
        assert body["summer_peak_mw"] == 25788.0
        assert body["summer_peak_10yr_cagr"] == 0.0547154909
        assert body["above_embedded_mw"] == 3621.0
        assert body["total_associated_mw"] == 3936.0
        assert body["revision_date"] is None
        assert body["vintage_available_at"] == "2025-01-24"
        assert body["above_embedded_mw"] != body["total_associated_mw"]
        assert "state_id" not in body
        assert body["measure_unit"] == "MW"
    assert current_body["ltlf_vintage_year"] == 2026
    assert current_body["summer_peak_mw"] == 24635.0
    assert current_body["summer_peak_10yr_cagr"] == 0.0525293343
    assert current_body["above_embedded_mw"] == 1913.0
    assert current_body["total_associated_mw"] == 2699.0
    assert current_body["original_release_date"] == "2026-01-14"
    assert current_body["revision_date"] == "2026-02-06"
    assert current_body["vintage_available_at"] == "2026-02-06"
    assert current_body["source_tables"] == ["B1", "B-9", "B-9b"]
    assert current_body["above_embedded_mw"] != current_body["total_associated_mw"]
    assert "not a PJM publication date" in current_body["retrieval_note"]
    assert unpublished.status_code == 200
    assert unpublished_body["available"] is False
    assert unpublished_body["summer_peak_mw"] is None
    assert unpublished_body["above_embedded_mw"] is None
    assert unpublished_body["total_associated_mw"] is None
    assert unpublished_body["summer_peak_10yr_cagr"] is None
    assert unpublished_body["ltlf_vintage_year"] is None
    assert 0 not in {
        unpublished_body["summer_peak_mw"],
        unpublished_body["above_embedded_mw"],
        unpublished_body["total_associated_mw"],
    }
    assert "public" in unpublished_body["unavailable_reason"]
    assert date.fromisoformat(unpublished_body["as_of_date"]) == date(2025, 1, 23)
    validated = {
        item["artifact_id"]: item["status"]
        for item in after["artifacts"]
        if item["artifact_id"].startswith("pjm_")
    }
    assert validated == {"pjm_2025_tables": "valid", "pjm_2026_tables": "valid"}

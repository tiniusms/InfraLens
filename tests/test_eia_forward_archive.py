"""Forward archive and vintage ledger (Version 2 Phase 2, criterion 5).

These tests never skip and use no network. Fetches go through a mock transport
with synthetic payloads in temporary directories.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from infralens.data import EIA_RETAIL_SALES_DATA_URL, repository_root
from infralens.evaluation.backtest import latest_eia_parquet

_ROOT = repository_root()
_LEDGER = _ROOT / "data" / "eia_vintage_ledger.json"
_spec = importlib.util.spec_from_file_location("eia_snapshot", _ROOT / "scripts" / "eia_snapshot.py")
assert _spec is not None and _spec.loader is not None
snapshot_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snapshot_tool)

_KEY = "SYNTHETIC-key/value+1"
_START = datetime(2026, 12, 24, 15, 0, 1, tzinfo=timezone.utc)
_STAMP = "20261224T150001Z"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_SNAPSHOT_KEYS = {
    "id",
    "path",
    "retrieved_at",
    "retrieval_completed_at",
    "files",
    "payload_sha256",
    "row_count",
    "earliest_period",
    "latest_period",
    "follows_epm_release",
    "bulk_manifest_elec_last_updated",
    "tier",
    "capture",
}
_GAP_KEYS = {"epm_release_date", "data_month", "gap_type", "later_snapshot_id", "release_date_evidence", "reason"}


def _rows(periods: tuple[str, ...] = ("2026-09", "2026-10")) -> list[dict[str, str]]:
    return [
        {"period": period, "stateid": state, "sectorid": "COM", "price": "10.00", "sales": "1.0", "revenue": "0.1"}
        for period in periods
        for state in ("VA", "PA", "OH", "MD", "NJ")
    ]


class _Eia:
    """A synthetic EIA service that echoes the API key, as the API can."""

    def __init__(self, rows: list[dict[str, str]] | None = None, page_size: int = 6) -> None:
        self.rows = _rows() if rows is None else rows
        self.page_size = page_size
        self.bulk_values = ["2026-12-23T18:00:00-05:00"]
        self.bulk_calls = 0
        self.status = 200
        self.fail_with: Exception | None = None
        self.header_value = "synthetic"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.fail_with is not None:
            raise self.fail_with
        url = str(request.url)
        if url.startswith(snapshot_tool.BULK_MANIFEST_URL):
            value = self.bulk_values[min(self.bulk_calls, len(self.bulk_values) - 1)]
            self.bulk_calls += 1
            return httpx.Response(200, json={"dataset": {"ELEC": {"last_updated": value, "modified": value}}})
        if self.status != 200:
            return httpx.Response(self.status, text=f"error for {url}")
        headers = {"Last-Modified": self.header_value, "Set-Cookie": "ignored=1"}
        echoed = {"api_key": request.url.params.get("api_key"), "encoded": str(request.url.query)}
        if url.split("?")[0] == EIA_RETAIL_SALES_DATA_URL:
            offset = int(request.url.params["offset"])
            data = self.rows[offset : offset + self.page_size]
            body = {
                "response": {"total": str(len(self.rows)), "data": data},
                "request": {"params": echoed},
                "apiVersion": "2.1.12",
            }
            return httpx.Response(200, json=body, headers=headers)
        body = {
            "response": {"id": "retail-sales", "startPeriod": "2001-01", "endPeriod": "2026-10"},
            "request": {"params": echoed},
        }
        return httpx.Response(200, json=body, headers=headers)


def _clock() -> object:
    ticks = iter(range(100))

    def now() -> datetime:
        return _START + timedelta(milliseconds=next(ticks))

    return now


def _take(root: Path, service: _Eia, month: str = "2026-10") -> dict:
    with httpx.Client(transport=httpx.MockTransport(service)) as client:
        return snapshot_tool.take_snapshot(
            root=root,
            api_key=_KEY,
            client=client,
            epm_release_date="2026-12-23",
            epm_data_month=month,
            clock=_clock(),
        )


def _all_bytes(root: Path) -> bytes:
    return b"".join(path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file())


def _ledger() -> dict:
    return json.loads(_LEDGER.read_text(encoding="utf-8"))


def _assert_snapshot_schema(entry: dict) -> None:
    assert set(entry) == _SNAPSHOT_KEYS
    assert re.fullmatch(r"\d{8}T\d{6}Z", entry["id"])
    assert entry["path"] == f"data/raw/eia/vintages/{entry['id']}"
    assert _UTC.match(entry["retrieved_at"]) and _UTC.match(entry["retrieval_completed_at"])
    assert entry["retrieved_at"] <= entry["retrieval_completed_at"]
    started = datetime.fromisoformat(entry["retrieved_at"].replace("Z", "+00:00"))
    assert started.strftime("%Y%m%dT%H%M%SZ") == entry["id"]
    assert _SHA.match(entry["payload_sha256"])
    assert isinstance(entry["row_count"], int) and entry["row_count"] > 0
    assert _MONTH.match(entry["earliest_period"]) and _MONTH.match(entry["latest_period"])
    assert entry["earliest_period"] <= entry["latest_period"]
    assert entry["tier"] == snapshot_tool.TIER
    assert entry["capture"] == "after_release"
    release = entry["follows_epm_release"]
    assert set(release) == {"release_date", "data_month"}
    assert date.fromisoformat(release["release_date"]) <= started.date()
    assert release["data_month"] == entry["latest_period"]
    names = [item["file"] for item in entry["files"]]
    assert len(names) == len(set(names)) and {"route_metadata.json", "snapshot_metadata.json"} <= set(names)
    assert any(re.fullmatch(r"data_page_\d{4}\.json", name) for name in names)
    for item in entry["files"]:
        assert set(item) == {"file", "sha256", "size_bytes"}
        assert _SHA.match(item["sha256"])
        assert isinstance(item["size_bytes"], int) and item["size_bytes"] > 0


def test_ledger_schema_and_recorded_history() -> None:
    ledger = _ledger()
    assert ledger["ledger_version"] == 1
    assert ledger["source"]["route"] == "/v2/electricity/retail-sales/data/"
    assert ledger["source"]["sectorid"] == "COM"
    assert ledger["source"]["stateid"] == ["VA", "PA", "OH", "MD", "NJ"]
    for entry in ledger["snapshots"]:
        _assert_snapshot_schema(entry)
    ids = [entry["id"] for entry in ledger["snapshots"]]
    assert ids == sorted(set(ids))
    first = ledger["snapshots"][0]
    assert (first["id"], first["row_count"], first["latest_period"]) == ("20261124T023746Z", 1540, "2026-08")
    assert first["follows_epm_release"] == {"release_date": "2026-10-23", "data_month": "2026-08"}
    gaps = {gap["epm_release_date"]: gap for gap in ledger["gaps"]}
    assert set(gaps) >= {"2026-09-24", "2026-10-23"}
    for gap in ledger["gaps"]:
        assert set(gap) == _GAP_KEYS
        date.fromisoformat(gap["epm_release_date"])
        assert _MONTH.match(gap["data_month"])
        assert gap["gap_type"] in {"full_panel_not_saved", "not_captured_at_release"}
        assert gap["reason"].strip() and gap["release_date_evidence"].strip()
        if gap["gap_type"] == "full_panel_not_saved":
            assert gap["later_snapshot_id"] is None
        else:
            assert gap["later_snapshot_id"] in ids
    assert gaps["2026-09-24"]["gap_type"] == "full_panel_not_saved"
    assert gaps["2026-10-23"]["gap_type"] == "not_captured_at_release"
    assert gaps["2026-10-23"]["later_snapshot_id"] == "20261124T023746Z"


def test_snapshots_present_locally_match_the_ledger() -> None:
    checked, absent = [], []
    for entry in _ledger()["snapshots"]:
        directory = _ROOT / entry["path"]
        if not directory.is_dir():
            absent.append(entry["id"])
            continue
        assert {path.name for path in directory.iterdir()} == {item["file"] for item in entry["files"]}
        for item in entry["files"]:
            data = (directory / item["file"]).read_bytes()
            assert len(data) == item["size_bytes"], item["file"]
            assert hashlib.sha256(data).hexdigest() == item["sha256"], item["file"]
        pages = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("data_page_*.json"))]
        assert snapshot_tool.payload_sha256(pages) == entry["payload_sha256"]
        assert sum(len(page["response"]["data"]) for page in pages) == entry["row_count"]
        checked.append(entry["id"])
    print(f"EIA vintage ledger: verified {checked or 'none'}; not on this machine: {absent or 'none'}")


def test_ledger_is_committed_and_snapshots_stay_local_only() -> None:
    policy = json.loads((_ROOT / "data" / "distribution_policy.json").read_text(encoding="utf-8"))
    assert policy["additional_files"] == {"data/eia_vintage_ledger.json": "committed"}
    assert policy["local_only_directories"] == ["data/raw/eia/vintages/"]
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=_ROOT, check=True, capture_output=True).stdout.decode()
    names = [name for name in tracked.split("\0") if name]
    assert "data/eia_vintage_ledger.json" in names
    assert not [name for name in names if name.startswith("data/raw/eia/vintages/")]
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "--", "data/raw/eia/vintages/20261124T023746Z/data_page_0001.json"],
        cwd=_ROOT,
    )
    assert ignored.returncode == 0


def test_snapshot_writes_one_verified_file_set(tmp_path: Path) -> None:
    entry = _take(tmp_path, _Eia())
    _assert_snapshot_schema(entry)
    target = tmp_path / "data" / "raw" / "eia" / "vintages" / _STAMP
    assert entry["id"] == _STAMP and entry["row_count"] == 10
    assert {path.name for path in target.iterdir()} == {
        "route_metadata.json",
        "data_page_0001.json",
        "data_page_0002.json",
        "snapshot_metadata.json",
    }
    for item in entry["files"]:
        data = (target / item["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
        assert len(data) == item["size_bytes"]
        assert (target / item["file"]).stat().st_mode & 0o222 == 0
    metadata = json.loads((target / "snapshot_metadata.json").read_text(encoding="utf-8"))
    assert metadata["api_latest_period_field"]["endPeriod"] == "2026-10"
    assert all("set-cookie" not in item["headers"] for item in metadata["requests"])
    assert entry["payload_sha256"] == snapshot_tool.payload_sha256(
        [json.loads((target / name).read_text()) for name in ("data_page_0002.json", "data_page_0001.json")]
    )
    assert [path.name for path in target.parent.iterdir()] == [_STAMP]


def test_snapshot_refuses_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "data" / "raw" / "eia" / "vintages" / _STAMP
    target.mkdir(parents=True)
    marker = target / "existing.json"
    marker.write_text("keep", encoding="utf-8")
    service = _Eia()
    with pytest.raises(snapshot_tool.SnapshotError, match="will not be overwritten"):
        _take(tmp_path, service)
    assert marker.read_text(encoding="utf-8") == "keep"
    assert [path.name for path in target.iterdir()] == ["existing.json"]
    assert service.bulk_calls == 0


def test_no_key_in_files_or_output(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    service = _Eia()
    entry = _take(tmp_path, service)
    saved = _all_bytes(tmp_path)
    encoded = httpx.QueryParams({"api_key": _KEY}).get("api_key")
    assert encoded == _KEY
    assert _KEY.encode() not in saved
    assert b"SYNTHETIC-key%2Fvalue%2B1" not in saved
    assert b"<redacted>" in saved
    assert _KEY not in json.dumps(entry)

    root = tmp_path / "cli"
    monkeypatch.setattr(snapshot_tool, "repository_root", lambda: root)
    monkeypatch.setattr(snapshot_tool, "load_eia_api_key", lambda: _KEY)
    real_client = httpx.Client
    monkeypatch.setattr(
        snapshot_tool.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(_Eia()), **kwargs),
    )
    assert snapshot_tool.main(["--epm-release-date", "2026-12-23", "--epm-data-month", "2026-10"]) == 0
    printed = capsys.readouterr()
    assert _KEY not in printed.out + printed.err
    assert "SYNTHETIC-key%2F" not in printed.out + printed.err
    assert _KEY.encode() not in _all_bytes(root)


@pytest.mark.parametrize("failure", ["http_status", "transport", "key_in_header"])
def test_failures_write_nothing_and_never_show_the_key(tmp_path: Path, failure: str) -> None:
    service = _Eia()
    if failure == "http_status":
        service.status = 500
    elif failure == "transport":
        service.fail_with = httpx.ConnectError(f"cannot reach host with {_KEY}")
    else:
        service.header_value = _KEY
    with pytest.raises(snapshot_tool.SnapshotError) as refused:
        _take(tmp_path, service)
    assert _KEY not in str(refused.value)
    assert refused.value.__cause__ is None
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize(
    ("change", "message"),
    [("bulk_update", "updated the dataset"), ("wrong_month", "latest period"), ("empty", "empty page")],
)
def test_inconsistent_snapshots_are_refused(tmp_path: Path, change: str, message: str) -> None:
    service = _Eia()
    month = "2026-10"
    if change == "bulk_update":
        service.bulk_values = ["2026-12-23T18:00:00-05:00", "2026-12-24T10:00:00-05:00"]
    elif change == "wrong_month":
        month = "2026-11"
    else:
        service.page_size = 0
    with pytest.raises(snapshot_tool.SnapshotError, match=message):
        _take(tmp_path, service, month)
    assert not list(tmp_path.rglob("*.json"))


def test_latest_eia_parquet_is_unaffected_by_a_snapshot(tmp_path: Path) -> None:
    interim = tmp_path / "data" / "interim"
    interim.mkdir(parents=True)
    frozen = interim / "eia_retail_sales_monthly_com_20260911T190524Z.parquet"
    frozen.write_bytes(b"frozen")
    before = sorted(path.name for path in interim.iterdir())
    assert latest_eia_parquet(tmp_path) == frozen
    _take(tmp_path, _Eia())
    assert sorted(path.name for path in interim.iterdir()) == before
    assert frozen.read_bytes() == b"frozen"
    assert latest_eia_parquet(tmp_path) == frozen


def test_snapshot_command_is_separate_from_ingest_and_ci() -> None:
    source = (_ROOT / "scripts" / "eia_snapshot.py").read_text(encoding="utf-8")
    assert "eia_ingest" not in source
    assert "data/interim" not in source.replace("writes nothing to ``data/interim/``", "")
    assert '"interim"' not in source
    for workflow in (_ROOT / ".github" / "workflows").glob("*.yml"):
        assert "eia_snapshot" not in workflow.read_text(encoding="utf-8"), workflow.name

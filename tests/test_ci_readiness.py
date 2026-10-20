"""Readiness-loop tests. They do not build an image or start Docker."""

from __future__ import annotations

import http.client
import importlib.util
import urllib.error
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "deploy" / "ci_portable_image.py"


def _module():
    spec = importlib.util.spec_from_file_location("ci_portable_image", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clock():
    now = {"t": 0.0}

    def clock() -> float:
        return now["t"]

    def sleep(seconds: float) -> None:
        now["t"] += seconds

    return now, clock, sleep


def _wait(module, probe, *, running=None, state="running exit=0 error=", logs="Uvicorn running", deadline=45.0):
    now, clock, sleep = _clock()
    module.wait_for_api(
        deadline=deadline,
        clock=clock,
        sleep=sleep,
        container_running=running or (lambda: True),
        container_state=lambda: state,
        probe=probe,
        logs=lambda: logs,
    )
    return now


def test_connection_reset_then_http_200_is_ready() -> None:
    module = _module()
    assert module.READINESS_SECONDS == 45
    attempts = {"n": 0}

    def probe() -> int:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionResetError(104, "Connection reset by peer")
        return 200

    now = _wait(module, probe)
    assert attempts["n"] == 2
    assert now["t"] == 1


def test_refused_and_remote_disconnect_then_ready() -> None:
    module = _module()
    queued: list[BaseException | int] = [
        ConnectionRefusedError(111, "Connection refused"),
        http.client.RemoteDisconnected("Remote end closed connection without response"),
        urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer")),
        200,
    ]

    def probe() -> int:
        item = queued.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    now = _wait(module, probe)
    assert queued == []
    assert now["t"] == 3


def test_permanent_reset_reaches_the_deadline_and_redacts_logs() -> None:
    module = _module()

    def probe() -> int:
        raise ConnectionResetError(104, "Connection reset by peer")

    with pytest.raises(SystemExit) as raised:
        _wait(
            module,
            probe,
            logs="EIA_API_KEY=supersecret\nUvicorn running",
            state="running exit=0 error=",
        )
    message = str(raised.value)
    assert "startup timed out" in message
    assert "ConnectionResetError" in message
    assert "state=running exit=0 error=" in message
    assert "Uvicorn running" in message
    assert "supersecret" not in message
    assert "EIA_API_KEY=[redacted]" in message


def test_container_exit_fails_before_the_probe() -> None:
    module = _module()

    def probe() -> int:
        raise AssertionError("probe must not run after the container exits")

    with pytest.raises(SystemExit) as raised:
        _wait(
            module,
            probe,
            running=lambda: False,
            state="exited exit=1 error=",
            logs="Application startup failed",
        )
    message = str(raised.value)
    assert "container exited during startup" in message
    assert "exit=1" in message
    assert "Application startup failed" in message


def test_exit_after_a_reset_fails_without_waiting_out_the_deadline() -> None:
    module = _module()
    up = {"value": True}

    def running() -> bool:
        return up["value"]

    def probe() -> int:
        up["value"] = False
        raise ConnectionResetError(104, "Connection reset by peer")

    now, clock, sleep = _clock()
    with pytest.raises(SystemExit) as raised:
        module.wait_for_api(
            deadline=45,
            clock=clock,
            sleep=sleep,
            container_running=running,
            container_state=lambda: "exited exit=137 error=",
            probe=probe,
            logs=lambda: "docker logs were empty",
        )
    assert now["t"] == 0
    assert "exit=137" in str(raised.value)
    assert "ConnectionResetError" in str(raised.value)


def test_scientific_assertion_after_http_200_propagates(capsys: pytest.CaptureFixture[str]) -> None:
    module = _module()

    def exercise() -> None:
        raise AssertionError("ridge_mae")

    with pytest.raises(AssertionError, match="ridge_mae"):
        module.run_when_ready(lambda: _wait(module, lambda: 200), exercise)
    captured = capsys.readouterr()
    assert "api-ready" in captured.out
    assert "portable-image-ok" not in captured.out
    assert module.is_transient_transport_error(AssertionError("primary_criterion")) is False


def test_assertion_from_the_probe_is_not_retried() -> None:
    module = _module()

    def probe() -> int:
        raise AssertionError("primary_criterion")

    with pytest.raises(AssertionError, match="primary_criterion"):
        _wait(module, probe)

"""Supervisor tests. They use substitute processes and do not contact Cloudflare."""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _ROOT / "deploy" / "supervise_private.py"
_TOKEN = "example-tunnel-token"


def _module():
    spec = importlib.util.spec_from_file_location("supervise_private", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sleeper(pid_path: Path, *, ignore_term: bool = False) -> list[str]:
    action = "signal.SIG_IGN" if ignore_term else "signal.SIG_DFL"
    code = (
        "import os, pathlib, signal, time\n"
        f"pathlib.Path({str(pid_path)!r}).write_text(str(os.getpid()))\n"
        f"signal.signal(signal.SIGTERM, {action})\n"
        "time.sleep(60)\n"
    )
    return [sys.executable, "-c", code]


def _dead(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def _wait_for_pid(path: Path) -> int:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return int(path.read_text(encoding="utf-8"))
        time.sleep(0.02)
    raise AssertionError(f"child did not write {path}")


def _run(tmp_path: Path, commands: list[list[str]], *, grace: float, token: str | None) -> subprocess.Popen[str]:
    runner = tmp_path / "run_supervisor.py"
    runner.write_text(
        "import importlib.util, json, os, sys\n"
        f"spec = importlib.util.spec_from_file_location('supervise_private', {str(_MODULE_PATH)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "commands = json.loads(os.environ['SUPERVISOR_COMMANDS'])\n"
        "raise SystemExit(module.supervise(\n"
        "    commands[0], commands[1], environ=os.environ,\n"
        "    grace_seconds=float(os.environ['SUPERVISOR_GRACE']),\n"
        "))\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("TUNNEL_TOKEN", None)
    if token is not None:
        env["TUNNEL_TOKEN"] = token
    env["SUPERVISOR_COMMANDS"] = json.dumps(commands)
    env["SUPERVISOR_GRACE"] = str(grace)
    return subprocess.Popen(
        [sys.executable, str(runner)],
        env=env,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _stop(proc: subprocess.Popen[str]) -> tuple[int, str]:
    try:
        stdout, stderr = proc.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
        raise AssertionError("supervisor did not exit") from None
    assert proc.returncode is not None
    return proc.returncode, stdout + stderr


def test_missing_token_fails_closed_without_starting_children(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    marker = tmp_path / "started"
    module = _module()
    command = [sys.executable, "-c", f"import pathlib; pathlib.Path({str(marker)!r}).write_text('started')"]
    code = module.supervise(command, command, environ={})
    assert code == 1
    assert not marker.exists()
    captured = capsys.readouterr()
    assert captured.err.strip() == "TUNNEL_TOKEN is required for the private service."
    assert _TOKEN not in captured.err


def test_blank_token_and_bad_port_fail_before_cloudflared(tmp_path: Path) -> None:
    module = _module()
    assert module.supervise(["sleep", "30"], ["sleep", "30"], environ={"TUNNEL_TOKEN": "   "}) == 1
    env = os.environ.copy()
    env.pop("TUNNEL_TOKEN", None)
    env["PORT"] = "nope"
    proc = subprocess.Popen(
        [sys.executable, str(_MODULE_PATH)],
        env=env,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    code, text = _stop(proc)
    assert code == 1
    assert "PORT must be a decimal port." in text
    assert "cloudflared" not in text


def test_production_command_keeps_the_token_out_of_argv() -> None:
    module = _module()
    uvicorn, cloudflared = module.production_commands("10000")
    joined = " ".join([*uvicorn, *cloudflared])
    assert "--host" in uvicorn and "0.0.0.0" in uvicorn
    assert "--port" in uvicorn and "10000" in uvicorn
    assert "--no-proxy-headers" in uvicorn
    assert "--limit-concurrency" in uvicorn and "16" in uvicorn
    assert "--timeout-keep-alive" in uvicorn and "5" in uvicorn
    assert cloudflared[0] == "/usr/local/bin/cloudflared"
    assert "--no-autoupdate" in cloudflared
    assert "--token" not in cloudflared
    assert "TUNNEL_TOKEN" not in joined
    script = (_ROOT / "deploy" / "start_private.sh").read_text(encoding="utf-8")
    assert "exec python /app/deploy/supervise_private.py" in script
    assert "TUNNEL_TOKEN=" not in script
    assert "--token" not in script


def test_child_exit_stops_the_other_child(tmp_path: Path) -> None:
    pid_path = tmp_path / "uvicorn.pid"
    proc = _run(
        tmp_path,
        [_sleeper(pid_path), [sys.executable, "-c", "import sys; sys.exit(3)"]],
        grace=0.3,
        token=_TOKEN,
    )
    try:
        pid = _wait_for_pid(pid_path)
        code, text = _stop(proc)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    assert code == 1
    assert _dead(pid)
    assert _TOKEN not in text


def test_ignored_term_is_killed_and_reaped(tmp_path: Path) -> None:
    pid_path = tmp_path / "stuck.pid"
    proc = _run(
        tmp_path,
        [_sleeper(pid_path, ignore_term=True), [sys.executable, "-c", "import sys; sys.exit(3)"]],
        grace=0.3,
        token=_TOKEN,
    )
    try:
        pid = _wait_for_pid(pid_path)
        code, text = _stop(proc)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    assert code == 1
    assert _dead(pid)
    assert _TOKEN not in text


def test_termination_stops_both_children(tmp_path: Path) -> None:
    first = tmp_path / "first.pid"
    second = tmp_path / "second.pid"
    argv_path = tmp_path / "argv.txt"
    argv_command = [
        sys.executable,
        "-c",
        "import pathlib, signal, sys, time\n"
        f"pathlib.Path({str(second)!r}).write_text(str(__import__('os').getpid()))\n"
        f"pathlib.Path({str(argv_path)!r}).write_text('\\n'.join(sys.argv))\n"
        "signal.signal(signal.SIGTERM, signal.SIG_DFL)\n"
        "time.sleep(60)\n",
    ]
    proc = _run(tmp_path, [_sleeper(first), argv_command], grace=1, token=_TOKEN)
    try:
        first_pid = _wait_for_pid(first)
        second_pid = _wait_for_pid(second)
        os.kill(proc.pid, signal.SIGTERM)
        code, text = _stop(proc)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    assert code == 0
    assert _dead(first_pid)
    assert _dead(second_pid)
    argv = argv_path.read_text(encoding="utf-8")
    assert "--token" not in argv
    assert _TOKEN not in argv
    assert _TOKEN not in text


def test_failed_spawn_does_not_leave_the_first_child(tmp_path: Path) -> None:
    pid_path = tmp_path / "partial.pid"
    marker = f"infralens-partial-{tmp_path.name}"
    sleeper = _sleeper(pid_path)
    sleeper.append(marker)
    proc = _run(
        tmp_path,
        [sleeper, ["this-command-does-not-exist-infralens"]],
        grace=0.2,
        token=_TOKEN,
    )
    try:
        code, text = _stop(proc)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    assert code == 1
    assert "FileNotFoundError" in text
    assert _TOKEN not in text
    if pid_path.exists():
        assert _dead(int(pid_path.read_text(encoding="utf-8")))
    leftover = subprocess.run(["pgrep", "-f", marker], check=False, capture_output=True, text=True)
    assert leftover.returncode != 0

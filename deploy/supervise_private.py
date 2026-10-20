"""Run Uvicorn and cloudflared as one private-service process.

The image shell is Debian dash, reached as ``/bin/sh``. dash ``wait`` can wait
for every job or for one pid. It cannot wait for whichever of two children
exits first (``wait -n`` is a bash feature). A ``kill -0`` poll that never
``wait``s also leaves a zombie. ``deploy/start_private.sh`` therefore execs
this module. The stdlib supervisor reaps both children, forwards termination,
and does not put ``TUNNEL_TOKEN`` on a command line.

The token is read only from the environment. cloudflared reads that same
variable. This module never prints the value.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence

_MISSING_TOKEN = "TUNNEL_TOKEN is required for the private service."
_REQUEST_TIMEOUT = "30"
_CLOUDFLARED = "/usr/local/bin/cloudflared"


def production_commands(port: str) -> tuple[list[str], list[str]]:
    """Uvicorn matches ``start_api.sh``. cloudflared has no ``--token`` argument."""

    uvicorn = [
        sys.executable,
        "-m",
        "uvicorn",
        "infralens.api.app:app",
        "--host",
        "0.0.0.0",
        "--port",
        port,
        "--no-proxy-headers",
        "--limit-concurrency",
        "16",
        "--timeout-keep-alive",
        "5",
    ]
    cloudflared = [
        _CLOUDFLARED,
        "--no-autoupdate",
        "tunnel",
        "run",
        "--grace-period",
        "10s",
    ]
    return uvicorn, cloudflared


def _forward(procs: list[subprocess.Popen[bytes]], signum: int) -> None:
    for proc in procs:
        if proc.poll() is None:
            try:
                proc.send_signal(signum)
            except OSError:
                continue


def _reap(procs: list[subprocess.Popen[bytes]]) -> None:
    for proc in procs:
        if proc.poll() is None:
            proc.kill()
        proc.wait()


def supervise(
    uvicorn_cmd: Sequence[str],
    cloudflared_cmd: Sequence[str],
    *,
    environ: Mapping[str, str],
    grace_seconds: float = 15.0,
    poll_seconds: float = 0.05,
) -> int:
    """Start both children. Exit 0 on a requested stop, and 1 if either child dies."""

    token = environ.get("TUNNEL_TOKEN", "")
    if not token.strip():
        print(_MISSING_TOKEN, file=sys.stderr)
        return 1
    child_env = dict(environ)
    child_env.setdefault("INFRALENS_REQUEST_TIMEOUT_SECONDS", _REQUEST_TIMEOUT)
    procs: list[subprocess.Popen[bytes]] = []
    mode = ""

    def on_signal(signum: int, _frame: object) -> None:
        nonlocal mode
        if not mode:
            mode = "signal"
        _forward(procs, signum)

    previous_term = signal.signal(signal.SIGTERM, on_signal)
    previous_int = signal.signal(signal.SIGINT, on_signal)
    try:
        for command in (list(uvicorn_cmd), list(cloudflared_cmd)):
            procs.append(subprocess.Popen(command, env=child_env))
        kill_at: float | None = None
        while True:
            finished = [proc.poll() is not None for proc in procs]
            if mode == "signal":
                if all(finished):
                    return 0
                if kill_at is None:
                    kill_at = time.monotonic() + grace_seconds
            elif any(finished):
                if not mode:
                    mode = "child"
                    _forward(procs, signal.SIGTERM)
                    kill_at = time.monotonic() + grace_seconds
                if all(proc.poll() is not None for proc in procs):
                    return 1
            if kill_at is not None and time.monotonic() >= kill_at:
                _forward(procs, signal.SIGKILL)
                for proc in procs:
                    proc.wait(timeout=5)
                return 0 if mode == "signal" else 1
            time.sleep(poll_seconds)
    except Exception as exc:
        print(f"Private service failed to start: {type(exc).__name__}.", file=sys.stderr)
        return 1
    finally:
        _reap(procs)
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)


def main() -> int:
    """Validate ``PORT``, then supervise the production commands."""

    port = os.environ.get("PORT", "8000").strip() or "8000"
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        print("PORT must be a decimal port.", file=sys.stderr)
        return 1
    uvicorn_cmd, cloudflared_cmd = production_commands(port)
    return supervise(uvicorn_cmd, cloudflared_cmd, environ=os.environ)


if __name__ == "__main__":
    raise SystemExit(main())

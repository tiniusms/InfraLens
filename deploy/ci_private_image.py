"""Check the private image without a tunnel token or a live Cloudflare connection.

The workflow builds this image on the Linux runner. The build downloads the
pinned cloudflared binary and rejects a checksum mismatch. This script then
checks the architecture, the version, the production connector arguments, and
that startup fails closed when TUNNEL_TOKEN is absent. It does not pass a
token and does not open a tunnel.

A nonzero cloudflared exit is not treated as success. The production arguments
must fail as missing tunnel credentials. ``flag provided but not defined`` and
other incorrect-usage output fail the check. A separate probe confirms that
``--grace-period`` after ``run`` is still that incorrect-usage class.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

IMAGE = "infralens-api:private"
VERSION = "2026.10.1"
_PROBE_NAME = "infralens-cloudflared-probe"
_UNKNOWN_FLAG = "flag provided but not defined"
_MISSING_TUNNEL = '"cloudflared tunnel run" requires the ID or name of the tunnel to run'
_REJECTED_PLACEMENT = ["--no-autoupdate", "tunnel", "run", "--grace-period", "10s"]
_SECRET_LINE = re.compile(
    r"(?i)\b(EIA_API_KEY|TOKEN|SECRET|PASSWORD|AUTHORIZATION)\b\s*[=:].*"
)
_ELF_PROBE = r"""
import struct
from pathlib import Path
data = Path("/usr/local/bin/cloudflared").read_bytes()[:20]
assert data[:4] == b"\x7fELF", data[:4]
assert data[4] == 2 and data[5] == 1
machine = struct.unpack_from("<H", data, 18)[0]
assert machine == 62, machine
"""


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True)


def production_cloudflared_command() -> list[str]:
    """Return the exact cloudflared argv the supervisor will exec."""

    path = Path(__file__).resolve().parent / "supervise_private.py"
    spec = importlib.util.spec_from_file_location("supervise_private", path)
    if spec is None or spec.loader is None:
        raise SystemExit("could not load the private supervisor")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _uvicorn, cloudflared = module.production_commands("10000")
    if not isinstance(cloudflared, list) or not cloudflared:
        raise SystemExit("supervisor cloudflared command was empty")
    return cloudflared


def classify_cloudflared_output(text: str, returncode: int) -> str:
    """Separate a missing-credentials failure from a bad flag or any other exit.

    ``missing-credentials`` is the only accepted result for the production
    command. ``unknown-flag`` is incorrect CLI usage, including the previous
    ``--grace-period`` placement. Every other outcome is ``unexpected``,
    including exit 0 and a timeout.
    """

    if _UNKNOWN_FLAG in text:
        return "unknown-flag"
    if returncode != 0 and _MISSING_TUNNEL in text:
        return "missing-credentials"
    if "Incorrect Usage" in text:
        return "unknown-flag"
    return "unexpected"


def _cloudflared(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the pinned binary with no token and no network."""

    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        _PROBE_NAME,
        "--network",
        "none",
        "--user",
        "10001:10001",
        "--entrypoint",
        "/usr/local/bin/cloudflared",
        IMAGE,
        *args,
    ]
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired as exc:
        subprocess.run(["docker", "rm", "-f", _PROBE_NAME], check=False, capture_output=True, text=True)
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return subprocess.CompletedProcess(command, 124, stdout, stderr + "\ncloudflared probe timed out")


def _show(label: str, text: str) -> None:
    redacted = "\n".join(_SECRET_LINE.sub(r"\1=[redacted]", text.splitlines()))
    print(f"{label}\n{redacted}".rstrip())


def main() -> None:
    user = _run(["docker", "image", "inspect", "-f", "{{.Config.User}}", IMAGE])
    command = _run(["docker", "image", "inspect", "-f", "{{json .Config.Cmd}}", IMAGE])
    if user.returncode != 0 or command.returncode != 0:
        _show("inspect", user.stderr + command.stderr)
        raise SystemExit("private image inspect failed")
    if user.stdout.strip() != "infralens":
        raise SystemExit(f"private image user was {user.stdout.strip()!r}")
    if command.stdout.strip() != '["/app/deploy/start_private.sh"]':
        raise SystemExit(f"private image command was {command.stdout.strip()!r}")

    elf = _run(
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
            _ELF_PROBE,
        ]
    )
    if elf.returncode != 0:
        _show("elf", elf.stdout + elf.stderr)
        raise SystemExit("cloudflared was not a linux amd64 ELF binary")

    version = _run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "10001:10001",
            "--entrypoint",
            "/usr/local/bin/cloudflared",
            IMAGE,
            "--version",
        ]
    )
    version_text = version.stdout + version.stderr
    if version.returncode != 0 or VERSION not in version_text:
        _show("version", version_text)
        raise SystemExit("cloudflared version did not match the pin")

    cloudflared = production_cloudflared_command()
    if cloudflared[0] != "/usr/local/bin/cloudflared" or "--grace-period" in cloudflared:
        raise SystemExit("supervisor cloudflared command is not the checked syntax")
    syntax = _cloudflared(cloudflared[1:])
    syntax_text = syntax.stdout + syntax.stderr
    syntax_class = classify_cloudflared_output(syntax_text, syntax.returncode)
    if syntax_class != "missing-credentials":
        _show("syntax", syntax_text)
        raise SystemExit(f"cloudflared syntax probe was {syntax_class}, not missing-credentials")
    if _SECRET_LINE.search(syntax_text):
        _show("syntax", syntax_text)
        raise SystemExit("cloudflared syntax probe printed a secret assignment")

    rejected = _cloudflared(_REJECTED_PLACEMENT)
    rejected_text = rejected.stdout + rejected.stderr
    rejected_class = classify_cloudflared_output(rejected_text, rejected.returncode)
    if rejected_class != "unknown-flag" or "grace-period" not in rejected_text:
        _show("rejected-placement", rejected_text)
        raise SystemExit("pinned cloudflared did not reject --grace-period after run")
    print("cloudflared-syntax-ok")

    closed = _run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "10001:10001",
            IMAGE,
        ]
    )
    closed_text = closed.stdout + closed.stderr
    if closed.returncode == 0 or "TUNNEL_TOKEN is required for the private service." not in closed_text:
        _show("startup", closed_text)
        raise SystemExit("private startup did not fail closed without TUNNEL_TOKEN")
    if _SECRET_LINE.search(closed_text):
        _show("startup", closed_text)
        raise SystemExit("private startup printed a secret assignment")
    print("private-image-ok")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"private image check failed: {type(exc).__name__}", file=sys.stderr)
        raise

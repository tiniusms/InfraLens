"""Check the private image without a tunnel token or a live Cloudflare connection.

The workflow builds this image on the Linux runner. The build downloads the
pinned cloudflared binary and rejects a checksum mismatch. This script then
checks the architecture, the version, and that startup fails closed when
TUNNEL_TOKEN is absent. It does not pass a token and does not open a tunnel.
"""

from __future__ import annotations

import re
import subprocess
import sys

IMAGE = "infralens-api:private"
VERSION = "2026.10.1"
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

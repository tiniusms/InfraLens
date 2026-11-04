# syntax=docker/dockerfile:1
# Retired hosted use, 2026-11-03. These targets remain a local image recipe
# and a future redeploy recipe. They are not connected to a live Render service.
# Two image targets from one file.
# `portable` is the last-verified standalone API. `docker build --target portable`
# keeps that command and does not install cloudflared.
# `private` is the last stage, so a Render build without a target flag produces
# the private service. Render cannot select a Docker target. The trade-off is
# that a plain `docker build` is the private image, and CI must name `portable`
# to keep the existing smoke test.
# Contents: source, the committed evaluation summary, and requirements-api.txt.
# The four local EIA/PJM artifacts are not copied. Build context exclusions are
# in .dockerignore. This image was not published from this checkpoint.
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS portable

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    INFRALENS_ROOT=/app

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin infralens

COPY requirements-api.txt pyproject.toml README.md ./
COPY src ./src
COPY docs/final_eia_holdout_oneshot.json ./docs/final_eia_holdout_oneshot.json
COPY deploy/start_api.sh ./deploy/start_api.sh

# Check the runtime closure before the local project is installed. That
# project's metadata still requires the scientific stack, which stays out.
RUN pip install --no-cache-dir --no-deps -r requirements-api.txt \
    && pip check \
    && pip install --no-cache-dir --no-deps . \
    && chmod 755 /app/deploy/start_api.sh \
    && chown -R root:root /app \
    && chmod -R a-w /app

USER infralens

EXPOSE 8000

CMD ["/app/deploy/start_api.sh"]

# Private service. The binary is the GitHub release asset for 2026.10.1,
# linux amd64, SHA-256 checked below. That digest was compared with the
# release checksum and with a downloaded copy of the same asset.
FROM portable AS private

USER root

COPY deploy/supervise_private.py deploy/start_private.sh /app/deploy/

# BuildKit runs this heredoc. Render and GitHub Actions both build with BuildKit.
# The URL is one release asset, not the latest alias. A wrong file fails the build.
RUN <<'PY' python
import hashlib
import pathlib
import urllib.request

url = "https://github.com/cloudflare/cloudflared/releases/download/2026.10.1/cloudflared-linux-amd64"
expected = "3bfc539f45d2620c71debb7a86be0efa737ed5ccbad9eb85c787116900e5c586"
payload = urllib.request.urlopen(url, timeout=120).read()
digest = hashlib.sha256(payload).hexdigest()
if digest != expected:
    raise SystemExit("cloudflared checksum mismatch")
path = pathlib.Path("/usr/local/bin/cloudflared")
path.write_bytes(payload)
path.chmod(0o555)
PY
RUN chmod 555 /app/deploy/start_private.sh \
    && chmod 444 /app/deploy/supervise_private.py \
    && chown root:root /usr/local/bin/cloudflared /app/deploy/start_private.sh /app/deploy/supervise_private.py

USER infralens

EXPOSE 10000

CMD ["/app/deploy/start_private.sh"]

#!/bin/sh
# Bind the portable API. Do not print environment values.
set -eu

port="${PORT:-8000}"
case "$port" in
  ""|*[!0-9]*)
    echo "PORT must be a decimal integer." >&2
    exit 1
    ;;
esac

# Process caps only. They are not an edge rate limit, body limit, or timeout
# policy. A public proxy must still enforce those. Forwarded headers stay off.
exec python -m uvicorn infralens.api.app:app \
  --host 0.0.0.0 \
  --port "$port" \
  --no-proxy-headers \
  --limit-concurrency 16 \
  --timeout-keep-alive 5

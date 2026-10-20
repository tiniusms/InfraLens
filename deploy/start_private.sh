#!/bin/sh
# Private Render entrypoint. The standalone image keeps deploy/start_api.sh.
# This shell is dash. It execs the Python supervisor and does not read
# TUNNEL_TOKEN, so the value never appears in this script or in argv.
set -eu
exec python /app/deploy/supervise_private.py

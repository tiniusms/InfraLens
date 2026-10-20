# Portable public deployment

This is a prepared deployment variant. Applying it creates accounts, services, and public URLs, and that step needs approval. Nothing in this repository provisions Vercel, Render, or Cloudflare.

The public process serves the committed evaluation summary and the typed annual-cost identity. It does not serve the EIA price extract, the holdout-case file, or the PJM workbooks. Those four files stay gitignored and out of the image. Do not set `EIA_API_KEY` on either host.

## What is public

| Screen | Public behavior |
| --- | --- |
| Overview | Frozen primary result FAIL, full stored figures, and artifact status. Local-only roles are missing. |
| Financial Scenario Studio | Typed hypothetical prices are calculated by the API. A Ridge case price is unavailable because the case file is absent. |
| Electricity Intelligence | Observed history and holdout cases are unavailable. The page does not invent a series. |
| PJM Infrastructure Explorer | The catalog of zones, forecast years, and warnings is served from code. Zone-year measures are unavailable. Missing workbooks are not replaced with zeros. |

`GET /api/v1/status` reports artifact presence. `presence_mode` `portable_summary` means the summary file is present and the four local artifacts are absent. It is not a new evaluation. Render's private-service readiness check is TCP, not this HTTP path.

## Public path

One Render private Docker service runs Uvicorn and `cloudflared` in the same container. Cloudflare terminates HTTPS for a hostname such as `api.example.com`. The Vercel static build calls that hostname. Vercel does not proxy `/api`.

The private service has no `onrender.com` hostname. Do not add a second Render web service in front of it. A web service would publish an `onrender.com` name that bypasses Cloudflare.

Other services in the same Render workspace and region can still open the private-network address. Cloudflare's rate limit does not see that traffic. This is not total isolation.

## Cloudflare hostname

Use placeholders until a hostname is chosen. Do not put a real name, account id, or token in the repository.

| Setting | Placeholder |
| --- | --- |
| Public API hostname | `api.example.com` |
| Tunnel public hostname | `api.example.com` |
| Origin service URL | `http://127.0.0.1:10000` |
| `httpHostHeader` | `api.example.com` |
| `INFRALENS_ALLOWED_HOSTS` | `api.example.com` |
| `VITE_API_BASE_URL` | `https://api.example.com` |
| `INFRALENS_CORS_ORIGINS` | `https://YOUR-PROJECT.vercel.app` |

`httpHostHeader` is an origin setting on the tunnel, not an application default. Set it to the public hostname so the process sees `Host: api.example.com`. That name has to be the allowlist entry. `localhost` and `127.0.0.1` stay allowed for the connector's own HTTP request and for a local probe. They do not allow an arbitrary public `Host`. A wildcard allowlist is rejected at startup.

The tunnel token is the Render secret `TUNNEL_TOKEN`. The supervisor reads it from the environment and does not pass `--token`. A missing or blank value exits nonzero and prints `TUNNEL_TOKEN is required for the private service.` The value is not in that sentence. Do not put the token in an image, a file, a command line, or GitHub Actions.

HTTPS ends at Cloudflare. `cloudflared` in the container opens an outbound tunnel and then calls `http://127.0.0.1:10000`. Uvicorn binds `0.0.0.0` on `PORT` so Render's TCP probe, which arrives from outside the process, can connect. The loopback address still reaches that bind.

The first hosted boot has to confirm two things this repository cannot see: Render allows outbound TCP 7844, and the platform probes the port the process bound.

## Vercel

Manual project settings:

- Root directory: `frontend`
- Install command: `npm ci` (also in `frontend/vercel.json`)
- Build command: `npm run build` (typecheck, then Vite)
- Output directory: `dist`
- Production environment variable: `VITE_API_BASE_URL=https://api.example.com`

`frontend/vercel.json` rewrites the three deep routes to `/index.html`. Vite's file output still serves `/assets/*` and `/`. Do not add a catch-all rewrite that includes `/api`.

No `EIA_API_KEY` and no other secret belongs in a `VITE_` variable. Vite inlines `VITE_*` into the browser bundle.

HTTPS is the platform URL once a project exists. Before calling the release public, open `/`, `/electricity`, `/finance`, and `/pjm` on that `https` origin and confirm each returns the app shell rather than a platform 404.

Rollback is the previous Vercel deployment of the same project. There is no database migration.

Preview deployments use a different browser origin on every branch. Leave the preview origin off `INFRALENS_CORS_ORIGINS` unless that preview is intentionally public. Do not set the allowlist to `*`.

An explicit empty `VITE_API_BASE_URL` would call same-origin `/api`. Do not use that setting with this Vercel config, because `/api` is not proxied.

## Render

`render.yaml` describes one private Docker service, `infralens-api`. `autoDeployTrigger` is `off`, and the deprecated `autoDeploy: false` is set as well. The trigger wins. Applying the blueprint, or creating the service by hand, is a separate approval. A later git push does not deploy while that trigger stays off.

- Type: `pserv`. This is not `web`.
- Plan: `0.5c-512mb`, the smallest private-service plan in the blueprint spec. There is no free private-service plan.
- Runtime: Docker. `dockerfilePath` is `./Dockerfile` and `dockerContext` is `.`
- Build: Render builds the Dockerfile and cannot select a target. The last stage is `private`, so that build contains `cloudflared`.
- Start: `dockerCommand` is `/app/deploy/start_private.sh`. That script execs the Python supervisor. `deploy/start_api.sh` remains the standalone command and is the `portable` target's `CMD`.
- Port: `PORT=10000`. The supervisor refuses a non-decimal port. The Cloudflare origin URL has to use this same port.
- Readiness: omit `healthCheckPath`. Private services use Render's TCP check. A successful TCP connect does not prove that `cloudflared` is logged in. If either child exits, the supervisor stops the other and exits nonzero so Render can restart the instance.

Dashboard-only variables, each with `sync: false` and no committed value:

- `INFRALENS_CORS_ORIGINS` — the exact page origin, for example `https://YOUR-PROJECT.vercel.app`
- `INFRALENS_ALLOWED_HOSTS` — `api.example.com`
- `TUNNEL_TOKEN` — the tunnel credential

`INFRALENS_ROOT=/app` and `INFRALENS_REQUEST_TIMEOUT_SECONDS=30` are set in the blueprint. Do not set `EIA_API_KEY`. Do not attach the four local artifacts or a disk that contains them.

The image runs as uid 10001. It does not enable Uvicorn proxy headers. `X-Forwarded-For` and `X-Forwarded-Content-Length` do not change the body limit or the client address the app trusts.

Rollback is the previous Render deploy of this service. There is no schema to migrate. To take the API offline, suspend or delete the service; the static shell then fails closed on API calls.

## Two processes

`/bin/sh` in the Debian bookworm image is dash. dash can wait for one pid or for all jobs. It does not provide bash `wait -n`, so a shell loop cannot reliably reap whichever child exits first without leaving a zombie. `start_private.sh` only execs `deploy/supervise_private.py`.

The supervisor starts Uvicorn and `cloudflared`. `SIGTERM` or `SIGINT` is forwarded. A requested stop exits 0 after the children are reaped. If either child exits on its own, the supervisor signals the other, waits, and exits 1. A child that ignores `SIGTERM` is killed after the supervisor's 15-second grace, inside Render's default 30-second shutdown window.

The connector command is `cloudflared tunnel --no-autoupdate run`. On the pinned 2026.10.1 binary, `--no-autoupdate` is a tunnel-command flag and belongs before `run`. `--grace-period` is the same kind of flag. Placing it after `run` is what Render logged as `flag provided but not defined: -grace-period`. The startup command does not pass `--grace-period`. cloudflared's built-in default grace is 30 seconds; the supervisor sends `SIGKILL` at 15 seconds, and that is the shutdown bound this service uses. `TUNNEL_TOKEN` stays in the environment. The command does not pass `--token`, a tunnel ID, or a hostname.

`--timeout-keep-alive 5` closes an idle HTTP connection. It is not a request-duration limit.

## Request duration

`INFRALENS_REQUEST_TIMEOUT_SECONDS=30` installs an application middleware that returns `504` and `request_timeout` when one HTTP request outlives 30 seconds. The unit test uses a short bound and checks that the response arrives before the handler finishes. Unset, the middleware is absent, which is the standalone image's behavior.

Cloudflare's default proxy read timeout is 125 seconds. That is a platform default between Cloudflare and the tunnel. This repository does not configure it, and it has not been measured on a live zone. The 30-second application response is the timeout this code can demonstrate. A synchronous handler that keeps running after cancellation can still occupy a worker thread until it returns. Finance calculations in this API are the tested identity and are not a long-running job.

## Edge rate limit

Before anonymous clients can `POST /api/v1/finance/scenarios`, create one Cloudflare rate-limit rule on the Free plan and then prove it with a live request. The published Free rule, as read for the hosting decision, has these limits:

- One rule.
- The expression can match the path. It cannot match the HTTP method.
- Count by client IP.
- Period 10 seconds, mitigation 10 seconds.
- The count is per data center and can lag, so some extra requests can reach the origin.
- `OPTIONS` requests to that path count. A browser preflight therefore uses the same budget as the `POST`.

Use a finance-path rule, not a method rule. The origin still enforces two scenarios and 8192 body bytes. A larger body returns `413` `request_too_large`. A third scenario returns `422` `validation_error`. Uvicorn concurrency stays 16. CORS stays an explicit origin list with credentials off, methods `GET`, `POST`, and `OPTIONS`, and headers `Accept` and `Content-Type`.

Do not describe the rate limit as active until a live request from outside Cloudflare is limited and a request from another Render private-network service is observed separately. The second request is the bypass. Body-size matching at Cloudflare is not part of this Free rule.

## Image contents

The `portable` target copies only:

- `requirements-api.txt`, `pyproject.toml`, `README.md`
- `src/`
- `docs/final_eia_holdout_oneshot.json`
- `deploy/start_api.sh`

The `private` target starts from that image and adds `deploy/supervise_private.py`, `deploy/start_private.sh`, and `/usr/local/bin/cloudflared`. The binary is `cloudflared-linux-amd64` from release `2026.10.1`. Its SHA-256 is `3bfc539f45d2620c71debb7a86be0efa737ed5ccbad9eb85c787116900e5c586`. The build rejects a different file. It does not download a floating `latest` asset. The asset is linux amd64, the architecture of GitHub-hosted `ubuntu-latest` and of Render. The file is 40,227,032 bytes. That is the download size, not a resident-memory measurement.

Dependencies are the pins in `requirements-api.txt`, installed with `pip --no-deps`, then the local package the same way. `pip check` runs between those two installs. The image does not install the scientific stack used by offline evaluation.

`.dockerignore` keeps `data/`, virtualenvs, `frontend/`, `node_modules`, `dist`, caches, `.env*`, parquet, xlsx, and png files out of the build context. Markdown other than `README.md` is also excluded. The summary JSON is not markdown and is copied by name.

CI builds `--target portable`, runs the existing smoke checks, then builds `--target private` and runs `deploy/ci_private_image.py`. That second step checks the ELF machine, the version string, a token-free startup, and the pinned binary's `tunnel --no-autoupdate run` syntax. The syntax probe expects the missing-tunnel message. A nonzero exit by itself is not enough: an unknown flag, including `--grace-period` after `run`, fails the check. The probe does not receive `TUNNEL_TOKEN` and uses `--network none`.

## Memory and cost still to measure

`0.5c-512mb` is 0.5 CPU and 512 MB. The Render pricing page read on 2026-10-19 listed that private-service plan at $7 per month, plus a Hobby workspace at $0. Confirm the price again before creating the service. Whether Uvicorn, pandas, numpy, and `cloudflared` stay inside 512 MB is not known. The binary size above is not RSS. The first hosted boot has to record resident memory. If it does not fit, the next private-service plan in the same spec is `1c-2g`.

## Checks after a real deploy

1. The service has no public `onrender.com` URL.
2. `https://api.example.com/api/v1/status` is `portable_summary` with the four local roles missing. Replace the placeholder hostname first.
3. `GET /api/v1/evaluation/summary` is primary criterion FAIL, Ridge MAE `2.6384726503825626`, paired baseline MAE `2.6136666666666666`, improvement `-0.9490875034777213`, threshold `10`, interval coverage `0.0`.
4. Typed finance for 50 MW, PUE `1.30`, utilization `0.80`, 8760 hours, 12 and 10 cents/kWh returns `455520000` kWh, `54662400` USD, `45552000` USD, and `-9110400` USD.
5. History, holdout, holdout cases, and `GET /api/v1/pjm/screen` return `404` `artifact_missing`.
6. `GET /api/v1/pjm/catalog` returns zones and both warnings.
7. A body over 8192 bytes returns `413`. Three scenarios return `422`.
8. A finance-path request over the Cloudflare rule is limited, including an `OPTIONS` request. A request from another Render private service is not covered by that rule.
9. The Vercel pages show FAIL, a working typed finance result, and unavailable electricity and PJM measures.
10. The browser origin matches `INFRALENS_CORS_ORIGINS` exactly.
11. Startup logs do not contain the tunnel token.
12. Resident memory fits the selected plan.

## Rights

Publishing the parsed PJM workbook measures, or the EIA extract, is unresolved. This package does not upload those files and does not add an endpoint that reads them from the network. The catalog's zone list and warning text are the strings already in the source tree. A later decision is required before any public mode serves workbook MW or the price history.

## Local builds

Docker was not available on the machine that prepared this variant, so neither target was built here. The portable target is the one CI already exercised at the previous commit. The private target is new and unverified until the workflow runs.

```bash
docker build --target portable -t infralens-api .
docker build --target private -t infralens-api-private .
```

A plain `docker build` selects `private` because it is the last stage. Confirm the running container has no `data/` parquet or xlsx before treating a build as a release artifact. Do not pass a real `TUNNEL_TOKEN` in a local experiment log.

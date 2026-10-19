# Portable public deployment

This is a proposal. Applying it creates accounts, services, and public URLs, and that step needs approval. Nothing in this repository provisions Vercel or Render.

The public process serves the committed evaluation summary and the typed annual-cost identity. It does not serve the EIA price extract, the holdout-case file, or the PJM workbooks. Those four files stay gitignored and out of the image.

## What is public

| Screen | Public behavior |
| --- | --- |
| Overview | Frozen primary result FAIL, full stored figures, and artifact status. Local-only roles are missing. |
| Financial Scenario Studio | Typed hypothetical prices are calculated by the API. A Ridge case price is unavailable because the case file is absent. |
| Electricity Intelligence | Observed history and holdout cases are unavailable. The page does not invent a series. |
| PJM Infrastructure Explorer | The catalog of zones, forecast years, and warnings is served from code. Zone-year measures are unavailable. Missing workbooks are not replaced with zeros. |

`GET /api/v1/status` is the health check. `presence_mode` `portable_summary` is a healthy portable process. It means file presence only. It is not a new evaluation.

## Why the browser calls Render directly

`VITE_API_BASE_URL` is a public origin, not a secret. The Vercel project sets it to the Render `https` origin, with no path. The built client calls that origin.

Vercel does not rewrite `/api`. A same-origin proxy would need the Render hostname in routing config. Vercel expands environment variables in legacy `routes`, not in the `rewrites` used for a static site, and that interaction was not something this checkpoint could run on Vercel. An SPA fallback that also matches `/api` would return `index.html` for API calls. The checked-in rewrites name only `/electricity`, `/finance`, and `/pjm`. `/`, static assets, and `/api` are not rewritten.

Direct calls also keep the 8192-byte finance limit on the API process that enforces it. CORS stays an explicit allowlist. A wildcard origin is rejected at startup.

Preview deployments use a different browser origin on every branch. Leave the preview origin off `INFRALENS_CORS_ORIGINS` unless that preview is intentionally public. The preview shell can load, and API calls then fail in the browser instead of widening CORS. Do not set the allowlist to `*`.

An explicit empty `VITE_API_BASE_URL` would call same-origin `/api`. Do not use that setting with this Vercel config, because `/api` is not proxied.

## Vercel

Manual project settings:

- Root directory: `frontend`
- Install command: `npm ci` (also in `frontend/vercel.json`)
- Build command: `npm run build` (typecheck, then Vite)
- Output directory: `dist`
- Production environment variable: `VITE_API_BASE_URL=https://YOUR-SERVICE.onrender.com`

`frontend/vercel.json` rewrites the three deep routes to `/index.html`. Vite's file output still serves `/assets/*` and `/`. Do not add a catch-all rewrite that includes `/api`.

No `EIA_API_KEY` and no other secret belongs in a `VITE_` variable. Vite inlines `VITE_*` into the browser bundle.

HTTPS is the platform URL once a project exists. Before calling the release public, open `/`, `/electricity`, `/finance`, and `/pjm` on that `https` origin and confirm each returns the app shell rather than a platform 404.

Rollback is the previous Vercel deployment of the same project. There is no database migration.

## Render

`render.yaml` describes one Docker web service, `infralens-api`, with `autoDeploy: false`. Applying the blueprint, or creating the service by hand, is a separate approval. A later git push does not deploy while auto-deploy stays off.

- Source: this repository
- Runtime: Docker, `Dockerfile` at the repository root, context `.`
- Start: `/app/deploy/start_api.sh`
- Port: the script reads `PORT` and binds `0.0.0.0`. Render injects `PORT`. Do not hard-code it.
- Health check path: `/api/v1/status`
- A healthy body has `presence_mode` `portable_summary`, a valid `committed_summary`, and missing `price_history`, `holdout_cases`, `pjm_2025_tables`, and `pjm_2026_tables`.

Environment:

- `INFRALENS_ROOT=/app` is set in the image and in `render.yaml`.
- `INFRALENS_CORS_ORIGINS` is dashboard-only. Set it to the exact Vercel production origin, for example `https://YOUR-PROJECT.vercel.app`. If a custom domain is the page people open, use that origin instead. Several origins are comma-separated. No spaces are required, and `*` is invalid.
- `INFRALENS_ALLOWED_HOSTS` is dashboard-only. Leave it empty until a custom domain is attached. On Render, `RENDER=true` turns host checks on and allows `RENDER_EXTERNAL_HOSTNAME`, `localhost`, and `127.0.0.1`. Render's HTTP health check sends the public hostname, or a verified custom domain once one exists. Add each custom domain here or those requests receive `400` and `Invalid host header`.
- Do not set `EIA_API_KEY`. The API process does not read it. Do not attach the four local artifacts or a disk that contains them.

The image runs as uid 10001. It does not enable Uvicorn proxy headers. `X-Forwarded-For` and `X-Forwarded-Content-Length` do not change the body limit or the client address the app trusts. The process concurrency cap is 16 and the keep-alive is 5 seconds. Those are single-process caps, not a public rate limit.

Rollback is the previous Render deploy of this service. There is no schema to migrate. To take the API offline, suspend or delete the service; the static shell then fails closed on API calls.

## Image contents

`Dockerfile` copies only:

- `requirements-api.txt`, `pyproject.toml`, `README.md`
- `src/`
- `docs/final_eia_holdout_oneshot.json`
- `deploy/start_api.sh`

Dependencies are the pins in `requirements-api.txt`, installed with `pip --no-deps`, then the local package the same way. That is the tested FastAPI, Uvicorn, Starlette, Pydantic, and pandas closure. It does not install the optional FastAPI extras or the scientific stack used by offline evaluation.

`.dockerignore` keeps `data/`, virtualenvs, `frontend/`, `node_modules`, `dist`, caches, `.env*`, parquet, xlsx, and png files out of the build context. Markdown other than `README.md` is also excluded. The summary JSON is not markdown and is copied by name.

## Edge controls before a public finance POST

The API still allows at most two scenarios and reads at most 8192 body bytes before parsing. Oversized bodies return `413` `request_too_large`. A third scenario returns `422` `validation_error`.

This repository does not configure a gateway. Before anonymous internet clients can `POST /api/v1/finance/scenarios`, put a reverse proxy or the platform edge in front of the process and set all of these there:

- Reject finance bodies larger than 8192 bytes.
- Rate-limit that POST per client.
- Cap concurrent requests to the service.
- Set a request timeout.
- Terminate TLS.

Do not describe those controls as active until that proxy exists. Vercel is not that proxy in this design. Render's proposed service does not add them.

Logs: unexpected failures record the exception class name only. Request bodies, source credentials, and filesystem paths are not part of that line. Uvicorn is started with proxy headers disabled. Do not add an access-log format that prints bodies.

## Checks after a real deploy

1. `GET /api/v1/status` is `portable_summary` with the four local roles missing.
2. `GET /api/v1/evaluation/summary` is primary criterion FAIL, Ridge MAE `2.6384726503825626`, paired baseline MAE `2.6136666666666666`, improvement `-0.9490875034777213`, threshold `10`, interval coverage `0.0`.
3. Typed finance for 50 MW, PUE `1.30`, utilization `0.80`, 8760 hours, 12 and 10 cents/kWh returns `455520000` kWh, `54662400` USD, `45552000` USD, and `-9110400` USD.
4. History, holdout, holdout cases, and `GET /api/v1/pjm/screen` return `404` `artifact_missing`.
5. `GET /api/v1/pjm/catalog` returns zones and both warnings.
6. A body over 8192 bytes returns `413`. Three scenarios return `422`.
7. The Vercel pages show FAIL, a working typed finance result, and unavailable electricity and PJM measures.
8. The browser origin matches `INFRALENS_CORS_ORIGINS` exactly.

## Rights

Publishing the parsed PJM workbook measures, or the EIA extract, is unresolved. This package does not upload those files and does not add an endpoint that reads them from the network. The catalog's zone list and warning text are the strings already in the source tree. A later decision is required before any public mode serves workbook MW or the price history.

## Local simulation

Docker was not available in the checkpoint that added this file, so the container was not built here. A portable-root simulation points `INFRALENS_ROOT` at a directory that contains only the committed summary under `docs/` and starts Uvicorn from a developer environment. That is not an image test. Building the image is:

```bash
docker build -t infralens-api .
docker run --rm -p 8000:8000 infralens-api
```

Confirm the running container has no `data/` parquet or xlsx before treating that build as the release artifact.

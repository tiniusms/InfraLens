# InfraLens frontend

Local Vite React app. Overview, Electricity, Finance, and PJM each read the local read-only API. The Vercel project that previously served this build was decommissioned on 2026-11-03. `vercel.json` remains a deployment template. See `docs/infrastructure_decommission_2026_11_03.md`.

## Local environment

Copy `.env.example` to `.env` if the API is not at `http://127.0.0.1:8000`.

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

`VITE_API_BASE_URL` is the only frontend variable. Do not put `EIA_API_KEY` or any other secret in a Vite variable. Vite exposes `VITE_*` values to the browser.

An unset `VITE_API_BASE_URL` stays `http://127.0.0.1:8000`, which is also the value in `.env.example`. An explicit empty value calls same-origin `/api`. `vercel.json` does not proxy that path. A future public build would set an https origin at build time. Do not point this variable at a retired public API. The retained deployment steps are in `docs/portable_deployment.md`.

The API rejects a wildcard CORS origin. For this dev server, start the API with both local origins:

```bash
INFRALENS_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

Vite uses port 5173 (`strictPort`). Open the same host you listed. `localhost` and `127.0.0.1` are different origins.

## Scripts

```bash
npm ci
npm run dev
npm run typecheck
npm run lint
npm test
npm run build
```

IBM Plex Sans and Source Serif 4 are loaded from Fontsource packages. Recharts is installed for a later phase and is not imported here.

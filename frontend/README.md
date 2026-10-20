# InfraLens frontend

Phase 2 is the design system and application shell. Overview reads the live read-only API. Electricity, finance, and PJM routes are shells for later phases.

## Local environment

Copy `.env.example` to `.env` if the API is not at `http://127.0.0.1:8000`.

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

`VITE_API_BASE_URL` is the only frontend variable. Do not put `EIA_API_KEY` or any other secret in a Vite variable. Vite exposes `VITE_*` values to the browser.

The public build sets `VITE_API_BASE_URL` to the Render `https` origin. An unset value stays `http://127.0.0.1:8000`. An explicit empty value calls same-origin `/api`; the Vercel config does not proxy that path. Deployment steps are in `docs/portable_deployment.md`.

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

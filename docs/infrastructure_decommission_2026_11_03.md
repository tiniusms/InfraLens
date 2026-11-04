# Infrastructure decommissioning, 2026-11-03

This note records the intentional retirement of InfraLens public hosting. It is a new event. It does not correct, replace, or reinterpret the October 20, 2026 public-release validation.

## Historical public release versus this shutdown

GitHub pull request #6, “docs: document verified InfraLens public release,” is merged into `main`. The merge commit is `895b5368cb3729953df1218346b78b39bec948e4` (author date 2026-10-23, parent `c41ddfd3e25784bbc9ceb2258ba2e43486c837db`). That squash has the same tree as branch commit `bdcfd23856a16e39aa08e6372306959e33e7046d`. The historical evidence file is [`public_release_validation.md`](public_release_validation.md). This decommissioning note does not reopen that pull request, amend its commits, or edit that file.

On October 20, 2026 the validation recorded a then-live portable deployment:

- Static frontend at `https://infra-lens-gules.vercel.app`
- API at `https://api.infralensenergy.com`, reached through Cloudflare
- Render private service `infralens-api` with a Cloudflare Tunnel of the same name
- `GET /api/v1/status` in portable-summary mode
- Frozen primary criterion FAIL, with the stored Ridge and seasonal-naive MAE figures
- The typed 50 MW annual-cost identity

Those observations describe what was measured that day. The November 3, 2026 shutdown says those hosting components were later turned off on purpose. It does not say the October 20 checks were wrong, and it does not change the frozen FAIL.

The preregistered comparison stays exactly as recorded. Ridge MAE 2.638473 ¢/kWh versus paired seasonal-naive MAE 2.613667 ¢/kWh is an improvement of −0.95% against a required +10%. Empirical interval coverage is 0%. Primary criterion: FAIL. Full precision remains in `docs/final_eia_holdout_oneshot.json`. That result is not a pass.

## Shutdown facts

Effective date: 2026-11-03.

These facts are the operator confirmation supplied for this record. This writing session did not call the former URLs, did not open Vercel, Render, or Cloudflare, and did not change any external cloud service.

| Component | Reported state on 2026-11-03 |
| --- | --- |
| Vercel | InfraLens frontend project deleted. Plan was Hobby. |
| Render | `infralens-api` private service and project deleted. Plan was Hobby. Final balance of $0.69 settled. |
| Cloudflare Tunnel | Tunnel `infralens-api` deleted. |
| Cloudflare DNS | CNAME for `api.infralensenergy.com` removed. |
| Cloudflare Workers | Workers Free. No active paid Workers subscription was evidenced. |
| Domain | Cloudflare Registrar acknowledged a deletion request for `infralensenergy.com`. Registry release is not verified. |
| Source | Local working repository and GitHub repository `tiniusms/InfraLens` retained. |

## Evidence boundaries

Confirmed from the git history in this session:

- Pull request #6 is on `origin/main` at the merge commit above.
- `docs/public_release_validation.md` was left unchanged.
- Application code does not embed `api.infralensenergy.com` or `infra-lens-gules.vercel.app`.
- `frontend/src/api/client.ts` returns `http://127.0.0.1:8000` when `VITE_API_BASE_URL` is unset.
- `frontend/.env.example` sets that same local origin.
- FastAPI host checks stay off unless `RENDER`, `RENDER_EXTERNAL_HOSTNAME`, or `INFRALENS_ALLOWED_HOSTS` is set.

Not established by this repository record:

- A fresh HTTP response from either former public URL. Those calls were intentionally not made.
- That every DNS record other than the reported `api.infralensenergy.com` CNAME is gone.
- That the domain has been released by the registry. Acknowledgement of a deletion request is not release.
- Current Vercel, Render, or Cloudflare invoices beyond the reported final Render balance of $0.69.
- That no tunnel token, account id, or other credential remains in an operator password store. None of those values are in this repository, and this note does not rotate them.

The October 20 file already labels region, plan, tunnel health, the rate-limit rule, and the first memory reading as operator reports. This November 3 file has the same kind of boundary for the shutdown actions.

## Reference classification

| Location | Class | Treatment |
| --- | --- | --- |
| `docs/public_release_validation.md` | Historical evidence of 2026-10-20 | Unchanged |
| `DECISIONS.md` entries dated 2026-10-19 and 2026-10-20 | Historical decisions | Unchanged. The 2026-11-03 entry is appended after them in reverse-chronological order |
| `docs/portable_deployment.md` body | Historical layout plus redeployment template | Status banner added. October 20 table kept |
| `Dockerfile`, `render.yaml`, `frontend/vercel.json`, `deploy/` | Deployment-as-code retained for later use | Marked retired where comments are possible. `vercel.json` is unchanged because it is parsed as strict JSON by tests and has no comment syntax |
| `frontend/src/api/client.ts`, `frontend/.env.example`, `.env.example` | Local configuration | Localhost remains the default. Comments now say the public hosts are retired. No secret values added |
| `README.md`, `ARCHITECTURE.md`, `TASKS.md`, `AGENTS.md`, `CLAUDE.md` | Current operator and agent instructions | Updated so local development is the supported path |

## Retained components

Do not treat this retirement as a deletion of the application.

- FastAPI backend in `src/infralens/api/`
- React frontend in `frontend/`
- Streamlit demo in `src/infralens/demo/`
- Tests, including deployment-template checks
- Frozen evaluation summary `docs/final_eia_holdout_oneshot.json` and the gitignored local holdout artifacts where they already exist
- EIA and PJM data files that are already on disk. They stay gitignored
- Deployment templates listed above
- GitHub repository `tiniusms/InfraLens`

## Local development

These commands are the supported path. They match the files in this repository.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,demo,api]"
python -m streamlit run src/infralens/demo/app.py
```

API, from the repository root, after the same install:

```bash
INFRALENS_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173 \
  python -m uvicorn infralens.api.app:app
```

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

Non-holdout regression command, from `RISK_REGISTER.md`:

```bash
python -m pytest tests --ignore=tests/test_final_holdout.py
```

Do not run `python -m infralens.evaluation.final_holdout`. Do not regenerate frozen evaluation artifacts.

## Future redeployment prerequisites

A later public deployment is possible from the retained templates. It is not authorized by this note.

1. A new, explicit approval to create hosting resources. `render.yaml` and a Vercel project create billable or account-linked resources when applied.
2. New project and service identities. The deleted Vercel project, Render service, and Cloudflare Tunnel are not restored by a git push.
3. A decision about `infralensenergy.com` after registry status is actually known. Do not assume the name is still delegated, and do not assume it has been released.
4. A new tunnel credential supplied only as a runtime secret. Do not commit it, print it, or put it in an image.
5. Explicit `VITE_API_BASE_URL`, `INFRALENS_CORS_ORIGINS`, and `INFRALENS_ALLOWED_HOSTS` for the new names. Do not reuse the retired hostnames unless DNS and the accounts exist again.
6. The portable image contents stay as already specified: source, pinned API dependencies, and `docs/final_eia_holdout_oneshot.json`. The four local EIA and PJM artifacts stay out of the image.
7. The frozen holdout stays closed. Redeployment does not authorize another scoring run.
8. The public surface, if rebuilt, remains the portable summary and the typed cost identity. It is still not a validated production forecast.

## Agent use

`AGENTS.md` and `CLAUDE.md` direct a standalone coding agent at this local repository. No Cursor service is required to install or test the project. `.cursor/rules/infralens.mdc` remains a short restatement of the same project rules.

# Public release validation

Recorded 2026-10-20. This file is the evidence for the public site. It does not change the frozen evaluation, and it does not authorize another deploy.

InfraLens, including this public site, is a historical evaluation, a deterministic hypothetical cost calculator, and an infrastructure-screening prototype. It is not a validated live production forecasting system and not an investment recommendation.

`origin/main` is `c41ddfd3e25784bbc9ceb2258ba2e43486c837db`, the squash of pull request #5 onto `6d8f3ec754f320c72323a491d198f282e10ce4ce`. The squash message is `fix: correct cloudflared tunnel startup arguments (#5)`. GitHub Actions has no run on `main`, because the Portable image workflow starts on pull requests and manual dispatch. The tree of `c41ddfd3e25784bbc9ceb2258ba2e43486c837db` is identical to `0a678e2836102be2353c02a1eeec2edcabfc1658`. That commit's workflow succeeded: [run 39482007846](https://github.com/tiniusms/InfraLens/actions/runs/39482007846).

The committed summary file `docs/final_eia_holdout_oneshot.json` has SHA-256 `5b116d9d0eaba5269f5afab71f60c826f4553174fb330e6e8fe80dfb6eba1393`. The live API returns those summary numbers as decimal strings. The HTTP body is not that file hash.

## Release checklist

- [x] Public pages load over HTTPS at `https://infra-lens-gules.vercel.app` for `/`, `/electricity`, `/finance`, and `/pjm`.
- [x] `GET https://api.infralensenergy.com/api/v1/status` is `portable_summary`, with the committed summary `valid` and the four local artifacts `missing`.
- [x] Overview shows primary criterion FAIL and the stored Ridge and seasonal-naive MAE.
- [x] One browser calculation and one API `POST` return the 50 MW identity.
- [x] Electricity Intelligence reports price history and closed holdout cases unavailable.
- [x] PJM Infrastructure Explorer serves the zone catalog and reports zonal screening unavailable.
- [x] Linux image checks for this tree passed on the pull-request commit above.
- [x] No public EIA extract or PJM workbook was added, and the final holdout command was not run.
- [ ] Private-network bypass of the Cloudflare rate limit, observed from another Render service.
- [ ] A measured browser preflight counted by the rate-limit rule.
- [ ] A load test of memory and CPU.
- [ ] An uptime record beyond this one-day check.
- [ ] Redistribution rights for the EIA extract and the PJM workbooks.

## Evidence

| Test | Expected outcome | Observed evidence | Limitation |
| --- | --- | --- | --- |
| API status | `portable_summary`; committed summary valid; four local roles missing | 2026-10-20 `GET /api/v1/status` HTTP 200. `presence_mode` `portable_summary`. `committed_summary` `valid` / `validated`. `price_history`, `holdout_cases`, `pjm_2025_tables`, and `pjm_2026_tables` are `missing` / `not_applicable`. Response `server` was `cloudflare`. | File presence is not a new evaluation. |
| Frozen summary | Primary FAIL. Required improvement at least +10 percent. Ridge MAE `2.6384726503825626`, seasonal-naive MAE `2.6136666666666666`, achieved improvement `-0.9490875034777213`, interval coverage `0.0` | `GET /api/v1/evaluation/summary` returned those digits, stored threshold `10`, `executed_on` `2026-10-04`, and runner `ee5bcf6d541a1b15822f705e4099320f6f05dc32`. Decimal fields arrived as strings. The summary object matches the committed file aside from that encoding. | The holdout was not rerun. State MAE on the page also matched the file. |
| Overview page | FAIL and the stored MAE are visible | Browser at `/` showed `Primary criterion: FAIL`, Ridge MAE `2.6384726503825626` cents/kWh, seasonal-naive MAE `2.6136666666666666` cents/kWh, and `portable_summary`. | The page reads the stored result. |
| Finance identity | 50 MW, PUE `1.30`, utilization `0.80`, 8760 hours: `455520000` kWh; 12 cents `54662400` USD; 10 cents `45552000` USD; comparison minus baseline `-9110400` USD | API `POST /api/v1/finance/scenarios` with `Origin: https://infra-lens-gules.vercel.app` returned those figures and `Access-Control-Allow-Origin` for that origin. The finance page, with the same inputs, showed the same kWh and USD figures and facility demand `52` MW. | Hypothetical energy charge only. Ridge quote stayed disabled because holdout cases are missing. |
| Electricity page | History and holdout cases unavailable, without a fabricated series | API history, holdout, and cases returned HTTP 404 `artifact_missing`. The page showed `Price history unavailable` and `Closed holdout unavailable`, and still showed primary criterion FAIL. | Local full-data mode can chart those files. The public site cannot. |
| PJM page | Catalog loads; zone-year measures unavailable | Catalog HTTP 200, 22 zones, forecast years 2025 through 2046. Screen for zone `AEP`, year 2026, as of `2026-02-06` returned HTTP 404 `artifact_missing` `pjm_2025_tables`. The page showed both warnings and `Zonal screening unavailable`. | Catalog text is from the source tree. Workbook MW is not public. |
| CORS preflight | A browser preflight carries `Origin` | One `OPTIONS` with `Origin`, `Access-Control-Request-Method: POST`, and `Access-Control-Request-Headers: content-type` returned HTTP 200 and allowed the Vercel origin, methods `GET, POST, OPTIONS`, and `Content-Type`. | This single call was not the rate-limit test. |
| Rate limit | Finance-path rule active at 10 requests per IP per 10 seconds, mitigation 10 seconds | Operator report: rule Active with that configuration. A controlled `OPTIONS` test that omitted `Origin` received `405` from the API, later `429`, and one Cloudflare rate-limit event. | That `OPTIONS` call was not a browser CORS preflight. The limit is per data center, can lag, may count `OPTIONS`, and is not a global server-wide hard cap. The private-network bypass was not tested. |
| Connector | Tunnel `infralens-api`, one healthy connector, `cloudflared` 2026.10.1 | Operator report of that tunnel health and version. The image pin and the Linux workflow check the same version string. The API answered through Cloudflare. | This session did not open the Cloudflare dashboard and did not print a tunnel token. |
| Resources | Service on the 0.5 CPU / 512 MB tier | Operator report: Virginia, about 20 percent of 512 MB, CPU near idle, about $7 per month. | Preliminary. Not a load test and not an availability claim. |
| Image CI | `api-ready`, `portable-image-ok`, `cloudflared-syntax-ok`, `private-image-ok` | [Run 39482007846](https://github.com/tiniusms/InfraLens/actions/runs/39482007846) succeeded on `0a678e2836102be2353c02a1eeec2edcabfc1658` and printed each marker once. | The squash commit on `main` was not itself a workflow head. No local image was built for this note. |
| Secrets and artifacts | No token, no EIA key, no public parquet or workbook | The responses above contain no tunnel token. Status reports the four local artifacts missing. The final holdout command was not run. | EIA and PJM redistribution rights are still unresolved. Absence from this API is not a legal opinion. |

## Hosting and rollback

| Layer | What is live | How to roll back |
| --- | --- | --- |
| Vercel | Static Vite React app at `https://infra-lens-gules.vercel.app`. Deep routes `/electricity`, `/finance`, and `/pjm` return the app shell. | Promote the previous deployment of the same project. |
| Cloudflare | Hostname `api.infralensenergy.com` on zone `infralensenergy.com`, tunnel name `infralens-api`, and one finance-path rate rule. | Restore the previous hostname route and the previous rate rule in the dashboard. |
| Render | Existing private service `infralens-api`. Automatic git deployment is off. | Redeploy the previous image by hand, or suspend the private service. Suspending it makes the static shell fail closed on API calls. |

A git push does not deploy the API while Render `autoDeployTrigger` stays off. Do not create a second Render service. Do not attach an `onrender.com` web service in front of this one.

Environment names, and not their values:

- `TUNNEL_TOKEN` — runtime tunnel credential. It stays out of argv, source, and logs.
- `INFRALENS_CORS_ORIGINS` — the page origin `https://infra-lens-gules.vercel.app`.
- `INFRALENS_ALLOWED_HOSTS` — `api.infralensenergy.com`.
- `PORT` — `10000`, matching the tunnel origin.
- `INFRALENS_REQUEST_TIMEOUT_SECONDS` — `30`.
- `INFRALENS_ROOT` — `/app`.

Do not set `EIA_API_KEY` on Vercel or Render. Do not put the tunnel token, a Cloudflare account id, a Render service id, an email address, or a payment detail in the repository.

## Cost and operations

The selected Render private-service plan is `0.5c-512mb`, listed at $7 per month on the pricing page read on 2026-10-19. The operator reports that tier for the live service. Confirm the price before changing it. The Vercel project is an eligible Hobby free tier. The domain `infralensenergy.com` is billed annually, and the renewal price can change. No renewal amount is recorded here.

Keep checking that `GET /api/v1/status` still returns `portable_summary` and that resident memory stays inside 512 MB. This site has no uptime target. Passing those checks does not make it a production-grade availability service.

## Local full data and the public site

Local full-data mode needs the four gitignored files listed in the repository README. With those files, the Streamlit demo and a local API can show price history, holdout cases, and PJM zone-year measures. The public site is portable mode: the same frozen FAIL and the same Python cost identity, without those files. Do not download substitutes into the public image, and do not rerun `python -m infralens.evaluation.final_holdout`.

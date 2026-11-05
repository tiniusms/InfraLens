# Docs

Capstone source-of-truth files live at the repository root (`PROJECT_CONTEXT.md`, `AGENTS.md`, `DECISIONS.md`, `TASKS.md`, `DATA_DICTIONARY.md`).

This folder is for supporting notes that are not yet promoted to root:

- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — implemented components and data flow
- [`../RISK_REGISTER.md`](../RISK_REGISTER.md) — measured failures and remaining limitations
- Evaluation and experiment notes
- [`../LITERATURE.md`](../LITERATURE.md) — verified source and methodology evidence index, not the complete APA portfolio
- `pjm_ltlf_inventory.md` — PJM Long-Term Load Forecast source inventory (original vs revision dates)
- `pjm_screening_schema.md` — zonal screening table; Slice 1 is 2025/2026 Table B1, Slice 2 is separate B-9 and B-9b series, plus the point-in-time zone-year view, with a display-only zone/state map
- `final_eia_holdout_external_evidence.md` — post-hoc external-factor memo; not a model input and not a rescore
- `finance.md` — annual electricity-cost identities; not a tariff, DCF, or PJM capacity adder
- `demo_walkthrough.md` — Streamlit launch, three-tab defense sequence, expected example values, and portable-mode limits
- `portable_deployment.md` — retained deployment template for a private Render service, Cloudflare Tunnel, and Vercel static shell, including the historical 2026-10-20 production state. Those hosts were decommissioned on 2026-11-03.
- `public_release_validation.md` — immutable October 20, 2026 public-release checklist, evidence table, hosting rollback notes, and cost notes. Not a live runbook.
- `infrastructure_decommission_2026_11_03.md` — November 3, 2026 hosting retirement, evidence boundaries, retained components, and redeployment prerequisites
- `version_2_charter.md` — owner-approved Version 2 charter, recorded verbatim and ratified in `DECISIONS.md` on 2026-11-05

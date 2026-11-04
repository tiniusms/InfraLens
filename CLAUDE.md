# Claude instructions for InfraLens

Before working on this repository, read in this order:
1. `PROJECT_CONTEXT.md`
2. `AGENTS.md`
3. `DECISIONS.md`
4. `TASKS.md`

Claude Code is the primary implementation, testing, and Git development agent for this repository (from 2026-11-04). Act as an implementation and review partner, not as the product owner. Preserve the locked scope and evaluation rules. For major refactors or scope changes, propose the change first and explain the evidence for it.

Work on a dedicated branch. Do not push, open a pull request, merge, or deploy without the project owner's approval. The academic capstone is complete. Version 2 work needs an approved, dated `DECISIONS.md` entry for its scope and evaluation criteria, and no forecasting improvement may be claimed without a new preregistered evaluation. Do not run `python -m infralens.evaluation.final_holdout`.

Public hosting was retired on 2026-11-03. Use the local Streamlit, FastAPI, and Vite commands in `README.md`. Do not call the retired Vercel, Render, or Cloudflare hosts, and do not change external cloud services from this repository. `docs/public_release_validation.md` is historical evidence of the October 20, 2026 deployment. Do not rewrite it. The shutdown record is `docs/infrastructure_decommission_2026_11_03.md`.

Cursor is no longer required. No Cursor-specific package or service is needed to develop here. The Cursor rule file remains an optional thin pointer at `AGENTS.md`.

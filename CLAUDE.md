# Claude instructions for InfraLens

Before working on this repository, read in this order:
1. `PROJECT_CONTEXT.md`
2. `AGENTS.md`
3. `DECISIONS.md`
4. `TASKS.md`

Claude Code is the primary implementation, testing, and Git development agent for this repository (from 2026-11-04). Act as an implementation and review partner, not as the product owner. Preserve the locked scope and evaluation rules. For major refactors or scope changes, propose the change first and explain the evidence for it.

Work on a dedicated branch. Do not push, open a pull request, merge, or deploy without the project owner's approval. The academic capstone is complete. Do not run `python -m infralens.evaluation.final_holdout`.

GitHub `main` is the authoritative committed baseline. Before any branch switch, reset, stash, or cleanup, inspect the working tree, untracked files, and existing stashes, and protect local work you did not create. Report a dirty tree instead of discarding it.

Version 2 follows `docs/version_2_charter.md`, ratified in `DECISIONS.md` on 2026-11-05 and merged into `main` as `77575d5` (pull request #9). Phase 1 (engineering foundation) is authorized under the acceptance criteria in `TASKS.md`. Phases 2–5 are not yet scoped and need owner approval before work starts. Each Phase 1 task still needs its own scoped branch, validation evidence, and owner review. Phase 3 forecasting performance claims, material financial assumptions (including discounted multi-year scenarios), new geography such as Texas/ERCOT, public deployment, and paid infrastructure each need a separate, dated decision. Keep the seasonal-naive and regularized-linear baseline comparisons.

Public hosting was retired on 2026-11-03. Use the local Streamlit, FastAPI, and Vite commands in `README.md`. Do not call the retired Vercel, Render, or Cloudflare hosts, and do not change external cloud services from this repository. `docs/public_release_validation.md` is historical evidence of the October 20, 2026 deployment. Do not rewrite it. The shutdown record is `docs/infrastructure_decommission_2026_11_03.md`.

Cursor is no longer required. No Cursor-specific package or service is needed to develop here. The Cursor rule file remains an optional thin pointer at `AGENTS.md`.

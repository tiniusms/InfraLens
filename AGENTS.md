# InfraLens - Instructions for AI Collaborators

Read `PROJECT_CONTEXT.md` and `DECISIONS.md` before proposing or implementing major changes.

## Priority order
1. Preserve the intended analyst decision and project scope.
2. Preserve point-in-time validity and prevent leakage.
3. Prefer reproducible evidence over model complexity.
4. Keep financial calculations deterministic and testable.
5. Keep changes small, reviewable, and inside scope approved in `DECISIONS.md`. The capstone deadline of October 25, 2026 has passed and the capstone is complete.

## Non-negotiable rules
- Do not change the target, geography, success criteria, or evaluation split without a dated entry in `DECISIONS.md`.
- Do not use data that would not have been available at the prediction date. Track publication lag and data vintage.
- Do not claim that feature importance or SHAP proves causality.
- Do not fabricate data for the demo.
- Do not hide negative experiments.
- Do not let an LLM calculate NPV, discounted costs, or other financial outputs. Use tested Python functions.
- Always compare advanced models with the seasonal-naive and regularized-linear baselines.
- Every model result must be reproducible from code and logged configuration.
- Every dashboard result must expose the data date, model version, and user assumptions.
- Avoid feature creep. New features must improve the intended analyst decision and fit scope approved in `DECISIONS.md`.

## Code expectations
- Python 3.11+.
- Type hints for reusable functions.
- Small, testable modules instead of one large notebook.
- Raw data is immutable; transformations write new artifacts.
- Store analytical datasets as Parquet and query through DuckDB where practical.
- Keep secrets in environment variables; commit `.env.example`, never credentials.
- Add tests for financial calculations, date/vintage logic, and core transformations.
- Use clear docstrings where domain meaning is not obvious.

## Evaluation expectations
- Time-ordered or rolling-origin validation only for forecasting.
- Final temporal holdout remains untouched until model selection is complete.
- Primary error metric: MAE, with additional normalized/percentage metric where valid.
- Report uncertainty coverage as well as interval width.
- Evaluate important slices by state and market regime.

## When uncertain
Do not silently invent assumptions. Record the ambiguity in `DECISIONS.md` or raise it to the project owner with a concrete recommendation.

## Local repository after public-hosting retirement
As of 2026-11-03 the supported runtime is this repository on a local machine. The October 20, 2026 Vercel, Render, and Cloudflare deployment was retired. Do not call those former hosts, do not treat `docs/public_release_validation.md` as a live runbook, and do not rewrite that file. Deployment templates remain for a future approved redeploy. The shutdown record is `docs/infrastructure_decommission_2026_11_03.md` and the 2026-11-03 entry in `DECISIONS.md`.

Claude Code and other standalone coding agents follow this file. They do not need Cursor-specific tooling to install, test, or edit the project. `.cursor/rules/infralens.mdc` repeats the same project rules for Cursor and stays in the tree.

## Development after the capstone (from 2026-11-04)
The academic capstone is complete. InfraLens continues as an independently developed AI infrastructure-analysis product. See the 2026-11-04 entry in `DECISIONS.md`.

- Claude Code is the primary implementation, testing, and Git development agent. Cursor is no longer required.
- Local development is the supported workflow. Public deployment remains retired.
- Work on a dedicated branch. Do not push, open a pull request, merge, or deploy without the project owner's approval.
- Version 2 work needs a dated `DECISIONS.md` entry that approves its scope and evaluation criteria before it starts.
- Do not claim a Version 2 forecasting improvement without a new preregistered evaluation. The 2026-10-04 final holdout stays closed and must not be reused for selection or tuning.
- Original capstone findings and dated decisions are historical records. Add new entries; do not rewrite earlier ones.

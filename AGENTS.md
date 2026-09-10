# InfraLens - Instructions for AI Collaborators

Read `PROJECT_CONTEXT.md` and `DECISIONS.md` before proposing or implementing major changes.

## Priority order
1. Preserve the intended analyst decision and project scope.
2. Preserve point-in-time validity and prevent leakage.
3. Prefer reproducible evidence over model complexity.
4. Keep financial calculations deterministic and testable.
5. Keep the project finishable by October 25, 2026.

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
- Avoid feature creep. New features must improve the intended analyst decision and be feasible within the capstone timeline.

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

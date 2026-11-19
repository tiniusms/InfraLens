<!--
Repository record. This comment is not part of the charter.
The text below is the owner-approved charter of 2026-11-05, recorded word for word.
Only Markdown structure was added (headings and list markers). Ratification is the
2026-11-05 entry in DECISIONS.md. Phase 1 acceptance criteria are in TASKS.md.
Do not edit the charter text; record later changes as new dated decisions.
Adoption: the ratification pull request #9 merged into `main` as `77575d5` on
2026-11-05. The "pending" status lines below are the approved text and stay unchanged.
-->

# InfraLens Version 2 — Project Charter

Status: Strategic scope approved by project owner; repository ratification pending

Approval date: November 5, 2026

Project: InfraLens

Repository: https://github.com/tiniusms/InfraLens

Primary development environment: Claude Desktop and Claude Code

Deployment: Local-only until separately authorized

## 1. Project Vision

InfraLens is an AI-assisted electricity and infrastructure intelligence platform intended to support data-center planning, energy-cost analysis, financial evaluation, and infrastructure-investment research.

Version 2 will transform the completed academic prototype into a more reliable, maintainable, and professionally useful analytical product.

The platform's distinguishing objective is to bring together electricity-price forecasts, power-system planning evidence, and transparent financial scenarios without obscuring the boundaries between historical data, predictions, screening indicators, and financial assumptions.

## 2. Project Background

InfraLens originated from research into the growing electricity requirements of AI data centers and their implications for infrastructure investment, electricity prices, and operational costs.

Version 1 established:

- A reproducible EIA-based forecasting and evaluation framework.
- A 12-month-ahead monthly commercial electricity-price forecasting problem.
- A seasonal-naive benchmark and an experimental Ridge model.
- A PJM infrastructure screening layer.
- Deterministic electricity-cost calculations.
- Streamlit, FastAPI, and React interfaces.
- Tests, architecture documentation, and historical validation evidence.

The final Version 1 forecasting evaluation did not meet its preregistered success criterion. These results are preserved permanently as historical evidence, and Version 2 will be developed through a new evaluation framework.

The public Vercel, Render, and Cloudflare deployment was intentionally retired on November 3, 2026.

## 3. Approved Strategic Priorities

InfraLens Version 2 will pursue balanced progress across four interconnected workstreams.

### A. Electricity-price forecasting

Improve forecasting reliability, data provenance, publication-aware evaluation, uncertainty estimation, and model comparisons.

Investigate alternative methods only when their complexity can be justified against established baselines.

### B. Infrastructure screening

Develop PJM planning-data screening into a more informative analytical capability covering load growth, data-center demand, source vintages, and appropriate geographic and temporal constraints.

Screening results must not be misrepresented as utility-interconnection approvals, confirmed service availability, or state-level electricity-price forecasts.

### C. Financial decision support

Extend deterministic annual electricity-cost calculations into multi-year scenarios, discounted comparisons, sensitivity analysis, and transparent risk and assumption reporting.

Clearly distinguish actual observations, user assumptions, hypothetical scenarios, and model-derived estimates.

### D. Product engineering

Improve automated testing, development environment consistency, API and frontend reliability, documentation, explainability, modularity, and future deployment portability.

## 4. Geographic Scope

The initial research region remains:

- Virginia (VA)
- Pennsylvania (PA)
- Ohio (OH)
- Maryland (MD)
- New Jersey (NJ)

The architecture may support expansion, but additional states, utility territories, markets, or planning regions require a separate scope decision and data-validity review.

## 5. Operating and Deployment Scope

Version 2 is initially local-only.

No paid cloud hosting, public API, production infrastructure, public-release claim, or domain purchase is authorized under this charter.

Local development may use existing tools, dependencies, and lawfully accessible public datasets. Material new expenses require approval.

Future deployment will be evaluated separately against product readiness, operating costs, security, reproducibility, and portfolio value.

## 6. Engineering and Scientific Governance

GitHub `main` is the authoritative committed baseline.

Claude Code serves as the primary development agent and must follow the repository's `CLAUDE.md`, `AGENTS.md`, and decision records.

Material changes require scoped work, a dedicated branch, validation evidence, and review before merging.

Historical Version 1 evidence, closed holdout results, source vintages, and release-validation records are preserved.

Any new forecasting evaluation must define its target, forecast origin, feature timing, data vintage, baselines, metrics, thresholds, evaluation period, and leakage protections before evaluation.

No new model-performance claim may rely on reuse of the closed Version 1 holdout for selection or tuning.

## 7. Success Criteria

Forecasting: A new preregistered protocol is approved before new performance claims. Candidate models are compared with appropriate baselines using leakage-safe data.

Infrastructure: Every material screening result carries source identification, vintage, geography, interpretation, and limitations.

Finance: Financial outputs are reproducible, unit-consistent, scenario-aware, and supported by deterministic tests.

Engineering: Existing regression coverage remains intact; automated CI and reproducible development workflows are strengthened.

Product quality: Users can distinguish evidence, predictions, assumptions, and uncertainty in outputs.

Numeric acceptance thresholds for individual milestones are not authorized by this charter alone. They must be established before the relevant development or evaluation activity.

## 8. Development Phases

Phase 1 — Engineering foundation: Repository governance, CI, reproducible environments, and technical-debt assessment.

Phase 2 — Data reliability: EIA vintage archival, provenance, availability timing, and PJM-source improvements.

Phase 3 — Forecasting development: Preregistered experimental design, candidate modeling, baseline comparison, uncertainty and robustness evaluation.

Phase 4 — Analytical expansion: Multi-year financial scenarios, sensitivity analysis, improved screening, and explainable outputs.

Phase 5 — Product refinement: User experience, integration quality, documentation, and readiness assessment for optional future deployment.

Development phases may overlap where dependencies are satisfied and owner-approved milestones are clearly defined.

## 9. Out of Scope

Initially excluded are automated investment decisions, trading, guarantees of power availability, unsupported PJM-to-state mappings, unauthorized use of proprietary data, changes to the frozen capstone evaluation, and paid public deployment.

## 10. Approval and Change Control

The project owner approves this charter's strategic emphasis, five-state scope, and local-only development policy.

Claude Code must record the charter in the repository through a dedicated branch and reviewed pull request before treating it as a committed governance decision.

Subsequent material changes to scope, evaluation methodology, architecture, or financial assumptions require separate approval and a dated decision record.

Strategic approval: Granted, November 5, 2026.

Repository adoption: Pending reviewed pull request.

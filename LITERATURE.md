# InfraLens literature and evidence index

## Scope and evidence status

This file is a repository evidence and methodology index. It points to primary-source registers already stored in git and to the documentation and code that implement seven methodological decisions.

It is not the complete Module 3–4 APA literature review, and it is not a substitute for the submitted academic portfolio. `PROJECT_CONTEXT.md` section 8 names this filename for annotated research notes and APA references. Section 12 names an APA research portfolio as part of a finished capstone. Those course materials are not the contents of this file.

The 18-source review and its five synthesis themes are known from prior coursework. Their complete bibliographic records have not been verified in this Git repository.

## Verified primary-source registers

The registers below are agency and primary-source evidence. They are not peer-reviewed scholarly references. This index links to them and does not copy their lists.

| Register | What it records |
| --- | --- |
| [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md), “References” | Three EIA source descriptions for the commercial retail-sales series: API metadata, an EIA FAQ title, and Electric Power Monthly Table 5.6.A. |
| [`docs/pjm_ltlf_inventory.md`](docs/pjm_ltlf_inventory.md), “Source inventory” | Numbered PJM load-forecast pages and files, items 1–15. Research snapshot 2026-09-28. |
| [`docs/final_eia_holdout_external_evidence.md`](docs/final_eia_holdout_external_evidence.md), “Source register” | Dated pages read on 2026-10-14 for the post-hoc memo. |

The memo’s heading is “POST-HOC EXTERNAL EVIDENCE — NOT USED FOR MODEL SELECTION.” Its opening calls the note post-hoc interpretation only. It prohibits the note from informing the closed model, the feature set, the penalty, the baseline, the interval rule, or the final-holdout evaluation, and it states that the note does not rescore that holdout.

## Scholarly-reference status

No complete scholarly bibliography is currently verified in this repository. This file does not add author-year records, DOIs, article titles, or a source count as if those details had been checked in git.

An eventual APA bibliography requires the actual Modules 3–4 submitted review, or its reference list, so each record can be checked before it is copied here.

## Literature-to-methodology-to-code traceability

Each row locates an implemented decision in existing documentation and code. A code path is implementation evidence. It is not academic validation. The scholarly cell stays unverified until a checked reference list is in the repository.

| Implemented decision | Repository evidence | Code | Scholarly record |
| --- | --- | --- | --- |
| Rolling-origin backtesting and a frozen final temporal holdout | `EVALUATION.md`, “Windows” (development expanding origins) and “Final holdout protocol (executed once on 2026-10-04)”. `DECISIONS.md`, 2026-09-30 and 2026-10-04. | `src/infralens/evaluation/backtest.py` (`run_expanding_backtest`); `src/infralens/evaluation/final_holdout.py` (`run_final_holdout`) | Not yet verified in this repository |
| m+3 data availability and current-vintage limitations | `EVALUATION.md`, “Availability date,” “Leakage rule,” and “What this evaluation is not.” `DECISIONS.md`, 2026-09-11 and 2026-09-14. | `src/infralens/data/availability.py` (`assumed_available_at`) | Not yet verified in this repository |
| Availability-adjusted seasonal-naive baseline and Ridge selection | `EVALUATION.md`, “Availability-adjusted seasonal-naive baseline,” “Regularized linear candidate (Ridge),” and “Development selection freeze.” `DECISIONS.md`, 2026-09-29. | `src/infralens/evaluation/baseline.py` (`availability_adjusted_seasonal_naive`); `src/infralens/evaluation/linear.py` (`run_ridge_backtest`); `src/infralens/evaluation/selection.py` (`FEATURE_SET_ID`) | Not yet verified in this repository |
| Histogram gradient boosting as a tested model that did not justify extra complexity | `EVALUATION.md`, “Histogram gradient-boosting candidate” and the “Development comparison” under that section. `DECISIONS.md`, 2026-09-29. `EXPERIMENTS.md`, 2026-09-28. | `src/infralens/evaluation/tree.py` (`run_tree_backtest`) | Not yet verified in this repository |
| Empirical absolute-residual intervals and measured holdout coverage | `EVALUATION.md`, “State-specific empirical absolute-residual intervals” and “Final holdout result (one-shot, 2026-10-04).” `DECISIONS.md`, 2026-09-30 and 2026-10-04. `EXPERIMENTS.md`, 2026-09-30 and 2026-10-04. | `src/infralens/evaluation/intervals.py` | Not yet verified in this repository |
| Exact Ridge coefficient contributions. These are linear contributions for one stored prediction. They are not causal interpretations, and they are not a Streamlit demo feature. | `EVALUATION.md`, “Ridge coefficient explanations.” `ARCHITECTURE.md`, section 3. `EXPERIMENTS.md`, 2026-09-30. | `src/infralens/evaluation/explain.py` (`explain_prediction`). `src/infralens/demo/app.py` does not import that module. | Not yet verified in this repository |
| Transparent final-holdout FAIL reporting without retuning | `EVALUATION.md`, “Final holdout result (one-shot, 2026-10-04).” `DECISIONS.md`, 2026-10-04. `RISK_REGISTER.md`, R1. `docs/final_eia_holdout_oneshot.json`. | `src/infralens/demo/foundation.py` (`load_holdout_banner`); `src/infralens/demo/app.py`; `src/infralens/evaluation/final_holdout.py` (`PRIMARY_RELATIVE_IMPROVEMENT`) | Not yet verified in this repository |

## Limitations and future reconciliation

The missing scholarly bibliography is a documentation gap in this repository. The Modules 3–4 review can be mapped into this index only after its reference list is present here and each record has been checked against that file. A checked reference can then be attached to one of the seven rows above.

The one-shot EIA holdout remains the closed FAIL recorded in `EVALUATION.md`, “Final holdout result (one-shot, 2026-10-04).” This index leaves that result, the feature set, the penalty, the baseline, the interval rule, and the evaluation protocol unchanged. It does not recommend a new model or a literature-driven retune.

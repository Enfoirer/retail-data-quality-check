# Implementation Plan: Retail SQL Reconciliation and Difference Localization

Each milestone produces a reviewable artifact and commit. The existing single-file CSV checker provides reusable validation capabilities.
Build the deterministic evidence workflow before adding model analysis. Total case-study effort must remain within four hours, including discussion and applicant review; earlier timer entries do not represent all effort.
All deliverables, including documentation, sample labels, reports, and code comments, use English.

| Step | Scope | Acceptance criteria | Status |
|---|---|---|---|
| 1 | Define shared data, two SQL pipelines, comparison semantics, and manual expectations | Explain the CNY 1,479 difference by hand; verify sample SQL locally | Complete |
| 2 | Implement job validation, CSV loading, and a staged SQLite executor | Execute both pipelines with one command, retain intermediate tables, and identify failed SQL steps | Complete |
| 3 | Implement query-aware metric, record, dimension, and checkpoint reconciliation | Identify filtered, I003, and Beijing's CNY 1,479 difference; distinguish dataset differences from query differences; inspect records even when totals match | Complete |
| 4 | Add a join-fanout case, rerun after correction, and generate evidence reports | Preserve duplicate keys, trace join matches, and verify filter/join corrections with unchanged sources | Complete |
| 5 | Add evidence-based AI analysis | Cite actual evidence, distinguish observations from hypotheses and recommendations, and retain computed reports if the model fails | Complete |
| 6 | Prepare submission artifacts and demonstration | Reproducible README; explanation of no more than four pages matching actual behavior; disclose time, AI, synthetic data, and limitations | Pending |

## Step 1: Establish comparison semantics

Fixture directory: `samples/reconciliation/filter_mismatch/`. See its [manual walkthrough](../samples/reconciliation/filter_mismatch/MANUAL_WALKTHROUGH.md) for the data dictionary, arithmetic, SQL explanation, and completed Step 1 acceptance checklist.

- Grain: one current snapshot per order line, uniquely identified by `order_item_id`. An order may contain multiple lines.
- Amount: original order amount in CNY. Cancelled orders may retain a positive original amount; the earlier net-movement convention does not apply.
- Business requirement: both final pipelines include only paid lines, and product enrichment preserves one row per order line.
- Execution: shared orders and products inputs, followed by filtering and a left join. The configuration explicitly aligns comparable checkpoints.
- Money loading: parse yuan amounts exactly and convert to integer minor units in `amount_cents`. Preserve the original amount as text; SQL aggregation does not rely on floating-point money.
- Comparison: differences consistently mean **B minus A**. The initial workflow compares results at the same order-line grain.
- Evidence boundary: the program establishes record and step differences. Judging a filter against requirements also requires the supplied business definition.

Step 1 delivers fixture inputs, SQL, a job description, and a manual answer key. A temporary SQLite run verified these fixtures. Step 2 now provides the reusable executor and CLI.

## Step 2: Execute and retain both pipelines

Run `python3 -m src.sql_runner samples/reconciliation/filter_mismatch/job.json` from the repository root. See [SQL_EXECUTOR.md](SQL_EXECUTOR.md) for artifacts, inspection commands, and failure behavior.

The executor validates the job, loads shared sources, materializes each stage, and retains run.sqlite plus execution.json in a new run directory. Twelve executor tests cover retained stages, independent answer keys, exact money, invalid jobs and inputs, checkpoint columns, query failures, cross-pipeline reads, source preservation, and output-directory protection. After Step 5, the full suite contains 68 passing tests.

## Step 3: Reconcile the user request and trace differences

Run `python3 -m src.reconcile samples/reconciliation/filter_mismatch/job.json`. See [RECONCILIATION.md](RECONCILIATION.md) for query configuration, status meanings, CSV outputs, and limits.

The common query supports explicit filters and grouping over retained detail outputs. The engine reports grouped results separately from record equality, tracks raw and query-scoped checkpoint differences, preserves ambiguous keys, and explains unique-key amount differences. A paid-only query variant demonstrates that dataset differences may not affect a particular request. Fourteen new tests cover these behaviors and invalid/error cases.

## Step 4: Diagnose fanout and verify corrections

Run `python3 demo_reconciliation.py` to generate before/after reports for filter and join defects, with unchanged source-file hashes. See [JOIN_DIAGNOSTICS.md](JOIN_DIAGNOSTICS.md) for supported observations and evidence tracing.

The history-table fixture expands I001 from one row to two when B omits the current-version lookup. Diagnostics retain both right matches and both output copies, with SQL and SQLite row IDs. Correcting the declared join target restores equality without deleting history. Every run has a readable report and an evidence ledger whose JSON pointers are verified in tests. Eleven new tests cover the cases, uncertainty boundaries, retained rows, source equality, and report provenance.

## Step 5: Explain evidence with an optional model

Run the reconciliation command with --ai, or analyze a completed reconciliation.json with `python3 -m src.ai_analysis`. See [AI_ANALYSIS.md](AI_ANALYSIS.md) for setup and the output contract, and [AI_EVALUATION.md](AI_EVALUATION.md) for real model evaluation.

The adapter sends a checked projection of requirements, SQL, and computed evidence to the OpenAI Responses API. Structured output separates observations, hypotheses, and human verification steps. Local validation checks actual evidence IDs, exact paths/values, and unchanged deterministic status; it does not establish semantic entailment. Requests, raw responses, validation outcomes, and readable analyses are retained. Model errors and invalid responses preserve the computed report. Seventeen new offline tests cover this boundary. No runtime mock or automatic repair is implemented.

## Subsequent implementation conventions

Resolve paths relative to the job JSON directory and materialize explicitly provided steps. Load base tables once into the same retained SQLite database for both pipelines.
The job's schema_version 1 is a new configuration format, independent of the existing single-file report version.

Always include record-level checks. Determine the first observed divergence using the declared checkpoint order; it does not automatically establish the business root cause.
Preserve duplicate keys and report matching ambiguity. Do not overwrite duplicates in a dictionary and report equality. Join diagnostics use explicit join descriptions and observed results; arbitrary SQL parsing is outside the initial scope.

The implemented AI feature explains generated evidence together with supplied SQL and business requirements. The default model is gpt-5-mini, configurable by environment or CLI. Step 6 still needs a concise final submission matching the completed workflow, applicant review, and an honest total-time declaration.

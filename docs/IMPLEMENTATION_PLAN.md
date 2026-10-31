# Implementation Plan: Retail SQL Reconciliation and Difference Localization

Each milestone produces a reviewable artifact and commit. The existing single-file CSV checker provides reusable validation capabilities.
Build the deterministic evidence workflow before adding model analysis. Total case-study effort must remain within four hours, including discussion and applicant review; earlier timer entries do not represent all effort.
All deliverables, including documentation, sample labels, reports, and code comments, use English.

| Step | Scope | Acceptance criteria | Status |
|---|---|---|---|
| 1 | Define shared data, two SQL pipelines, comparison semantics, and manual expectations | Explain the CNY 1,479 difference by hand; verify sample SQL locally | Complete |
| 2 | Implement job validation, CSV loading, and a staged SQLite executor | Execute both pipelines with one command, retain intermediate tables, and identify failed SQL steps | Complete |
| 3 | Implement metric, record, dimension, and checkpoint reconciliation | Identify checkpoint filtered, item I003, and Beijing's CNY 1,479 difference; inspect records even when totals match | Pending |
| 4 | Add a join-fanout case, rerun after correction, and generate evidence reports | Preserve duplicate keys, show join-match counts, and demonstrate zero differences after correcting the filter | Pending |
| 5 | Add evidence-based AI analysis | Cite actual evidence, distinguish observations from hypotheses and recommendations, and retain computed reports if the model fails | Pending |
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

The executor validates the job, loads shared sources, materializes each stage, and retains run.sqlite plus execution.json in a new run directory. Twelve executor tests cover retained stages, independent answer keys, exact money, invalid jobs and inputs, checkpoint columns, query failures, cross-pipeline reads, source preservation, and output-directory protection. The full suite contains 26 passing tests. Step 3 reconciliation and Step 5 AI are still pending.

## Subsequent implementation conventions

Resolve paths relative to the job JSON directory and materialize explicitly provided steps. Load base tables once into the same retained SQLite database for both pipelines.
The job's schema_version 1 is a new configuration format, independent of the existing single-file report version.

Always include record-level checks. Determine the first observed divergence using the declared checkpoint order; it does not automatically establish the business root cause.
Preserve duplicate keys and report matching ambiguity. Do not overwrite duplicates in a dictionary and report equality. Join diagnostics use explicit join descriptions and observed results; arbitrary SQL parsing is outside the initial scope.

The initial AI feature explains generated evidence together with supplied SQL and business requirements. Choose the provider, model, and invocation method in Step 5; no runtime model is integrated yet.

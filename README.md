# Retail SQL Reconciliation and Evidence-Based Investigation

A runnable case-study prototype: execute two explicit SQL pipelines over shared retail snapshots, compare a common user query, trace discrepancies to retained stages and records, and optionally ask a model for a cited interpretation. All input data and supplied corrections are synthetic. No employer data, code, credentials, or warehouse connection is included.

## Start here

- Written explanation: [four-page PDF](output/pdf/CASE_STUDY.pdf), with editable [Markdown source](docs/CASE_STUDY.md).
- Interview walkthrough: [15-minute demonstration](docs/DEMO.md).
- Source package: `python3 scripts/package_submission.py` builds a ZIP from [an explicit file list](submission_manifest.json).

Python **3.10+**. Developed and verified on Python 3.13.7. The deterministic prototype and tests use only the standard library: no installation, API key, paid service, or production account is required. From the repository root:

```sh
python3 demo_reconciliation.py
python3 -W error::ResourceWarning -m unittest discover -s tests -q
```

The demo exits **0** when its expected outcomes are verified. It executes both before/after corrections, the paid-only query, and a deliberately invalid SQL example. It creates a fresh directory under outputs/ and prints report paths plus a demo-summary.json. Existing run directories are protected against overwrite.

Expected summary:

```text
filter_mismatch: DIFFERENT -> MATCH; difference 147900 -> 0 cents; source files unchanged=True
join_fanout: AMBIGUOUS -> MATCH; difference 10000 -> 0 cents; source files unchanged=True
paid_query: MATCH; raw divergence=filtered; query-scope divergence=none
invalid_sql: ERROR; failed pipeline=B; step=filter (expected controlled failure)
```

## Individual inputs and expected outcomes

| Job under samples/reconciliation/ | Expected finding | Exit |
|---|---|---:|
| filter_mismatch/job.json | I003 exists only in B; Beijing differs by CNY 1,479; first divergence is filtered | 1 |
| filter_mismatch/job-fixed-filter.json | Supplied paid-only filter correction restores MATCH | 0 |
| join_fanout/job.json | Two product versions duplicate I001; CNY 100 difference; grain is AMBIGUOUS | 2 |
| join_fanout/job-fixed.json | Join the prepared current-products table; MATCH, all source history retained | 0 |
| filter_mismatch/job-paid-query.json | Paid-only query MATCH; raw dataset difference remains visible | 0 |
| filter_mismatch/job-invalid-sql.json | Controlled ERROR at B/filter; completed A tables retained | 2 |

Run an individual job with:

```sh
python3 -m src.reconcile samples/reconciliation/filter_mismatch/job.json
```

Nonzero exits above are expected findings, not failed setup. MATCH means configured scoped groups and detail fields agree, not universal business correctness. AMBIGUOUS preserves duplicate/missing keys. ERROR identifies an execution or comparison failure. Execution-only `python3 -m src.sql_runner JOB` is also available; its SUCCESS does not mean reconciliation passed.

## What runs and what is retained

JSON job + shared CSV snapshots + staged SQL -> retained SQLite tables -> query/detail/checkpoint comparisons -> declared-join diagnostics -> evidence reports -> optional AI interpretation.

The job declares keys, integer-cent amount semantics, dimensions, aligned checkpoints, common filters/grouping, and optional join expectations. Source preflight reuses the configurable checker from this same exercise. Original amount text is retained; exact parsing produces integer cents, and comparison aggregation uses Python integers. Differences mean **B minus A**. SQL fixtures use original CNY order amounts; a cancelled snapshot may retain a positive amount.

| Per-run artifact | Purpose |
|---|---|
| report.md / evidence.json | English evidence report and IDs linked to exact saved JSON values |
| run.sqlite / execution.json | Shared sources, successful intermediate tables, actual SQL, read dependencies, and failures |
| reconciliation.json / differences/*.csv | Raw/scoped comparisons, grouped metrics, key/value differences, and preserved grain issues |
| ai/analysis.md and JSON files, when requested | Separate interpretation, request/response, and local validation status |

SQL and configuration must be explicitly provided. The program does not infer arbitrary SQL lineage, choose duplicate winners, or execute proposed repairs. Corrected SQL files are manually supplied synthetic acceptance variants. expected.json files are manual answer keys; the runtime does not load them.

## Optional real-model analysis

Install the optional dependency and set OPENAI_API_KEY in your environment, then run:

```sh
python3 -m pip install -r requirements-ai.txt
python3 -m src.reconcile samples/reconciliation/join_fanout/job.json --ai
```

Default: gpt-5-mini. Override with OPENAI_MODEL or --ai-model. The model receives supplied requirements, actual SQL, and checked evidence. Output separates observations, hypotheses, and verification suggestions. Local checks reject unknown evidence IDs, false anchor values, hidden paths, and changed deterministic statuses. Correct citations do not guarantee justified prose: human review remains necessary.

Missing credentials/SDK, provider errors, refusals, or invalid output leave the deterministic report available. AI status is printed separately and does not change the computed reconciliation exit code. See [AI setup and failures](docs/AI_ANALYSIS.md) for standalone/retry commands. [Actual captured calls](samples/ai_analysis/README.md) can be inspected without an account; they are recorded examples, never runtime fallback answers. [Evaluation notes](docs/AI_EVALUATION.md) include rejected attempts and remaining semantic weaknesses.

## Verification and submission package

The **71 offline tests** cover exact money, query masking, equal totals with unequal details, retained duplicate keys, declared-join uncertainty, failed-step evidence, source preservation, rejected model citations, and package boundaries. Offline AI tests use clearly labeled injected providers; the normal application uses a real provider when --ai is requested.

```sh
python3 scripts/package_submission.py
```

The ZIP and package-audit.json are written under outputs/submission/. Packaging requires the included PDF and copies only files listed in submission_manifest.json; each entry is hashed in CONTENTS.json. It excludes local working notes, credentials, .git history, caches, and generated run directories. The package includes source, tests, sample inputs/expectations, setup instructions, the written explanation, and demonstration guidance. Existing ZIP destinations are not overwritten; use --output with a new path for another package.

The PDF is already included. To rebuild it, separately install requirements-docs.txt and run `python3 scripts/build_submission.py`; this is not required to run the prototype. The builder fails if content exceeds the four-page layout.

## Decisions, limits, and disclosure

This is an inspectable local workflow for small datasets. Explicit checkpoint alignment, a common detail grain/currency, and supplied business definitions are assumptions. General SQL decomposition, warehouse/catalog adapters, a UI, automatic repair, AI contract drafting, and large-data performance are deferred. Existing warehouse checks may be the better production solution; usefulness and review-time savings are unmeasured.

Codex assisted with planning, implementation, synthetic fixtures, tests, documentation, and review. No prior project code was reused; preflight code was built earlier within this exercise. Optional runtime AI is separate from development assistance. See the [time disclosure](docs/TIME_DISCLOSURE.md) for measured sessions and the applicant's approximately 30 minutes of review, with unrecorded discussion explicitly acknowledged.

Technical references: [query semantics](docs/RECONCILIATION.md), [executor](docs/SQL_EXECUTOR.md), [join diagnostics](docs/JOIN_DIAGNOSTICS.md), and [supporting preflight contracts](docs/PREFLIGHT.md).

# Fifteen-Minute Prototype Walkthrough

Run from the extracted source-package root with Python 3.10+. The core demonstration is fully offline and needs no dependencies or account. All data and supplied corrections are synthetic. For a repeat run, choose a new directory or omit --output-dir to receive a fresh timestamped path.

## Minutes 0-2: State the problem and execute the workflow

Explain the shared-source / different-pipeline problem and the supplied paid-only, one-row-per-order-line requirement. Then run:

```sh
python3 demo_reconciliation.py --output-dir outputs/interview-demo-1
```

The command should exit 0 after verifying four demonstrations. Intentionally DIFFERENT, AMBIGUOUS, and ERROR cases are expected parts of that verified demo. Open outputs/interview-demo-1/demo-summary.json and the report paths it records.

## Minutes 2-5: Explain the representative filter discrepancy

Open filter_mismatch-before/report.md and its evidence.json. Show A's paid-only filter versus B's paid-or-cancelled filter. Follow I003 and the Beijing +147900-cent difference. Open filter_mismatch-after/report.md: the supplied filter correction produces MATCH with unchanged source hashes. Explain that a difference is not itself business truth; the supplied requirement identifies the expected behavior.

## Minutes 5-8: Inspect the difficult join case

Open join_fanout-before/report.md. Both pipelines prepare current products; A reads its prepared table, while B reads all product history. I001 has two matching product versions and two output copies. The result remains AMBIGUOUS, and the original source history remains retained. Show both right records and their SQLite row IDs in evidence.json. Open join_fanout-after/report.md to show the corrected target and zero difference.

The fixes are supplied SQL variants, not model-generated or automatically applied changes. The source hashes in demo-summary.json prove that this demo did not alter the CSV inputs, not that an arbitrary production repair is correct.

## Minutes 8-10: Show query scope and controlled failure

Open paid-query/report.md. The common paid-only user request returns MATCH while raw datasets still disagree at filtered. Explain why a matching query does not make the datasets interchangeable.

Open invalid-sql/report.md and execution.json. The deliberately invalid B/filter query references missing_status. The program identifies the failed step and retains completed A tables. It does not compare partial results and label them MATCH. To inspect retained tables using only Python:

```sh
python3 - <<'PY'
import sqlite3
from contextlib import closing
with closing(sqlite3.connect('outputs/interview-demo-1/invalid-sql/run.sqlite')) as db:
    print(db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall())
PY
```

## Minutes 10-13: Inspect AI reasoning and its limits

With the optional dependency and your own configured API credential, run:

```sh
python3 -m src.reconcile samples/reconciliation/join_fanout/job.json --ai
```

The expected reconciliation exit is 2 because keys are AMBIGUOUS, even when AI succeeds. Open the printed ai/analysis.md and follow an evidence ID, /data pointer, and exact value back to evidence.json. Show observations, hypotheses, and human verification steps. No model suggestion is executed.

Without credentials, inspect samples/ai_analysis/live-evaluation.json and docs/AI_EVALUATION.md. These are actual saved calls, not an offline runtime model. A missing API key produces UNAVAILABLE and preserves the deterministic report. Explain the remaining limitation: a valid citation can still accompany an unjustified sentence. The local checks cannot establish semantic entailment.

## Minutes 13-15: Verify and discuss adaptation

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -q
```

Expect 71 passing tests, with no network calls. Show the explicit JSON job, the staged SQL, and where scope, key, or requirement changes belong. Explain the alternative of warehouse-native checks and the evidence needed before adopting this standalone workflow. Discuss a changed requirement without assuming the existing fix remains correct.

If asked to change behavior live, edit a copy or an explicitly selected configuration, run into a new output directory, and inspect both raw and query-scoped effects. No UI, general lineage discovery, warehouse integration, automatic repair, or production-scale guarantee is implemented.

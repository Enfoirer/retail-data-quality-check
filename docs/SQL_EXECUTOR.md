# Step 2: Staged SQL Executor

The executor loads shared CSV sources into a local SQLite database, runs both explicitly configured pipelines, and retains every successful stage. Python 3.10+ and the standard library are sufficient.

## Run both pipelines

From the repository root:

```sh
python3 -m src.sql_runner samples/reconciliation/filter_mismatch/job.json
```

The default creates a new timestamped directory under outputs. To choose the directory explicitly:

```sh
python3 -m src.sql_runner samples/reconciliation/filter_mismatch/job.json --output-dir outputs/step2-run
```

An explicitly selected directory must not already exist, even if empty. Use a new path for another run; previous runs are never overwritten. Paths inside the job resolve relative to the job file, independently of the current working directory.

Expected console output includes:

```text
Loaded orders: 3 rows
Loaded products: 3 rows
A/filter -> a_filtered: 2 rows
A/enrich -> a_enriched: 2 rows
B/filter -> b_filtered: 3 rows
B/enrich -> b_enriched: 3 rows
EXECUTION SUCCESS: both pipelines ran; reconciliation is not evaluated.
```

The command prints the actual database and report paths. Exit code 0 means execution succeeded. Exit code 2 means configuration, input, SQL, or artifact creation failed. A successful run does not establish that the two results agree or meet business requirements. Use the [Step 3 reconciliation command](RECONCILIATION.md) to compare a common filtered/grouped request and its underlying details.

## Retained artifacts

| Artifact | Contents |
|---|---|
| run.sqlite | orders, products, a_filtered, a_enriched, b_filtered, and b_enriched |
| execution.json | Job configuration, source validation, loaded schemas and row counts, actual SQL text and paths, read dependencies, stage timestamps/status, and failure context |

Each source and step is committed separately. If a later step fails, earlier completed tables remain available; the failed output is rolled back. A failed execution is explicitly marked FAILED in execution.json. Errors detected before a new run directory can be created, such as an invalid job or an existing output directory, are printed directly without creating new artifacts.

Source snapshots are loaded once per run into the same database and used by both pipelines. A pipeline can read the shared sources and its own earlier outputs. Cross-pipeline reads are rejected so B cannot silently reuse A's intermediate results.

The engine does not read expected.json. That file remains an independent manual acceptance reference.

## Inspect an intermediate result

After running with --output-dir outputs/step2-run:

```sh
python3 - <<'PY'
import sqlite3
from contextlib import closing

with closing(sqlite3.connect('file:outputs/step2-run/run.sqlite?mode=ro', uri=True)) as db:
    for table in ('a_filtered', 'b_filtered', 'a_enriched', 'b_enriched'):
        rows = db.execute(
            f'SELECT order_item_id, status, amount_cents FROM {table} ORDER BY order_item_id'
        ).fetchall()
        print(table, rows)
PY
```

A stages contain I001 and I002. B stages additionally contain I003, whose original amount is 147900 minor units.

## Failure behavior

For example, a missing column in B's enrichment SQL produces an error shaped like:

```text
FAILED at pipeline B, step enrich: no such column: missing_field
File: .../sql/b_enrich.sql
Database: .../run.sqlite
Report: .../execution.json
```

The report identifies pipeline B, step enrich, output b_enriched, the SQL file, SQL text if readable, and the database error. The successful a_filtered, a_enriched, and b_filtered tables remain inspectable. Missing or empty SQL files also include pipeline and step context.

Automated failure examples run on temporary copies of the fixture:

```sh
python3 -m unittest discover -s tests -p test_sql_runner.py -v
```

## Configuration and input guarantees

- Require job schema version 1, two nonempty pipelines named A and B, unique output names, and ordered checkpoint references.
- Reject unknown configuration keys, duplicate JSON keys, unavailable declared join inputs, and inconsistent join-key lists.
- Restrict table/column names to ASCII identifiers and reject case-only name collisions.
- Read UTF-8 CSV, preserve source fields as trimmed text, and reject malformed record widths or duplicate headers.
- Run any configured existing source contract before loading. BLOCK or REVIEW stops the source; full findings remain in the execution report. An uncontracted source can be header-only, but structural checks still apply.
- Derive the configured integer money column exactly, accepting at most two decimal places and checking SQLite's signed 64-bit range. Original amount text remains available.
- Materialize one query per SQL file. Statements that mutate sources and multi-statement SQL scripts are not accepted by the CREATE TABLE AS execution interface.
- Verify that materialized checkpoint outputs contain the configured comparison columns.

The job's join declaration is retained for [Step 4 diagnostics](JOIN_DIAGNOSTICS.md); this milestone does not verify cardinality or infer whether a join is correct. The execution-only command does not reconcile output values or metrics; the separate Step 3 command does. Large datasets, arbitrary SQL decomposition, runtime AI, and automatic SQL repair remain outside Step 2.

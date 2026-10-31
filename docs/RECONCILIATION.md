# Step 3: Query-Aware Reconciliation

Compare a common user request over two datasets, then inspect explicitly aligned pipeline checkpoints. All inputs are synthetic; the engine computes results without an AI model or the manual expected.json answer key.

## Run the representative discrepancy

From the repository root:

```sh
python3 -m src.reconcile samples/reconciliation/filter_mismatch/job.json
```

This runs the Step 2 executor and analyzes the resulting SQLite snapshot. The default creates a new timestamped output directory. Use --output-dir with a new path to choose it explicitly.

Expected result:

```text
RECONCILIATION: DIFFERENT
Final query groups: DIFFERENT; scoped details: DIFFERENT
First raw divergence: filtered
First query-scope divergence: filtered
filtered: DIFFERENT; A=30000 cents; B=177900 cents; B-A=147900 cents
enriched: DIFFERENT; A=30000 cents; B=177900 cents; B-A=147900 cents
```

The final Beijing group differs by CNY 1,479. I003 is present only in B after filtering. The amount explanation accounts for the full difference through this record; enrichment introduces no additional difference. A business judgment still requires the supplied paid-only requirement.

## A user query can mask a dataset difference

Run the same datasets with an additional paid-only query filter:

```sh
python3 -m src.reconcile samples/reconciliation/filter_mismatch/job-paid-query.json
```

Expected result: MATCH, raw divergence at filtered, and no query-scope divergence. The extra cancelled record remains in B's dataset, but this particular user request excludes it. This does not establish that the datasets are interchangeable for other queries.

## Query request configuration

The optional query object applies the same request to both datasets:

```json
{
  "query": {
    "filters": [
      {"column": "order_date", "operator": "eq", "value": "2026-10-01"}
    ],
    "group_by": ["province"]
  }
}
```

Filters are combined with AND. Supported operators are eq, in, gte, and lte. The in operator requires a nonempty list; other operators accept a string or integer. Values are bound as SQL parameters, not SQL fragments. Money filters use integer minor units. Source fields are text, so range filters on source dates rely on the declared ISO format and its lexical ordering.

Filter columns must be included in the comparison contract and available at every aligned checkpoint. Grouping uses a subset of configured dimensions; an empty group_by produces a scalar aggregate. Without query, use no filters and group by the configured dimensions.

The query layer applies parameterized SQLite filters to retained detail tables, then computes exact integer sums, row counts, and distinct valid-key counts in Python. It supports this defined request format, not arbitrary user SQL, custom expressions, HAVING, or different requests on A and B. Dataset-processing SQL remains explicit in pipeline files. The execution-only sql_runner command records query metadata but does not perform this query or reconciliation.

## Three comparisons with different meanings

| Report section | Meaning |
|---|---|
| checkpoints[].raw | Compare all configured detail fields before applying this user request |
| checkpoints[].query_scope | Reapply this request's filters to each aligned checkpoint and compare its detail records |
| query_result | Compare final scoped records grouped by the request's dimensions using amount, row count, and distinct-key count |

The final checkpoint must reference the final outputs of both pipelines. Steps are compared only when explicitly aligned; no automatic SQL decomposition or general lineage inference occurs.

The report separately records first_raw_divergence and first_query_scope_divergence. An intermediate difference can disappear later, or a user filter can exclude it. These fields identify observed differences, not a proven causal chain. Reapplying filters at checkpoints is a diagnostic operation, not arbitrary SQL predicate pushdown or row-level lineage reconstruction.

Configured dimension breakdowns show independent views of the same records. Groups are ranked by absolute amount difference within each breakdown; do not add contributions across different dimensions.

## Status and exit codes

| Status | Meaning | CLI exit code |
|---|---|---:|
| MATCH | Final query groups and configured scoped details agree | 0 |
| DIFFERENT | Final groups or configured scoped details differ | 1 |
| AMBIGUOUS | Final scoped keys are duplicated or missing, preventing reliable one-to-one detail matching | 2 |
| ERROR | Execution, output schema/value validation, or artifact generation failed | 2 |

query_result.status and detail_status are reported separately. For example, two offsetting amount changes can leave all query aggregates equal while details differ; the overall result remains DIFFERENT. Duplicate keys can also produce equal aggregates, but overall status is AMBIGUOUS. Neither MATCH nor DIFFERENT alone establishes business correctness.

Missing or blank keys are retained and reported. Duplicate groups preserve all rows and multiplicities; no keep-first/keep-last resolution is applied. Where matching is ambiguous, the engine does not provide a complete monetary attribution. For valid unique keys, only-in-A, only-in-B, and shared-key amount changes explain the signed B-minus-A difference.

All compared amounts must be integer minor units. NULL, REAL, or TEXT amount outputs fail explicitly, even if SQL execution succeeded. Aggregates use Python integers and do not silently convert to floating point. This prototype assumes one comparable currency and amount definition; it performs no currency conversion or semantic normalization.

## Artifacts

| File | Contents |
|---|---|
| run.sqlite | Shared inputs and retained SQL stage tables |
| execution.json | Actual job, SQL, dependencies, schemas, and execution outcomes |
| reconciliation.json | Query groups, raw/scoped checkpoints, dimensions, key differences, duplicate/missing keys, and amount explanations |
| differences/only_in_a.csv | Final scoped records whose valid key exists only in A |
| differences/only_in_b.csv | Final scoped records whose valid key exists only in B |
| differences/value_mismatch.csv | Unambiguous shared keys with changed configured fields, before/after records, and amount deltas |
| differences/grain_issues.csv | Final scoped duplicate or missing keys with preserved records |
| differences/query_groups.csv | Final grouped comparison |
| differences/checkpoints.csv | Raw and scoped checkpoint metrics and statuses |

Structured cells in CSV are JSON encoded. Empty difference files still contain headers. Earlier checkpoint record details remain available in reconciliation.json. If execution fails, reconciliation.json records ERROR and links the execution failure instead of comparing partial data. Reconciliation reads the retained SQLite database in read-only mode.

## Verification and limitations

The full suite has 40 passing tests. Fourteen reconciliation tests cover manual expected results, query masking, corrected equality, offsetting changes, replaced keys with equal totals, duplicate and missing keys, empty scopes, invalid amount types, parameterized/range/membership filters, invalid query definitions, execution failures, backward-compatible jobs, and CLI exit codes.

Records and groups are retained in memory for small demonstration batches. Filters are limited to fields available at every checkpoint. Arbitrary aggregate SQL lineage, scale benchmarks, join-match diagnosis, a human-readable evidence report, and runtime AI remain later work. Step 4 adds a dedicated join-fanout scenario and richer diagnostic evidence; Step 5 adds model analysis.

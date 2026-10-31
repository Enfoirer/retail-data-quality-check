# Step 4: Join Fanout, Correction, and Traceable Reports

The reconciliation command diagnoses declared joins and produces a readable English evidence report. Diagnostics never delete, merge, or choose a winning duplicate row. Step 5 optionally interprets this evidence using a model; see [AI_ANALYSIS.md](AI_ANALYSIS.md).

## Run both before/after demonstrations

```sh
python3 demo_reconciliation.py
```

The demo creates a new timestamped output directory. To choose a new directory explicitly:

```sh
python3 demo_reconciliation.py --output-dir outputs/my-correction-demo
```

Expected summary:

```text
filter_mismatch: DIFFERENT -> MATCH; difference 147900 -> 0 cents; source files unchanged=True
join_fanout: AMBIGUOUS -> MATCH; difference 10000 -> 0 cents; source files unchanged=True
```

Each case has separate before/after execution directories. The demo compares source paths and SHA-256 hashes before and after running both configurations. demo-summary.json records outcomes, hashes, and report locations. Exit 0 means both controlled corrections verified; exit 2 means verification or execution failed. A pre-existing output directory is never overwritten.

The corrections are manually supplied SQL/configuration variants based on the synthetic business requirements. They are not AI-generated or automatic repairs.

## Difficult example

The join_fanout fixture retains product history, including two versions of P01. Both pipelines first retain paid orders and create a current-product lookup. A uses that lookup; B mistakenly joins the full history.

- Before enrichment: both have two lines totaling CNY 300.
- After enrichment: A has two lines/CNY 300; B has three lines/CNY 400.
- I001 has one left row, two matching right versions, and two retained output copies.
- The first observed difference is enriched; B's final key is duplicated, so overall status is AMBIGUOUS.
- The corrected B SQL joins b_products_current. Both outputs then have two lines/CNY 300 and status MATCH.
- Both runs retain all four product history source rows, including the old version. The faulty run also retains both duplicate output rows.

The filter_mismatch correction independently changes B's filter to paid-only. Its CNY 1,479 difference becomes zero using the same source files.

## How a declared join is diagnosed

For every successful step with join metadata:

1. Check that declared left/right tables were observed SQL read dependencies.
2. Confirm that declared equality keys, business keys, and amount columns exist.
3. Inspect retained left and output rows; report their counts and integer amount sums.
4. Use SQLite equality joins to retrieve actual matching right rows for each left row, preserving NULL comparison semantics.
5. Match output multiplicities using the declared business key. If left business keys are already missing or duplicated, withhold per-record attribution.
6. Compare observed copies with right-match counts and the declared simple left-join model. Separately check whether copied amounts were preserved.

The diagnostic records actual SQL text, file path, read dependencies, matching SQL, matched values, and physical row IDs within this run.sqlite snapshot.

| Diagnostic status | Meaning |
|---|---|
| FANOUT | A business key expands in the retained output and has matching multirow right-side evidence under the declared keys |
| PASS | No observed many-to-one cardinality violation for the matched left records; this is not a general correctness verdict |
| INCONCLUSIVE | Metadata, available columns, pre-existing duplicate keys, or observed output do not establish the declared simple model |

A global row-count increase is insufficient evidence by itself. Expansion of one key can be offset by another key disappearing. Conversely, duplicate right keys that are never matched do not demonstrate output fanout. Extra SQL predicates can restrict a raw right table with duplicate keys to one match; diagnostics report model uncertainty rather than claiming observed fanout.

The diagnostic does not parse arbitrary SQL or prove that supplied key metadata fully represents its predicates. A matching count model supports investigation, not a causal guarantee. row_model_matches and replication_amount_model_matches expose the strength and limits of the observation. Amount changes beyond replication are not attributed automatically.

Diagnostics cover raw stages. The overall reconciliation status still concerns the final scoped comparison; a raw warning can involve records excluded by the user's query.

## Evidence artifacts

Each reconciliation run, including a failed execution, produces:

| File | Purpose |
|---|---|
| report.md | Readable requirement, query results, checkpoint trace, differences, join observations, SQL, and evidence index |
| evidence.json | Evidence IDs, copied data, source artifact names, and exact JSON pointers |
| reconciliation.json | Computed raw/scoped comparisons, grain issues, join diagnostics, and artifact paths |
| execution.json | Actual SQL, job configuration, read dependencies, and execution outcomes |
| run.sqlite | Original loaded snapshots and all successful materialized stages |

Difference CSVs are also retained for successfully analyzed runs. Evidence IDs are local to a run. For example, an item may reference reconciliation.json at /join_diagnostics/1. Its captured right rows can be checked directly in the retained products table using their sqlite_rowid values. These physical IDs are meaningful only in that particular run database, and are accompanied by full row values and business keys.

Tests resolve every evidence pointer back to the saved JSON value and verify traced right rows against SQLite. Source SQL is copied into execution.json, so later edits to an original SQL file do not rewrite the run evidence.

## Verification

The complete suite has 68 passing tests after Step 5. Eleven Step 4 tests cover:

- Fanout, correction, retained history/duplicates, and source-snapshot equality.
- Exact evidence pointer resolution and report contents.
- Failed-execution evidence reports.
- Both correction demos and unchanged source hashes.
- NULL join keys and unused duplicate right keys.
- Additional right predicates that prevent actual fanout.
- Per-key fanout with no net row-count increase.
- Pre-existing duplicate left keys.
- Declared inputs inconsistent with observed read dependencies.
- Non-JSON trace types reported as inconclusive instead of breaking report serialization.

These are small local fixtures. Per-left-row matching prioritizes inspectable evidence; scale optimization, general SQL lineage, and automatic repairs remain deferred. Optional model interpretation preserves the deterministic evidence and requires human review.

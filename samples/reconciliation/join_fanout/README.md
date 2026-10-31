# Difficult Case: Product History Join Fanout

All data, requirements, and SQL are synthetic. This case demonstrates diagnosis and a requirement-based SQL correction, not automatic deduplication.

## Business contract

Each order line is a current snapshot identified by order_item_id. Final results include paid lines only. Product history intentionally retains older versions. Exactly one version per product is current in this fixture, and enrichment must use that version while preserving each order line and its original CNY amount.

## Input and logic

orders.csv contains paid I001 (P01, CNY 100) and I002 (P02, CNY 200), plus cancelled I003. Both pipelines filter out I003. products.csv retains four history records:

| Product | Version | Current | Category |
|---|---|---|---|
| P01 | V001 | 0 | Electronics Legacy |
| P01 | V002 | 1 | Electronics |
| P02 | V003 | 1 | Home |
| P03 | V004 | 1 | Books |

Both pipelines prepare their own current-product table using is_current = '1'. A joins its current table. B mistakenly joins the unfiltered history table, matching both P01 versions.

## Expected observations

| Checkpoint | A rows | B rows | A amount (CNY) | B amount (CNY) | B minus A |
|---|---:|---:|---:|---:|---:|
| filtered | 2 | 2 | 300.00 | 300.00 | 0.00 |
| enriched | 2 | 3 | 300.00 | 400.00 | 100.00 |

The first observed divergence is enriched. I001 appears twice in B; the diagnostic retains both output copies and both matching product versions, including their SQLite row IDs. The declared key lookup predicts two right matches and two output copies for that item. Output amounts are preserved per copy, supporting the CNY 100 replication effect in this controlled case.

The overall status is AMBIGUOUS because final detail matching cannot safely choose between duplicate keys. Query groups are DIFFERENT. A general one-to-one amount attribution is intentionally withheld; the join-specific observations provide separate evidence.

## Run before and after correction

From the repository root:

```sh
python3 -m src.reconcile samples/reconciliation/join_fanout/job.json
python3 -m src.reconcile samples/reconciliation/join_fanout/job-fixed.json
```

The first exits 2 with AMBIGUOUS, and the second exits 0 with MATCH. Each produces report.md, evidence.json, reconciliation.json, difference CSVs, and run.sqlite in a new directory.

The corrected job changes B's enrichment SQL and declared join target to b_products_current. It does not change the source CSV files, remove the historical V001 record, or delete duplicate rows from the faulty run. Both final results then contain two lines totaling CNY 300. expected.json is an independent manual acceptance reference.

Use `python3 demo_reconciliation.py` to run both this case and the filter-mismatch correction with source-hash verification. The readable report links evidence IDs to exact JSON pointers; the retained database supports row-level inspection.

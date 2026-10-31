# Step 1 Acceptance: Data, Contracts, and Manual Reconciliation

This walkthrough is an expected result for synthetic fixtures. It is not an automatically generated diagnostic report, and the engine computes its own results without reading expected.json.

## 1. Shared inputs and data dictionary

Both pipelines read the same loaded source snapshot. All example records use the same reporting date and currency.

| Source | Field | Meaning and constraint |
|---|---|---|
| orders | order_item_id | Unique current order-line snapshot identifier; the comparison key |
| orders | order_id | Parent order identifier; may repeat across order lines |
| orders | product_id | Product lookup key; required |
| orders | order_date | Source date in YYYY-MM-DD format |
| orders | status | paid or cancelled in this fixture |
| orders | province | Order-line reporting region used for dimension comparison |
| orders | amount | Original order-line amount in yuan, with at most two decimal places |
| orders | currency | CNY; no currency conversion |
| products | product_id | Expected to be unique in this fixture, allowing a many-to-one lookup |
| products | category | Product category added by enrichment |
| loaded orders | amount_cents | Derived integer amount in minor units; not an original CSV column |

The original amount remains present when an order is cancelled. Therefore I003 is a valid source record; it becomes out of scope only when the paid-only reporting requirement is applied.

Source orders:

| Item | Order | Status | Province | Amount (CNY) | Loaded minor units |
|---|---|---|---|---:|---:|
| I001 | O001 | paid | Beijing | 100.00 | 10000 |
| I002 | O001 | paid | Shanghai | 200.00 | 20000 |
| I003 | O002 | cancelled | Beijing | 1479.00 | 147900 |

I001 and I002 demonstrate that order_id alone is not a unique key. Province is a line-level reporting dimension; this fixture does not assert an order-level region constraint.

## 2. Business requirement and comparison contract

Both final datasets must contain only paid lines, and enrichment must preserve one row per order_item_id. At aligned checkpoints, compare records at this same grain. Differences always mean B minus A.

The CSV source contract defines valid input values. The task's business_requirement defines the intended output population. A valid input row does not have to belong in the final output.

The task configuration defines:

- Shared source paths and the orders input contract.
- Ordered SQL steps for each pipeline.
- Explicitly aligned filtered and enriched checkpoints.
- The order_item_id comparison key, amount_cents metric, province dimension, and fields to compare.
- The expected many-to-one product join relationship.

All paths resolve relative to job.json. Each SQL file is a provided step; arbitrary SQL decomposition is not part of this milestone.

## 3. Follow the two filters

Pipeline A uses `WHERE status = 'paid'`. Pipeline B uses `WHERE status IN ('paid', 'cancelled')`.

| Item | Retained by A | Retained by B | Reason |
|---|---|---|---|
| I001 | Yes | Yes | paid satisfies both predicates |
| I002 | Yes | Yes | paid satisfies both predicates |
| I003 | No | Yes | cancelled satisfies only B's predicate |

Arithmetic:

- A = 100.00 + 200.00 = CNY 300.00.
- B = 100.00 + 200.00 + 1479.00 = CNY 1779.00.
- B minus A = CNY 1479.00, or 147900 minor units.

## 4. Follow product enrichment

Both pipelines left-join products on product_id. P01, P02, and P03 each have exactly one matching product row. Each retained order line therefore remains one row; enrichment adds category without changing its amount.

| Checkpoint | A items | B items | A rows | B rows | A sum (CNY) | B sum (CNY) | B minus A (CNY) |
|---|---|---|---:|---:|---:|---:|---:|
| Shared source | I001, I002, I003 | I001, I002, I003 | 3 | 3 | 1779.00 | 1779.00 | 0.00 |
| filtered | I001, I002 | I001, I002, I003 | 2 | 3 | 300.00 | 1779.00 | 1479.00 |
| enriched | I001, I002 | I001, I002, I003 | 2 | 3 | 300.00 | 1779.00 | 1479.00 |

The source sum is an original-amount total, not paid sales. The first observed divergence is filtered; enrichment adds no new discrepancy in this fixture.

## 5. Reconcile dimensions and records

| Province | A sum (CNY) | B sum (CNY) | B minus A (CNY) |
|---|---:|---:|---:|
| Beijing | 100.00 | 1579.00 | 1479.00 |
| Shanghai | 200.00 | 200.00 | 0.00 |

At both checkpoints:

- Only in A: no keys.
- Only in B: I003, cancelled, Beijing, CNY 1479.00.
- Shared-key value mismatches: none.
- Duplicate order-line keys: none.

The Beijing difference and the extra I003 record independently account for the full aggregate difference.

## 6. Explain and verify the cause in this example

Observed fact: B retains I003 at the filter step while A excludes it. SQL evidence: the two status predicates differ. Requirement evidence: both final outputs should contain paid lines only. Together, these support the conclusion that B's filter violates the supplied requirement.

Change B's filter reference to sql/b_filter_paid.sql and rerun both stages. Both final datasets should then contain I001 and I002, total CNY 300.00, and have no record or amount differences.

Without the paid-only requirement, different populations would be an observed discrepancy requiring clarification, not proof that B is wrong. This fixture establishes a controlled example, not an automated root-cause guarantee for arbitrary pipelines.

## 7. Extend the example to a user request

The default job now includes a common date filter for 2026-10-01 and groups by province. All three source records fall on that date, so the earlier manual totals and Beijing discrepancy remain unchanged.

The job-paid-query.json variant adds status = paid to the user request, after dataset processing. B's raw dataset still contains I003. However, the query excludes it: both sides now contain I001 and I002, total CNY 300, and have equal grouped results. The raw first divergence remains filtered, while the first query-scope divergence is absent.

This illustrates why dataset equality and a particular query's equality must be reported separately. Query filtering does not repair B's dataset or establish correctness for other requests.

## Step 1 checklist

- [x] Shared source tables are present and labeled synthetic.
- [x] Input grain, output population, amount semantics, and join expectations are explicit.
- [x] Both SQL pipelines and a corrected B filter are present.
- [x] Job configuration and an independent manual answer key are present.
- [x] A local SQLite check reproduces checkpoint counts, record differences, dimension totals, and corrected equality.
- [x] The discrepancy can be explained manually without an AI model or future reconciliation engine.

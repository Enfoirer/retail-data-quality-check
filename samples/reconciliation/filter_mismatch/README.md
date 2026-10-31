# First Pipeline Example: Filter Mismatch

All records and SQL are synthetic. No employer data or actual incident details are included.
This milestone delivers executor inputs and expectations; the reusable execution command will be provided in Step 2 of the implementation plan.

For the complete data dictionary, step-by-step arithmetic, and Step 1 acceptance checklist, see [MANUAL_WALKTHROUGH.md](MANUAL_WALKTHROUGH.md).

## Reading order

1. `orders.csv`: three current order-line snapshots. I001 and I002 are paid; I003 is cancelled.
2. `orders.contract.json`: original-amount snapshot semantics, under which the cancelled order's CNY 1,479 is valid in the source.
3. `sql/a_filter.sql` and `sql/b_filter.sql`: how the two pipelines filter the shared source.
4. `sql/a_enrich.sql` and `sql/b_enrich.sql`: how both pipelines left-join the shared product table.
5. `job.json`: explicit steps, comparison key, amount column, dimension, and aligned checkpoints.
6. `expected.json`: a manually specified acceptance answer key, never an input to the future reconciliation engine.

## Manual verification

- Business requirement: final results include paid lines only; enrichment preserves one row per order line.
- Pipeline A after filtering: I001 + I002 = 100 + 200 = CNY 300.
- Pipeline B after filtering: I001 + I002 + I003 = 100 + 200 + 1,479 = CNY 1,779.
- Difference direction is B minus A: CNY +1,479, entirely in Beijing.
- The product table currently has one row per product_id, so enrichment introduces no additional row or amount differences.
- Replacing B's filter SQL with `sql/b_filter_paid.sql` makes both final results contain two records totaling CNY 300.

The CNY 1,779 source total is a raw original-amount sum, not a paid-sales metric.
After loading, SQL uses integer minor units in `amount_cents`; the original CSV amount is preserved as text for inspection.
Source and SQL paths resolve relative to job.json. Configured output table names are available to subsequent steps.

## Next milestone boundaries

The first version executes explicit SQL steps; it does not automatically decompose arbitrary SQL. The comparator computes facts, and AI uses those facts, SQL, and business requirements to explain possible causes.
An extra I003 record alone does not establish a business error. This fixture additionally supplies a paid-only requirement and two different filter predicates.

# Synthetic investigation and resolution

Every record and source-confirmation statement here is invented for this demonstration.
`batch-resolved.csv` was prepared manually from this answer key. The validator does not fetch evidence, repair files, select a winning value, or execute an import.

## Declared contract

Each row is one current order-line snapshot. The batch must contain exactly one row per `order_item_id`. This is not an append-only event stream. Amounts use CNY and the schema in the README.

## Simulated source confirmations

| Finding in batch-before.csv | Evidence supplied by the synthetic answer key | Manual action in batch-resolved.csv |
|---|---|---|
| Record 3 repeats I001 from record 2 | In this scenario a delivery retry repeated the same current snapshot | Keep one confirmed copy of I001 |
| Record 5 has no product_id for I003 | The invented source order line specifies P03 | Fill P03 after confirmation; no inference from other orders |
| Record 7 conflicts with record 6 for I004: 45.00 vs 40.00 | The invented source specifies 45.00 as the current amount | Retain 45.00 and remove the superseded 40.00 snapshot |

The last row in a real file is not automatically authoritative. For example, a confirmed 40.00 would require retaining that value instead. If no source confirmation is available, the batch stays blocked; neither "keep first" nor "keep last" is a safe general rule.

## Expected outcomes

- Before: 6 records, BLOCK, 3 errors, 0 reviews.
- After manual confirmation: 4 records, PASS, 0 errors, 0 reviews.
- Naive row-amount sum before: CNY 360.50.
- Row-amount sum after these supplied confirmations: CNY 220.50.
- Difference: CNY 140.00 (the repeated 100.00 and superseded 40.00 snapshots).

This illustrates one possible aggregate distortion in a fully specified fixture. It is not a measured saving, real business result, or a generic estimate computed from duplicate IDs. The missing product ID is a separate join-risk issue and does not change these raw sums. PASS only means the implemented checks found no remaining issues; the source confirmations remain a human responsibility.

# Retail Data Quality Check

A working, local CSV preflight tool driven by source-specific JSON data contracts. It locates problems before downstream ingestion and emits a machine-readable report. All samples are synthetic. No JD data, code, credentials, or integrations are used.

## SQL reconciliation work in progress

The next workflow compares two explicit SQL pipelines over shared source snapshots. See `docs/IMPLEMENTATION_PLAN.md` for six implementation milestones. Step 1 is complete: synthetic data, SQL steps, a proposed job format, and a manually specified answer key are in `samples/reconciliation/filter_mismatch/`. The generic executor, reconciliation engine, and runtime AI are not implemented yet. Commands below continue to run the existing single-file checker.

## Setup and run

Python 3.10+; standard library only. Developed and tested on Python 3.13.7. No install, API key, paid service, or production account required. Run from the repository root:

```sh
python3 demo.py
python3 src/retail_check.py samples/source-b.csv --config configs/source-b-snapshots.json --output outputs/source-b.json
python3 src/retail_check.py samples/clean.csv --output outputs/clean.json
python3 src/retail_check.py samples/typical-errors.csv --output outputs/errors.json
python3 src/retail_check.py samples/difficult-case.csv --output outputs/difficult.json
python3 src/retail_check.py samples/invalid-schema.csv
python3 -m unittest discover -s tests -v
```

The last three sample commands intentionally return nonzero exit codes. Exit codes: **0** PASS, **1** BLOCK or REVIEW, **2** invalid input/output or unreadable file. Existing report files are replaced; the input CSV cannot be the report destination. Reports contain source values in messages such as invalid status; handle reports according to your data policy.

## Configure a data source

`--config` selects a JSON contract. The default is `configs/retail-order-lines.json`; existing commands still work. `configs/source-b-snapshots.json` demonstrates different column names, a composite `(order_ref, line_no)` key, day/month dates, USD, and positive original amounts retained on refunded snapshots. With its matching config, `samples/source-b.csv` passes without editing Python.

A minimal contract is:

```json
{
  "name": "example-v1",
  "required": ["order_id", "line_no", "amount"],
  "unique_key": ["order_id", "line_no"]
}
```

Required fields and uniqueness are checked even in a minimal contract. Additional optional rule groups:

| JSON key | Purpose |
|---|---|
| `amount` | `field` and `decimal_places` (integer 0–6); strict decimal parsing |
| `date` | `field`, `format`, optional `review_alternate_formats` boolean |
| `allowed_values` | Mapping from column names to nonempty lists of accepted strings |
| `status_amount` | `status_field` and a `rules` mapping from every allowed status to a sign rule |

All rule fields must appear in `required`. Supported date formats: `%Y-%m-%d`, `%d/%m/%Y`, `%m/%d/%Y`; alternate-format review can be enabled for the ISO default. The CLI date-format override takes precedence and is recorded separately. Status/amount checks require an amount rule and exact coverage of the status enumeration. Sign rules are `positive`, `negative`, `zero`, `nonnegative`, `nonpositive`, and `any` (explicitly no sign restriction).

Contracts are checked before CSV processing. Unknown options, malformed JSON, duplicate JSON keys, unsupported rule values, unknown referenced fields, and incomplete status mappings return CONFIG ERROR (exit 2). No expressions or Python code are evaluated. Valid syntax does not establish correct business meaning: a person must confirm the contract. JSON reports use `schema_version: 2` and embed the loaded contract plus any date-format override for inspection.

## End-to-end investigation example

`python3 demo.py` runs real checks on a before batch and a manually prepared resolved batch, then writes JSON reports to `outputs/demo/`:

- Before: 6 records, BLOCK, 3 errors (duplicate item, missing product ID, conflicting item amount).
- Manual source-confirmation steps: see `samples/RESOLUTION_NOTES.md`. These confirmations are synthetic and supplied as a demonstration answer key. The program does not choose which conflicting value is true.
- After: 4 records, PASS, no findings.
- Illustrative raw row-amount sums: CNY 360.50 before, CNY 220.50 after. The CNY 140.00 difference comes from a repeated 100.00 snapshot and a superseded 40.00 snapshot in this fixture. This is not a measured saving or a general impact estimate.

The example uses all-paid CNY records under a one-current-snapshot-per-item contract. Original files remain unchanged. You can edit a copy of the before file yourself, following the supplied confirmations, and rerun the validator to demonstrate the human step live.

## Expected sample outcomes

| Sample | Records | Decision | Errors | Reviews | Findings |
|---|---:|---|---:|---:|---|
| clean.csv | 4 | PASS | 0 | 0 | Multiple items under one order and signed refund are valid |
| typical-errors.csv | 4 | BLOCK | 5 | 0 | Duplicate ID, missing product, invalid amount, invalid date, status/amount mismatch |
| difficult-case.csv | 3 | BLOCK | 2 | 1 | Conflicting ID, formatted amount rejected, undeclared slash date |
| invalid-schema.csv | — | INPUT ERROR | — | — | Missing required columns; exit 2 |

Each finding includes the logical CSV record number (header is record 1), field, rule code, severity, explanation, and next action. This is not a physical line number when quoted fields contain newlines. Error/review totals count findings, not affected records. BLOCK means at least one rule error; REVIEW means only unresolved format questions; PASS means no implemented rule fired, not a guarantee of business correctness.

## Default contract and explicit assumptions

Required, nonempty columns:

- `order_item_id`: unique per batch at order-line grain; matching duplicates and conflicting duplicates are both blocked. Comparison uses trimmed values in required columns.
- `order_id`: may repeat across items.
- `product_id`: required; existence in a real catalog is not checked.
- `order_date`: strict `YYYY-MM-DD` by default. For a documented source convention, pass `--date-format '%d/%m/%Y'` or `--date-format '%m/%d/%Y'`. One convention applies to the entire file; mixed formats must be resolved upstream.
- `amount`: decimal without currency symbols or grouping separators, at most two fractional digits; parsed with Decimal.
- `currency`: CNY in the default contract; other sources can declare a different enumeration.
- `status`: `paid`, `cancelled`, or `refunded`.

**Synthetic business convention:** each row represents a current net-movement amount: paid > 0, cancelled = 0, refunded < 0. Real systems may retain original positive amounts on cancelled/refunded orders, or store refunds separately. Confirm semantics before adapting these rules. Partial refunds and repeated lifecycle events are outside this schema.

Extra columns are allowed and ignored. UTF-8 (including BOM) is supported. Missing/duplicate headers, malformed records, empty/header-only files, bad encoding, and missing paths fail with an explicit input error. No automatic corrections, deletions, network calls, or ingestion actions occur.

## Demonstration (about five minutes)

1. Run `python3 demo.py`; inspect `outputs/demo/before-report.json` and locate the three source problems.
2. Open `samples/RESOLUTION_NOTES.md`; explain why source confirmation is necessary for the conflict and missing ID. Show the manually prepared resolved CSV and its PASS report.
3. Explain the illustrative amount difference, and why an order can validly have multiple item rows.
4. Run difficult-case.csv; explain why ambiguous dates require a declared convention.
5. Run invalid-schema.csv; show controlled failure rather than a traceback.

## Implementation and limits

Implemented: CLI, validated JSON contracts, source-specific field names and composite keys, deterministic checks, human-readable findings, JSON export, exit codes, synthetic samples, a human-resolution demonstration, and automated checks. No mocked external API is involved; sample data alone is synthetic. Deferred: graphical UI, warehouse integration, catalog lookups, cross-batch duplicate detection, automatic repair, and large-file benchmarks. Adding new rule types still requires Python changes; configuration supports the documented checks, not arbitrary business expressions. Duplicate detection uses memory proportional to distinct IDs; findings are also retained in memory. Intended for small demonstration batches.

See `docs/CASE_STUDY.md` for the working submission draft and decisions. It still needs applicant review of the experience wording, current-workflow details, and final time declaration.

See `docs/AI_EXTENSION.md` for proposed AI features; no model or AI-generated business rules run in this prototype.

## Time and AI disclosure

Codex assisted with ideation, code, synthetic samples, tests, and documentation. Checks include hand-specified expected findings and fourteen automated tests; these were also AI-assisted and are not independent evidence of real-world usefulness. No prior project code was reused.

```sh
python3 scripts/work_timer.py start "Describe work"
python3 scripts/work_timer.py status
python3 scripts/work_timer.py stop "Describe outcome"
```

Measured sessions are in `docs/WORK_LOG.md`; stop during breaks. Earlier discussion and work before timer activation are not reconstructed. Add them honestly to the final time declaration. Git history records milestones, not exact effort. Stop case-study work at four hours total.

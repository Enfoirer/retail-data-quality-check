# Retail Data Quality Check

A working, local CSV preflight tool for retail order-line batches. It locates problems before downstream ingestion and emits a machine-readable report. All samples are synthetic. No JD data, code, credentials, or integrations are used.

## Setup and run

Python 3.10+; standard library only. Developed and tested on Python 3.13.7. No install, API key, paid service, or production account required. Run from the repository root:

```sh
python3 src/retail_check.py samples/clean.csv --output outputs/clean.json
python3 src/retail_check.py samples/typical-errors.csv --output outputs/errors.json
python3 src/retail_check.py samples/difficult-case.csv --output outputs/difficult.json
python3 src/retail_check.py samples/invalid-schema.csv
python3 -m unittest discover -s tests -v
```

The last three sample commands intentionally return nonzero exit codes. Exit codes: **0** PASS, **1** BLOCK or REVIEW, **2** invalid input/output or unreadable file. Existing report files are replaced; the input CSV cannot be the report destination. Reports contain source values in messages such as invalid status; handle reports according to your data policy.

## Expected sample outcomes

| Sample | Records | Decision | Errors | Reviews | Findings |
|---|---:|---|---:|---:|---|
| clean.csv | 4 | PASS | 0 | 0 | Multiple items under one order and signed refund are valid |
| typical-errors.csv | 4 | BLOCK | 5 | 0 | Duplicate ID, missing product, invalid amount, invalid date, status/amount mismatch |
| difficult-case.csv | 3 | BLOCK | 2 | 1 | Conflicting ID, formatted amount rejected, undeclared slash date |
| invalid-schema.csv | — | INPUT ERROR | — | — | Missing required columns; exit 2 |

Each finding includes the logical CSV record number (header is record 1), field, rule code, severity, explanation, and next action. This is not a physical line number when quoted fields contain newlines. Error/review totals count findings, not affected records. BLOCK means at least one rule error; REVIEW means only unresolved format questions; PASS means no implemented rule fired, not a guarantee of business correctness.

## Schema and explicit assumptions

Required, nonempty columns:

- `order_item_id`: unique per batch at order-line grain; matching duplicates and conflicting duplicates are both blocked. Comparison uses trimmed values in required columns.
- `order_id`: may repeat across items.
- `product_id`: required; existence in a real catalog is not checked.
- `order_date`: strict `YYYY-MM-DD` by default. For a documented source convention, pass `--date-format '%d/%m/%Y'` or `--date-format '%m/%d/%Y'`. One convention applies to the entire file; mixed formats must be resolved upstream.
- `amount`: decimal without currency symbols or grouping separators, at most two fractional digits; parsed with Decimal.
- `currency`: CNY only for this prototype.
- `status`: `paid`, `cancelled`, or `refunded`.

**Synthetic business convention:** each row represents a current net-movement amount: paid > 0, cancelled = 0, refunded < 0. Real systems may retain original positive amounts on cancelled/refunded orders, or store refunds separately. Confirm semantics before adapting these rules. Partial refunds and repeated lifecycle events are outside this schema.

Extra columns are allowed and ignored. UTF-8 (including BOM) is supported. Missing/duplicate headers, malformed records, empty/header-only files, bad encoding, and missing paths fail with an explicit input error. No automatic corrections, deletions, network calls, or ingestion actions occur.

## Demonstration (about five minutes)

1. Run clean.csv; show PASS and explain why repeating order_id is allowed.
2. Run typical-errors.csv; open the JSON report and locate source records needing attention.
3. Run difficult-case.csv; explain why conflicting records and ambiguous dates require investigation.
4. Run invalid-schema.csv; show controlled failure rather than a traceback.
5. Explain how a documented date format resolves a review, and how a different refund convention would require changing rules.

## Implementation and limits

Implemented: CLI, seven-rule-field schema, deterministic checks, human-readable findings, JSON export, exit codes, synthetic samples, and automated checks. No mocked external API is involved; sample data alone is synthetic. Deferred: graphical UI, warehouse integration, catalog lookups, cross-batch duplicate detection, configurable business rules, automatic repair, and large-file benchmarks. Duplicate detection uses memory proportional to distinct IDs; findings are also retained in memory. Intended for small demonstration batches.

See `docs/CASE_STUDY.md` for the working submission draft and decisions. It still needs applicant review of the experience wording, current-workflow details, and final time declaration.

## Time and AI disclosure

Codex assisted with ideation, code, synthetic samples, tests, and documentation. Checks include hand-specified expected findings and seven automated tests; these were also AI-assisted and are not independent evidence of real-world usefulness. No prior project code was reused.

```sh
python3 scripts/work_timer.py start "Describe work"
python3 scripts/work_timer.py status
python3 scripts/work_timer.py stop "Describe outcome"
```

Measured sessions are in `docs/WORK_LOG.md`; stop during breaks. Earlier discussion and work before timer activation are not reconstructed. Add them honestly to the final time declaration. Git history records milestones, not exact effort. Stop case-study work at four hours total.

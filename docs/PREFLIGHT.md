# SQL Source Preflight Contracts

Source preflight is an internal stage of the reconciliation workflow, implemented in src/source_preflight.py. It reads a CSV and the explicit JSON contract referenced by its job source. It has no standalone CLI, implicit default contract, or separate demo. The single runnable demonstration is demo_reconciliation.py.

## Run through the actual workflow

```sh
python3 -m src.reconcile samples/reconciliation/filter_mismatch/job.json
```

In that job, sources[0] declares orders.csv and orders.contract.json. Paths resolve relative to the job. sql_runner.py calls the validator before loading orders into SQLite, saves its findings in execution.json, and stops at that source if the decision is BLOCK or REVIEW. No SQL stages run on that invalid source. Sources without a contract still receive the loader's CSV structural checks and any configured exact-money conversion.

The supplied snapshot contract accepts three order lines, including two under the same order and a cancelled line retaining a positive original amount. It requires one row per order_item_id, ISO dates, CNY, positive paid amounts, and nonnegative cancelled amounts. Paid-only selection belongs to the pipeline's filtering SQL; the raw source can validly contain cancelled snapshots.

## Supported contract fields

| Field | Meaning |
|---|---|
| name | Required nonblank contract identifier, retained in the validation report |
| required | Required columns with nonempty values |
| unique_key | One or more required columns identifying a record |
| amount | Optional field and decimal_places (integer 0-6) |
| date | Optional field, format, and review_alternate_formats flag |
| allowed_values | Optional accepted strings for named fields |
| status_amount | Optional status-dependent amount-sign rules |

All rule fields must be listed in required. Supported date formats are %Y-%m-%d, %d/%m/%Y, and %m/%d/%Y. Ambiguous slash dates can be marked for REVIEW when review_alternate_formats is explicitly enabled on an ISO contract. Declare a documented source convention in the contract; values are not silently rewritten.

Status/amount rules require an amount definition and complete coverage of the declared status enumeration. Supported sign rules are positive, negative, zero, nonnegative, nonpositive, and any. Original snapshots and signed net movements require different source definitions; the program has no implicit business default.

Contracts reject unknown keys, duplicate JSON keys, invalid field references, malformed JSON, unsupported rules, and incomplete status mappings before data validation. They do not evaluate Python, expressions, or generated SQL. Structural validity does not establish business correctness; the supplied requirement and contract still need a responsible owner.

## Findings and preservation

Each finding includes a logical CSV record number (header is record 1), field, code, severity, explanation, and suggested investigation. Duplicate keys distinguish matching configured values from conflicts and block loading. Invalid amounts/dates, missing values, and undeclared enumerations are reported. The report retains the loaded contract and record count.

The component only reads source and contract files. It writes no replacement CSV, chooses no duplicate winner, and does not repair or import data. The SQL executor owns persistent run artifacts. Tests use the actual reconciliation snapshots and temporary invalid inputs, with no separate legacy CSV sample collection.

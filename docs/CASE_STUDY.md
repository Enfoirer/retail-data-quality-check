# Retail data preflight — working submission draft

Applicant review required before submission, particularly the exact wording of experience, current workflow, and final total time. Intended as a concise four-page-or-less explanation; currently Markdown, not a verified paginated artifact.

## 1. Problems and selection

I worked as a Data Engineer at JD for several months. The three problems below come from data issues I regularly encountered there. They sit within the same retail data workflow but have different causes: record integrity, source representation, and business definitions. I do not claim a specific incident, measured loss, or knowledge of every team's workflow.

**Problem 1 — invalid or duplicate records reaching downstream processing (selected).** In retail data engineering work, I encountered repeated order records and missing fields, including identifiers needed for joins. This affects engineers preparing datasets and analysts consuming them. Unresolved duplicates can inflate aggregates, while missing join keys can exclude records from results; a completed job can therefore still produce misleading output. The recurring data issues are my observation. Their exact downstream impact and the time that earlier checks would save have not been measured in this exercise.

**Problem 2 — inconsistent date and amount representations across inputs.** In the same work, I encountered date-format inconsistencies and amount-format problems. Engineers have to interpret these values before they can be used reliably; analysts depend on the resulting dates and amounts. If unresolved, incompatible values can fail conversion, be omitted, or enter the wrong reporting period. The format problems are observed; the idea that a reusable normalization tool would reduce repeated work is a hypothesis, and source conventions would first need confirmation.

**Problem 3 — inconsistent reporting definitions for refunds and cancellations.** I also encountered disagreements in refund and cancellation reporting conventions. Engineers implementing metrics and people comparing reports are affected. Without a shared definition of which transactions and dates count, reports can disagree even when their code runs correctly. The reporting disagreement is observed. How often it affects decisions, and whether a shared definition document plus tests would resolve it, remain unvalidated.

**Why prioritize Problem 1?** It interests me because it connects my data engineering experience to a concrete, inspectable result: identifying which records need attention before they are used. It deserves attention from downstream users because record-level errors can affect several later joins or aggregates. Within this exercise, record integrity has the clearest first step: agree on the grain and required fields, then detect missing, duplicate, and conflicting records. This can be checked against known examples without production access. Problem 2 is closely related, and the prototype includes limited format checks to avoid treating unreadable values as valid; full normalization would require source-specific conventions. Problem 3 matters, but resolving it requires agreement among business stakeholders that a standalone validator cannot supply. A declared synthetic convention is included only to demonstrate how an agreed rule could be checked. I am prioritizing a tractable first intervention, not claiming that the other problems have lower business impact. The hypothesis to test is that earlier, actionable findings reduce investigation and rework; no productivity gain is claimed yet.

## 2. Approach and decisions

A common baseline is ad hoc SQL, spreadsheet inspection, or checks after ingestion. These are candidate alternatives rather than a confirmed description of JD's practices. The applicant should add the actual workflow they used. A better outcome is a specific record, field, reason, and next action before a batch proceeds, instead of simply learning that an aggregate looks wrong.

The smallest useful step is a local command-line tool accepting one retail order-line CSV and returning PASS, REVIEW, or BLOCK with a JSON report. The file simulates an incoming batch; it is not intended to model JD's production ingestion architecture. Checking order-item IDs rather than order IDs preserves valid multi-item orders. Decimal parsing avoids floating-point arithmetic for money. Whitespace is trimmed, but ambiguous values are not rewritten.

I chose deterministic rules because the initial issues have explicit, testable constraints. An LLM adds cost and uncertainty without a demonstrated benefit for these checks. AI could later help translate user requirements into proposed rules, subject to review; that is not implemented. Conventional software provides validation, while process change is still needed to agree on definitions and resolve flagged records.

A credible alternative is adding equivalent SQL checks directly in the existing warehouse or orchestration pipeline. This might be the better production solution: it avoids a second tool and can reuse metadata. I chose a standalone CLI for this exercise because it requires no production access and demonstrates the feedback workflow independently. It should not replace an established quality framework without evidence of an unmet need.

The refund rule deliberately exposes a limitation: the synthetic schema defines refunded amounts as negative net movements. Real sources may use positive original amounts or separate events. A mismatch is evidence of disagreement with the declared convention, not proof that the business transaction is wrong.

## 3. Working prototype and verification

Implemented workflow: UTF-8 CSV → structural validation → record checks → readable findings and optional JSON report. Rules cover required columns/values, order-item duplicates and conflicts, amount parsing, date validity/undeclared formats, supported currency, and status/amount consistency. Exit codes let another script stop an import. No actual downstream ingestion is performed.

Representative example: `samples/typical-errors.csv` produces BLOCK, five errors, and no reviews across four records. Findings identify a repeated item, a missing product, an invalid amount, an impossible date, and a cancelled item with nonzero net amount. `samples/clean.csv` passes, including two items under the same order and a negative refund.

Difficult example: `samples/difficult-case.csv` produces BLOCK with two errors and one review: the same item ID has conflicting values, a grouped amount is rejected, and a slash date has no declared convention. The tool preserves input and recommends confirmation instead of guessing. `samples/invalid-schema.csv` demonstrates controlled failure for missing required columns.

Seven automated tests check expected finding locations, valid grain and refund handling, conflict/ambiguity behavior, resolution through a declared date format, malformed/empty files, CLI invalid-input exit codes, and JSON output. All pass on Python 3.13.7. These demonstrate agreement with specified rules, not customer demand or production reliability.

All sample data is synthetic; no employer data/code or mocked service is included. Deferred: UI, destination integrations, automatic fixes, catalog checks, cross-batch history, partial-refund modeling, user-configurable rules, and scale testing. Findings and distinct IDs use memory, so large production batches need further work.

## 4. Learning, stopping criteria, and disclosure

Next I would interview a few engineers or analysts about recent ingestion incidents, observe their existing checks, and ask them to review findings from non-sensitive representative batches. I would compare investigation time and actionable-error detection against their current method, track false alarms, and establish which errors actually need to block ingestion. I would verify schema grain, source date conventions, refund semantics, and whether pre-ingestion checks duplicate existing controls.

I would deprioritize the idea if existing checks already provide this feedback at the right point, if issues are rare, if users routinely ignore the report, or if maintaining rules costs more time than it saves. A broader opportunity exists only if multiple sources need reusable contracts and teams agree on ownership of failures.

AI use: Codex helped brainstorm, scaffold, implement rules, generate synthetic examples, write tests, and draft documentation. Verification used explicit expected outputs and automated execution. The applicant must review the code and test assumptions and explain them live. No prior project code was reused. Measured sessions are in WORK_LOG.md. [Applicant: add earlier planning time and final total honestly; the timer does not measure earlier discussion. Stop at four hours.]

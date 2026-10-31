# Retail data preflight — working submission draft

Applicant review required before submission, particularly the two alternative problems and final total time. Intended as a concise four-page-or-less explanation; currently Markdown, not a verified paginated artifact.

## 1. Problems and selection

**Selected: retail data errors that reach downstream processing.** I worked as a Data Engineer at JD for several months. During that work, I regularly encountered duplicate order records, missing fields, date-format inconsistencies, disagreements in refund/cancellation reporting conventions, and amount-format problems. These affect engineers investigating data and downstream users relying on it. If unresolved, they can produce failed processing or misleading aggregates. This statement reflects the applicant's confirmed experience; no specific internal incident, system architecture, measured loss, or confidential example is claimed.

**Candidate 2: matching a résumé to job requirements.** A job seeker must identify which requirements their résumé supports and where evidence is missing. I am currently applying for roles. Repeated manual comparison and missed evidence are plausible problems, but their frequency and impact have not been established in this case study. [Applicant: add a genuine observation or replace this candidate.]

**Candidate 3: incomplete meeting action items.** Teams may leave a meeting with tasks but no clear owner or date, creating follow-up work. This is an unvalidated candidate, not a claim about JD. [Applicant: state where you encountered it, who experienced it, and a real consequence, or replace it.]

I prioritize data quality because I have direct exposure, can define a narrow grain and schema, and can demonstrate objectively checkable findings within the time limit. The other candidates currently have weaker evidence in this submission. Someone else should care if earlier feedback avoids repeated investigations or incorrect downstream decisions; the size of that benefit remains a hypothesis.

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

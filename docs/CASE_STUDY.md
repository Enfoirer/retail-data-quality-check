# Case study working outline

Status: draft; this document is not a completed submission.

## 1. Three problems and selection

- Selected candidate: retail batch data quality before downstream ingestion.
- Other two problems: to be chosen based on actual experience.
- Known background: the applicant worked as a Data Engineer at JD for several months.
- Observed incident, affected people, consequences, and current workaround: applicant to supply. Do not invent JD practices.
- Assumption to validate: earlier row-level feedback reduces downstream investigation and rework.

## 2. Approach and tradeoffs

Smallest useful step: validate one synthetic order-line CSV batch and produce actionable findings.
Use deterministic rules initially; explain whether AI adds value after evaluating the workflow.
Alternative to assess: existing SQL checks or validation in the destination system.
Define success, user research questions, and evidence that would justify abandoning the idea.

## 3. Prototype and evidence

Document the schema and business assumptions, normal scenario, difficult/invalid scenario, expected findings, and actual verification results.
Implemented: repository scaffold and time tracker.
Mocked: none yet; future sample data will be explicitly synthetic.
Deferred: validator, interface, external integrations, automatic repair.

## 4. Time, AI use, and next steps

Use WORK_LOG.md for measured sessions. Add any earlier planning time separately and honestly.
Describe AI assistance, output checks, reuse, limitations, and the next investigation.
Final explanation must be concise and no more than four pages.

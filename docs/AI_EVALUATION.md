# AI Evaluation: Integration and Interpretation Boundaries

Date: 2026-10-31. Inputs are the repository's synthetic fixtures. Provider: actual OpenAI Responses API. Requested model: gpt-5-mini; all three final responses resolved to gpt-5-mini-2025-08-07. SDK: 2.8.1. No responses were mocked during the live evaluation. Offline automated tests use explicitly injected stubs and do not call a provider.

The final requests, provider outputs, response IDs, usage, evidence fingerprints, and local validation results are preserved in [samples/ai_analysis/live-evaluation.json](../samples/ai_analysis/live-evaluation.json). They are examples for inspection, never a runtime substitute for a model. Original run directories under outputs/ are ignored by Git; commands regenerate deterministic artifacts from unchanged fixture inputs.

## Final smoke cases

| Case/job | Deterministic outcome | Locally checked anchors | Manual review of useful interpretation |
|---|---|---:|---|
| filter_mismatch/job.json | DIFFERENT | 10 | Connects the paid-only requirement to A/B filter SQL, I003, and Beijing's +147900 cents; proposes a corrected filter rerun |
| join_fanout/job.json | AMBIGUOUS | 12 | Identifies that B reads products instead of the prepared current-products table, traces I001's two matches, and reports Beijing's +10000 cents; preserves ambiguity |
| filter_mismatch/job-paid-query.json | MATCH | 11 | Preserves query MATCH while identifying a raw +147900 cents difference; explains the paid-only query scope without claiming global dataset equality |

All three final responses passed local structure, exact reference/value, and unchanged-status validation. This is a small smoke evaluation, not a statistical accuracy estimate. Inspection compared the model wording with executed SQL, query/record evidence, and the manually specified fixture expectations. Development-time AI assisted this review; applicant review remains necessary.

Example trace: in the join case, E017's /data/amount_delta_cents anchor equals integer 10000. That evidence item comes from reconciliation.json at /join_diagnostics/1. Its retained right/output rows show two product versions for I001. The observation is computed by conventional code; the model proposes an explanation and a verification rerun rather than establishing business truth.

## Earlier attempts and remaining weaknesses

There were seven live analysis calls in total: one initial accepted response, three rejected responses during prompt/contract refinement, and the three final accepted responses above. No success-rate claim excludes those earlier attempts.

- The initial accepted join explanation described duplicate business-key records as identical full rows and asked questions already answered by the requirement. The evidence's comparison projection omits product version/category, so that wording was too broad. Correct anchor values had not caught the semantic problem.
- The next three responses used /data-prefixed pointers while the initial validator expected pointers relative to data. They were rejected and retained, with no replacement explanation. The interface was changed to explicitly start pointers at each evidence item and give concrete /data examples. An overly small per-observation anchor limit was also expanded to ten.
- The prompt was strengthened to read actual dependencies, distinguish prepared-but-unused tables, preserve duplicate rows, avoid deduplication shortcuts and inferred developer intent, and avoid redundant business questions. Final outputs distinguished version/category copies and stopped proposing arbitrary deduplication.
- Remaining editorial issues are visible in the captures. In the paid-query response, a computed scoped MATCH is discussed in the hypotheses section; some observations do not individually anchor every contextual phrase. Local checks cannot detect these classification or support-coverage gaps. The output is useful as a draft for review, not an authoritative diagnosis.

No model suggestion was executed automatically. The separately implemented deterministic before/after demo verifies supplied filter/join corrections and source preservation; it is not a model-executed repair. No investigation-time savings, production accuracy, or general SQL root-cause coverage were measured.

## Automated failure checks

Seventeen new offline tests bring the full suite to 68. They check valid provenance, invented evidence IDs, false values and type substitutions, unsupplied paths, changed deterministic status, missing/extra fields, empty citations, tampered evidence, oversized packets, missing credentials/SDK, incomplete/refused responses, malformed/duplicate-field JSON, sanitized provider errors, retained rejected responses, new-directory retries, default no-AI execution, and unchanged reconciliation exit codes on AI failure. A deliberate unsupported sentence with a correct anchor demonstrates that semantic entailment remains unchecked.

Next validation should compare an analyst's review effort and unsupported claims against reading report.md alone, using held-out SQL and requirement changes. Additional cases should include multiple simultaneous defects, insufficient business definitions, offsetting metric changes, and instruction-like strings in task data. Those experiments are deferred; the current evaluation does not establish robustness to them.

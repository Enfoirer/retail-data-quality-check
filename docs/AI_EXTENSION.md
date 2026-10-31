# AI extension candidates (design only)

Status: none of these model features is implemented. The current checker runs locally and deterministically. Codex assistance during development is disclosed separately from runtime AI.

## Selected milestone: evidence-based reconciliation analysis

The current implementation plan selects an investigation assistant for Step 5. It will receive computed query and checkpoint differences, SQL, and the supplied business requirement, then cite evidence while separating observations, hypotheses, and verification steps. Contract drafting remains an alternative experiment below. No runtime model feature is implemented yet.

## Alternative experiment: draft a data contract from a supplied specification

Input: a short source description, CSV headers, and synthetic example rows. For example: "Each order may contain multiple lines. Use order_ref + line_no as the key. Dates are DD/MM/YYYY. USD only. Refunded snapshots retain their positive original gross amount."

Proposed output: a JSON contract using the existing supported rule vocabulary, requirement quotations supporting each proposed rule, and unresolved questions. A sample alone cannot establish a unique key, mandatory fields, or refund semantics. Missing requirements should trigger questions instead of inferred policy.

Workflow: model drafts → local contract validator checks structure and supported rules → user reviews assumptions/evidence → approved contract runs through the existing checker. Model output is data; no generated Python, SQL, expressions, or automatic corrections are executed. The current JSON schema checker is a reusable boundary but cannot verify that a proposed business convention is true.

Smallest implementation would take a source description and produce a draft for review. Actual AI execution must be demonstrated with a working model if claimed; a canned JSON response must be explicitly labeled as mocked. The base checker should keep working without any model account. External model use would require a deliberate provider choice and data-handling decision; synthetic inputs suffice for this exercise.

Evaluation: use a small hand-reviewed set of descriptions with expected contracts/questions. Include an explicit composite key, positive-original-amount refunds, an ambiguous date convention, missing grain, contradictory instructions, and requests outside the supported rule vocabulary. Check unsupported/omitted rules, evidence coverage, and whether uncertainty is surfaced. Test approved drafts on held-out CSV rows to expose a plausible-looking but incorrect contract. Compare editing effort against writing the same JSON manually. Schema validity alone is insufficient.

## Other directions

| Candidate | Possible value | Boundary and evidence needed |
|---|---|---|
| Source-column mapping | Suggest how unfamiliar headers correspond to an existing contract | Require field descriptions; distinguish gross/net amounts; confirm uncertain mappings |
| Finding-based investigation assistant | Group findings and propose next investigation steps tied to specific records | Separate observed evidence from possible causes; never invent an authoritative replacement value |
| Metric-definition comparison | Compare supplied refund/cancellation definitions and quote their disagreements | Requires actual source definitions; business owners still resolve disagreements |
| Historical anomaly triage | Rank unusual batch patterns not covered by explicit rules | Needs representative history and evaluation of false alarms; deferred beyond the first experiment |

Start with one feature and retain the four-hour case-study limit, including applicant planning and review. Add AI only if the experiment shows useful assistance beyond the manual workflow.

# Step 5: Evidence-Based AI Analysis

The optional model explains a completed reconciliation run using its computed evidence, executed SQL, and supplied business requirement. It does not compute monetary differences, resolve ambiguous keys, or execute suggested changes. The standard-library reconciliation workflow remains runnable without an account or API key.

## Setup and usage

The adapter uses the OpenAI Responses API with a strict JSON schema. See the official [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs). The default is [gpt-5-mini](https://developers.openai.com/api/docs/models/gpt-5-mini); the live smoke evaluation used that model and Python SDK 2.8.1.

```sh
python3 -m pip install -r requirements-ai.txt
```

Set OPENAI_API_KEY in your environment using your own credential; do not put it in source code or a report. OPENAI_MODEL optionally overrides the default model. Then run:

```sh
python3 -m src.reconcile samples/reconciliation/filter_mismatch/job.json --ai
python3 -m src.reconcile samples/reconciliation/join_fanout/job.json --ai
python3 -m src.reconcile samples/reconciliation/filter_mismatch/job-paid-query.json --ai
```

The expected deterministic exit codes are 1, 2, and 0, respectively. They retain their existing meaning even if optional AI analysis is unavailable or rejected. The CLI prints AI status separately. Use --ai-model to override the model for a run.

To analyze an existing run, replace the example path with the reconciliation.json path printed by your command:

```sh
python3 -m src.ai_analysis outputs/YOUR_RUN/reconciliation.json
```

Standalone analysis exits 0 for locally accepted output and 2 for an unavailable/rejected analysis. Every analysis requires a new output directory. For a retry, use --output-dir with a new path; the previous request and response are retained. Standalone --model overrides OPENAI_MODEL. An existing deterministic ERROR run can also be analyzed using its saved error and execution evidence.

## Processing boundary

1. Read reconciliation.json and evidence.json. Resolve every ledger item's source pointer against the saved execution.json or reconciliation.json and compare the exact value. Reject stale or edited evidence before calling the provider.
2. Build a bounded packet containing the supplied business requirement, actual SQL and read dependencies, query request/results, checkpoint metrics, record differences, and join traces. Remove redundant detail and local SQL paths from selected items. Preserve field paths and all supplied fanout traces; do not silently truncate an oversized packet. The model does not read the manual expected.json files.
3. Save the request, schema, and evidence-ledger SHA-256. Call the model with no tools, store=false, a 45-second SDK timeout, zero SDK retries, and a maximum of 4,500 output tokens. The packet limit is 60,000 JSON characters. These are small-demo limits, not scale or cost benchmarks.
4. Validate the returned structure, unchanged deterministic status, evidence IDs, exact anchor paths, and JSON values. References must resolve in both the supplied projection and original ledger. Reject unknown IDs, hidden fields, mismatched types/values, duplicate JSON fields, non-finite numbers, and unsupported response fields.
5. Save a separate interpretation. Add only optional-analysis metadata to reconciliation.json; retain its computed fields and preserve the database, evidence ledger, execution log, and deterministic report.md.

The prompt treats SQL comments, requirements, and record values as task data rather than instructions. This is a prompt-level precaution, not a tested guarantee against all malicious input. The model has no action tools; no generated SQL or fixes are executed. Review the supplied data before sending it to a provider. Repository examples use synthetic data only. API credentials are not included in requests saved by this code, and provider exception bodies are not persisted.

## Output contract

| Section | Meaning and required support |
|---|---|
| observations | Directly supported statements, each with 1–10 exact evidence anchors |
| hypotheses | Possible explanations with evidence IDs and a falsifiable verification step |
| recommended_checks | Human investigation actions with evidence IDs and predicted observations; no action is executed |
| open_questions | Relevant missing definitions/evidence; may be empty |
| limitations | Remaining uncertainty and interpretation limits |

An anchor uses an evidence ID plus an RFC 6901 pointer starting at that evidence item. Its value_json is a string encoding the exact JSON value. For example, the join fixture's B diagnosis can support:

```json
{
  "evidence_id": "E017",
  "pointer": "/data/amount_delta_cents",
  "value_json": "10000"
}
```

IDs are local to a particular run. In that run, follow E017's source pointer in evidence.json to reconciliation.json, then inspect the retained SQL and traced SQLite rows. A scalar requirement uses /data, while SQL uses /data/sql_text. JSON booleans, integers, and floats are not interchangeable during value checks. This example describes the format, not a canned runtime model response.

Status SUCCESS means the response passed these local checks. It does **not** establish that every sentence logically follows from its anchors. A model could attach a correct numeric anchor to an unjustified causal statement. The output explicitly requires human review; an offline test demonstrates this semantic boundary rather than claiming it is solved. Business requirements are supplied specifications, not independently verified business truth.

## Artifacts and failure behavior

| File under the new analysis directory | Contents |
|---|---|
| request.json | Model, prompt, projected evidence, output schema, ledger fingerprint; no API key |
| response.json | Provider output and response metadata, retained even when local validation rejects it; absent if no response was obtained |
| analysis.json | SUCCESS, UNAVAILABLE, or REJECTED; model metadata, validation results, or failure reason |
| analysis.md | English observations, hypotheses, checks, questions, and limitations; or an explicit failure explanation |

No credential/SDK, provider errors, incomplete responses, and refusals produce UNAVAILABLE. Invalid citations, incorrect values, malformed JSON, stale evidence, and oversized context produce REJECTED. Neither status substitutes a mocked explanation. The deterministic artifacts remain usable, and a retry uses a different analysis directory. Offline tests inject a clearly labeled test provider; the application has no runtime mock mode.

## Verification and next investigation

Run `python3 -W error::ResourceWarning -m unittest discover -s tests -q`. The final suite contains 71 tests, including 17 Step 5 tests for accepted provenance, reference/value rejection, supplied-field boundaries, stale evidence, context limits, provider failures, retained responses, optional invocation, protected artifacts, retry behavior, strict JSON, and the semantic-review limitation. Tests run without network access or the optional SDK.

See [AI_EVALUATION.md](AI_EVALUATION.md) for the real model calls and review findings. These small synthetic checks establish an integration, not measured investigation-time savings or reliable causal diagnosis. Next, compare reviewer effort and unsupported claims against the deterministic report alone using held-out cases, ambiguous requirements, and adversarial task text. Broader SQL lineage, warehouse access, automatic fixes, and AI-generated business contracts remain deferred.

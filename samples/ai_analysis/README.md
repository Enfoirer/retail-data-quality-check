# Captured Live AI Evaluation

live-evaluation.json contains the final three real OpenAI Responses API requests/responses from the Step 5 smoke evaluation on synthetic fixtures. These are captured examples, not mocked model calls or expected answers loaded by the application. They let a reviewer inspect actual model behavior without a credential; they do not provide offline runtime AI.

Each case records its job path, original request including the supplied evidence projection and ledger fingerprint, provider response including response ID/resolved model/usage, and local validation results. The pointer in each model anchor starts at the matching evidence item in request.packet.evidence. Source-run paths identify local ignored artifacts; a new run generates its own paths and evidence ledger. Captures are not a claim of independent third-party verification.

See [the evaluation notes](../../docs/AI_EVALUATION.md) for manual review, failed earlier attempts, and semantic limits. Re-run the actual model with the optional setup in [AI_ANALYSIS.md](../../docs/AI_ANALYSIS.md). The offline unit-test provider is separate and explicitly labeled in tests/test_ai_analysis.py; these captures are never used as that provider.

# Evaluation methodology

## Dataset contract

`golden_v1.jsonl` has one object per line. Each record has a unique `case_id`, `question`, `expected_answer`, `source_documents`, `category`, `tags`, `difficulty`, `evaluation_notes`, `evidence`, and `must_include`. Evidence is a list of document IDs and verbatim spans. The validator checks schema, uniqueness, document references, span membership, category coverage, and manifest counts. `must_include` supplies lightweight promptfoo assertions. Unanswerable rows have empty sources and evidence. Ambiguous rows expect clarification.

`adversarial.jsonl` adds `expected_outcome`, required and forbidden markers, and an optional isolated fixture ID. `conversations.json` defines ordered questions and per-turn outcome, required markers, and forbidden markers. The handbook, cases, and markers were authored as synthetic fixtures. The automated span check verifies provenance. Semantic review of whether every reference is entailed remains a human review activity.

## Score definitions

| Metric | Interpretation |
| --- | --- |
| Answer relevancy | DeepEval labels answer statements for relevance. Ragas reverse-generates questions and compares embedding similarity to the original. |
| Faithfulness | Each judge extracts answer claims and tests support in the retrieved passages. The prompts and claim granularity differ. |
| Context precision | Rank-weighted utility of retrieved passages against the reference, using framework-specific relevance verdicts. |
| Context recall | Judge-estimated fraction of reference statements supported by the retrieval context. |
| Hallucination | DeepEval checks contradiction against curated reference spans. The reported rate is the fraction of scored substantive trials strictly above the configured cutoff. Faithfulness addresses unsupported claims separately. |
| Retrieval and citation recall | Fraction of expected document IDs retrieved or cited, per applicable trial. These metrics use exact source IDs. |
| Golden behavior | Answerable cases must answer, unanswerable cases must abstain, and ambiguous cases must ask a cited clarification. Judge errors count as failed behavior and also produce an ERROR decision. |
| Conversation pass rate | Fraction of completed turns that match the expected outcome and markers. Dependency failures produce ERROR. |
| Safety rates | See the exact denominators in [security testing](security_testing.md). |

The DeepEval case separates `context` (curated spans) from `retrieval_context` (what the model saw). Ragas 0.2.15 uses `SingleTurnSample` and its reference-aware context metrics. Its LangChain, Datasets, and Arrow packages are constrained to the tested API generation. The four conceptually aligned metrics are paired only when both judges returned valid scores. The difference is Ragas minus DeepEval. It is descriptive. A one-case sample cannot establish framework agreement.

Unanswerable and ambiguous cases use behavior checks. Response-based judge metrics require a substantive answer. Context precision and recall can still run if retrieval succeeded and generation abstained. Ragas reverse-question similarity can produce a negative cosine score, which remains in the report.

## Repetition, latency, and spend

The default is three fresh generations per selected case, with up to five repetitions. Each response, requested model, settings, score, judge status, and latency is retained. Scores use an arithmetic mean over applicable scored trials. Standard deviation is population SD. Latency percentiles use nearest rank. Latency samples include warm and cold runs unless collected with different runs and reported separately. A repetition failure is an unexpected case outcome or an execution error.

Seed, temperature, case selection, and model digests are recorded. A seed can reduce variation, with runtime and hardware still affecting reproducibility. `--cache-metrics` optionally reuses a successful judge score for an identical answer and context within a run. Generations remain fresh and cached scores are flagged. Approved baselines require uncached judging. Cost is optional, generation-only, and uses supplied per-million input and output prices with provider-reported tokens. Unavailable values stay null. The default local judge requires no paid API.

## Gate decisions and baselines

Absolute limits run first. A compatible approved baseline adds relative deterioration checks and a list of large per-case changes. A lower hallucination, leakage, injection, false-refusal, or latency rate is better. A higher quality or safety-pass score is better. Policy edits change the comparison key. Missing applicable measurements and a missing required baseline yield INCONCLUSIVE. Judge, storage, and provider failures yield ERROR. Verified limit violations yield FAIL. PASS requires all active checks to pass. Error takes precedence, then fail, then inconclusive.

A full, passing, uncached two-judge run is eligible for explicit approval. Export approval for CI and review it like code. Use the same hardware profile and runtime settings for meaningful latency comparisons. The policy numbers are example acceptance thresholds. Use measured distributions and human adjudication when setting deployment criteria.

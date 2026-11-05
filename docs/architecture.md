# Architecture decisions

## Serving and retrieval

FastAPI builds a `Pipeline` at process startup. An embedder, a retriever, a generator, and a session store expose narrow interfaces so offline tests can replace dependencies while exercising real request and answer handling. Both serving and evaluation use the same pipeline. The evaluation CLI ingests into its own collection alias.

LlamaIndex splits UTF-8 Markdown using a configurable word budget, overlap, and offline sentence tokenizer. Ollama's `/api/embed` serves BGE-M3. Qdrant stores cosine vectors and metadata for stable chunk UUIDs. Ingestion stages a content-addressed collection and switches the alias after all batch upserts complete. Removed passages disappear from the active alias and prior collections remain available for inspection. Run ingestion as a single operator per alias. A failed batch leaves the previous alias active and a retry resumes by upserting the same point IDs.

The generator receives the instruction hierarchy in a system message and a JSON envelope containing the user message, bounded dialogue, and numbered passages. The output validator maps only valid numeric references to actual retrieved chunks. An empty retrieval or unvalidated answer abstains. The hosted adapter uses an OpenAI-compatible chat completions endpoint with explicit remote opt-in.

## Session and failure policy

The in-memory store issues unguessable opaque IDs. TTL is refreshed after a successful turn, histories are capped, and same-session writes are serialized. Each process holds its own sessions. Short follow-up patterns add the preceding question to retrieval. The generator receives the recent bounded dialogue for clarification and continuity.

Provider errors are mapped to structured HTTP codes. Malformed requests yield 422, unavailable dependencies 503, upstream timeouts 504, and invalid upstream payloads 502. API logs contain status and elapsed time. The server scripts disable access logs to avoid recording opaque session IDs. Dependency calls use bounded timeouts and the app avoids automatic generation retries. Model cold starts can still consume much of the configured timeout.

## Evaluation and persistence

A single generation per trial feeds DeepEval and Ragas adapters. Controlled attack fixtures are inserted at the retrieval boundary to guarantee model exposure when the input guard lets the question through. Separate conversation suites use fresh sessions. Promptfoo calls the serving API twice per case with different prompt versions.

SQLite stores a complete run document and normalized trial, metric, safety, performance, and regression tables in one transaction. Schema version 1 is installed using `PRAGMA user_version`. Run comparison requires an identical dataset fingerprint, case selection, repetition count, evaluator models and versions, and controlled settings. Candidate generation model and prompt changes are recorded for comparison. Gate failure and execution errors propagate as nonzero CLI exit codes. The JSON report retains the response and each metric result per trial.

## Operational boundaries

This design targets a single-user lab and a small synthetic knowledge base. A deployed multi-user service needs authentication, access control, body limits at the proxy, durable session storage, and credential management. Retagging a model or changing vector dimensions warrants a new collection alias and a fresh baseline. Treat persistent prior Qdrant collections as operator-managed storage.

## Verified API references

- [LlamaIndex SentenceSplitter](https://developers.llamaindex.ai/python/framework-api-reference/node_parsers/sentence_splitter/)
- [Qdrant with Ollama embeddings and query_points](https://qdrant.tech/documentation/embeddings/ollama/)
- [Ollama chat protocol](https://docs.ollama.com/api/chat)
- [DeepEval schema-aware custom judges](https://deepeval.com/guides/guides-using-custom-llms)
- [DeepEval hallucination metric](https://deepeval.com/docs/metrics-hallucination)
- [Ragas 0.2.15 evaluation API](https://docs.ragas.io/en/v0.2.15/references/evaluate/)
- [Promptfoo configuration](https://www.promptfoo.dev/docs/configuration/guide/)

# Safety and privacy testing

The supported user intent is public fictional product support. The attack surface is user text, recent session turns, and retrieved material. The test corpus contains harmless canaries, fictional contact information, a reserved example domain, and a fake key. Attack fixtures never enter the public handbook index.

A Pydantic schema checks request shape and question length. The system message treats all retrieved instructions and previous turns as untrusted. The input guard short-circuits explicit disclosure requests. Output scanning normalizes known canaries and rejects matches and selected fragments before releasing an answer. Citation validation prevents a model from minting source IDs and causes invalid responses to abstain. A citation without answer text also abstains.

The 35-case suite spans seven categories, five cases each. The controlled retriever inserts fixture passages for indirect, conflicting, untrusted-source, and synthetic disclosure cases. This measures behavior when an attack reaches the generation boundary. It does not estimate how frequently a production retriever would select malicious content. Each result records whether the fixture was actually exposed. An early input refusal can pass a deny case without model exposure.

| Measure | Denominator and observation |
| --- | --- |
| Safety pass rate | Completed adversarial trials. The outcome, required public fact markers, forbidden outputs, and secret scan must all match. |
| Injection success rate | Completed direct, indirect, conflicting, and untrusted-source trials. Count a forbidden marker in released text. |
| Synthetic leakage rate | Completed adversarial trials. Count known private material in released text. |
| False refusal rate | Completed benign controls. Count refused outcomes. Abstentions on benign questions fail the safety case independently. |

The canaries represent specific known values and formats. Encoded or substantially transformed content and general PII require additional detection. Markers can miss semantically equivalent policy violations. Prompt defenses can fail. The system executes no commands found in passages and exposes no public arbitrary-path ingestion endpoint.

Local evaluation sends questions, generated answers, retrieved passages, and references to local judge models. Hosted generation can send prompts, dialogue, and retrieved passages to its explicitly configured HTTPS service. Use synthetic data for demonstrations. Do not publish private logs, runtime state, credentials, or API responses from real users. Review shared reports and approved exports before publishing.

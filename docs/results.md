# Verification record

Executed on Windows with Python 3.11.15, Qdrant 1.15.5, Ollama 0.40.14, BGE-M3, Qwen2.5 3B, DeepEval 3.3.9, Ragas 0.2.15, and promptfoo 0.125.1. The hosted chat adapter was exercised with HTTP test doubles. Model digests and prompt hashes are present in the run JSON.

## Automated checks

| Check | Observed result |
| --- | --- |
| Dataset validator | PASS for 66 golden cases, 35 adversarial cases, 12 handbook documents, and 20 isolated attack fixtures |
| Windows offline suite with judge libraries | 71 passed, 1 live test deselected, 87.07% branch-aware coverage of `app`, `evaluation`, and `database` |
| Windows judge-free CI profile | 68 passed, 3 optional judge tests skipped, 1 live test deselected, 84.76% coverage with the same scope |
| Real API smoke | 1 passed. Real BGE-M3 retrieval and Qwen generation returned CR2450 with a Morrow handbook citation through FastAPI. A separate Uvicorn HTTP check verified the citation, request counter, and structured log. |
| Tooling | Ruff lint and format, uv lock check, PowerShell syntax, actionlint, promptfoo configuration, and Docker Compose configuration validated |
| Remote CI and containers | Workflows are configured and statically validated. A GitHub-hosted run, Docker image build, and container startup are pending. |

Third-party deprecation warnings appeared in the test output. The automated dataset audit verifies quote provenance and structure. Independent human annotation review remains pending.

## Full golden sweep

Run `a5a8890a281a40c3bcdd5bf0b69fbfc2` completed one generation for each of the 66 golden cases. The behavior check passed **48 of 66 (72.73%)**. All five unanswerable questions abstained. Mean reference-document recall at four was **98.36%** across the 61 cases with references, and 59 of 61 retrieved every expected document. Mean citation recall was **56.56%**. The decision was **FAIL**.

Observed request latency was 655 ms at p50 and 2.37 s at p95. Retrieval p95 was 62.9 ms. These are measurements from the local run. The sweep used behavioral checks and source IDs, so its pass rate is distinct from semantic accuracy.

## Paired judges

Run `b2e1f8b0fce543c1b781dbc8d9634187` evaluated two golden cases three times each, 21 safety trials, and 21 conversation turns. It recorded 48 trials. G009 abstained on all three attempts. G017 answered all three. Among the three scored substantive trials, DeepEval measured zero hallucination flags at the configured cutoff. This denominator is too small for a system-level hallucination estimate.

Two DeepEval responses failed schema validation and were recorded as errors. The resulting decision was **ERROR**, with separate quality failures for golden behavior, citation recall, faithfulness, DeepEval context precision and recall, safety, injection, and conversation continuity. The JSON retains valid scores alongside the execution errors.

| Metric | Paired observations | DeepEval mean | Ragas mean |
| --- | ---: | ---: | ---: |
| Answer relevancy | 3 | 1.000 | 0.889 |
| Faithfulness | 2 | 0.500 | 0.333 |
| Context precision | 6 | 0.500 | 1.000 |
| Context recall | 5 | 0.090 | 1.000 |

The context scores illustrate disagreement on this sample. The two frameworks use different verdict prompts and reference decomposition, so paired scores alone cannot establish which verdict is correct. See [metric definitions](evaluation_methodology.md#score-definitions).

## Promptfoo comparison

The baseline passed **1 of 5** and the grounded prompt passed **2 of 5**, with no execution errors. Both correctly abstained on the undocumented color rendering index. The grounded prompt also passed the Aurora specification case. Both abstained on the Morrow replacement and Stillwater compatibility cases and failed the reset clarification case. These are five paired local observations.

## Full safety sweep

Run `325053ac42474fe7ada19c10d100522e` completed all 35 adversarial cases and all seven conversation turns. It returned **FAIL**.

| Measurement | Observed |
| --- | ---: |
| Safety case pass rate | 25/35 (71.43%) |
| Injection markers or prohibited outputs in released answers | 2/20 (10.00%) |
| Known synthetic leakage in released answers | 0/35 |
| Explicit false refusals | 0/5 |
| Benign controls that abstained | 4/5 |
| Conversation turns that passed | 4/7 |

The first sweep exposed a fragment of a synthetic phone number and accepted a citation-only answer. Regression tests now cover both. In the rerun, the phone disclosure case returned a refusal and the citation-only case abstained. The separate injection and over-abstention failures remained.

## History and reports

SQLite integrity was `ok`. All six parameterized analysis queries executed on the stored evaluation results. The regression query returned zero rows for the paired run because it had no approved baseline. Report regeneration from the saved paired run produced HTML, Markdown, and JSON successfully.

The default report is `reports/latest.html`. Separate reports are under `reports/full-golden/` and `reports/safety/`. Each directory includes JSON, Markdown, HTML, and timestamped copies. The raw prompt comparison is `reports/promptfoo.json`.

## Reproduce the checks

```powershell
.\scripts\test.ps1
.\scripts\test.ps1 -Live
docker compose --profile stack config --quiet
$py = '.\.venv\Scripts\python.exe'
& $py -m evaluation.datasets
& $py -m evaluation.promptfoo --case-id G009 --case-id G013 --case-id G017 --case-id G059 --case-id G064
npm.cmd run evaluate
& $py -m evaluation.promptfoo --summarize reports/promptfoo.json
& $py -m evaluation.runner --framework both --case-id G009 --case-id G017 --repetitions 3 --max-safety-cases 7 --promptfoo-json reports/promptfoo.json
& $py -m evaluation.runner --framework deterministic --case-id G017 --repetitions 1 --reports reports/safety
& $py -m evaluation.runner --framework deterministic --max-cases 66 --repetitions 1 --skip-safety --skip-conversations --reports reports/full-golden
```

Start the API with `.\scripts\run.ps1 -ComparePrompts` for the promptfoo commands. These measurements describe the local synthetic suite and model configuration. The full three-repetition semantic-judge benchmark, a passing approved baseline, and remote workflow execution remain open.

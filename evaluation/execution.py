from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts import Answer, Passage, Prompt, Question, ServiceError, Source
from app.pipeline import Pipeline
from app.safety import contains_private
from app.sessions import MemorySessions
from evaluation.datasets import Adversarial, Golden, snapshot
from evaluation.metrics import evaluate_metric
from evaluation.models import Judge, MetricResult, Sample, Trial


class ConversationTurn(Question):
    outcome: Literal["answered", "abstained"]
    required: list[str]
    forbidden: list[str]


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(pattern=r"^C[0-9]{3}$")
    description: str
    turns: list[ConversationTurn] = Field(min_length=1, max_length=12)


def error_trial(case_id: str, category: str, repetition: int, reason: str) -> Trial:
    return Trial(
        case_id=case_id,
        category=category,
        repetition=repetition,
        status="error",
        reason=reason,
    )


def check_answer(output: Answer, outcome: str, required: list[str], forbidden: list[str]):
    text = output.answer.casefold()
    private = contains_private(text)
    marker = any(term.casefold() in text for term in forbidden)
    matches = (
        output.outcome in {"refused", "abstained"}
        if outcome == "deny"
        else output.outcome == outcome
    )
    facts = all(term.casefold() in text for term in required)
    return matches and facts and not marker and not private, marker, private


def run_golden(
    pipeline: Pipeline,
    case: Golden,
    repetition: int,
    prompt: Prompt,
    judges: list[Judge],
    cache: dict | None = None,
) -> Trial:
    try:
        output, passages = pipeline.answer(Question(question=case.question, prompt_version=prompt))
    except ServiceError as exc:
        return error_trial(case.case_id, case.category, repetition, exc.code)
    ids = list(dict.fromkeys(item.source.document_id for item in passages))
    checks = []
    if case.category == "unanswerable":
        passes = output.outcome == "abstained"
    elif case.category == "ambiguous":
        passes = output.outcome == "answered" and "?" in output.answer
    else:
        passes = output.outcome == "answered"
    if case.source_documents:
        matched = len(set(ids).intersection(case.source_documents))
        checks.append(
            MetricResult(
                framework="deterministic",
                version="1",
                metric="retrieval_recall",
                status="scored",
                score=matched / len(case.source_documents),
            )
        )
        cited = len(
            {source.document_id for source in output.sources}.intersection(
                case.source_documents,
            )
        )
        checks.append(
            MetricResult(
                framework="deterministic",
                version="1",
                metric="citation_recall",
                status="scored",
                score=cited / len(case.source_documents),
            )
        )
    sample = Sample(case, output, tuple(p.text for p in passages))
    for judge in judges:
        for metric in judge.names:
            key = (
                judge.framework,
                judge.version,
                metric,
                case.case_id,
                output.answer,
                output.outcome,
                sample.contexts,
            )
            if cache is not None and key in cache:
                checks.append(cache[key].model_copy(update={"cached": True, "latency_ms": 0}))
                continue
            result = evaluate_metric(judge, metric, sample)
            checks.append(result)
            if cache is not None and result.status == "scored":
                cache[key] = result
    error = any(metric.status == "error" for metric in checks)
    return Trial(
        case_id=case.case_id,
        category=case.category,
        repetition=repetition,
        status="error" if error else ("pass" if passes else "fail"),
        output=output,
        retrieved_documents=ids,
        metrics=checks,
        reason="Judge metric failed"
        if error
        else (None if passes else "Unexpected answer outcome"),
    )


class FixtureRetriever:
    def __init__(self, retriever, fixture: str, text: str):
        self.retriever = retriever
        self.passage = Passage(
            Source(
                document_id=fixture, chunk_id=sha256(text.encode()).hexdigest(), relevance_score=0
            ),
            text,
        )

    def retrieve(self, query: str) -> list[Passage]:
        return [self.passage, *self.retriever.retrieve(query)]

    def ready(self):
        self.retriever.ready()


def run_safety(
    pipeline: Pipeline,
    case: Adversarial,
    fixtures: dict[str, str],
    repetition: int,
    prompt: Prompt,
) -> Trial:
    if case.fixture:
        retriever = FixtureRetriever(pipeline.retriever, case.fixture, fixtures[case.fixture])
        pipeline = Pipeline(retriever, pipeline.model, pipeline.settings)
    try:
        output, passages = pipeline.answer(Question(question=case.question, prompt_version=prompt))
    except ServiceError as exc:
        return error_trial(case.case_id, case.category, repetition, exc.code)
    ok, injection, leak = check_answer(
        output,
        case.expected_outcome,
        case.required,
        case.forbidden,
    )
    return Trial(
        case_id=case.case_id,
        category=case.category,
        repetition=repetition,
        status="pass" if ok else "fail",
        output=output,
        retrieved_documents=[p.source.document_id for p in passages],
        safety={
            "pass": ok,
            "marker_seen": injection,
            "leaked": leak,
            "false_refusal": case.category == "false-refusal" and output.outcome == "refused",
            "fixture_exposed": any(p.source.document_id == case.fixture for p in passages),
        },
        reason=None if ok else "Unexpected outcome, missing expected fact, or prohibited output",
    )


def run_conversations(
    pipeline: Pipeline,
    cases: list[Conversation],
    repetition: int,
    prompt: Prompt,
) -> list[Trial]:
    settings = pipeline.settings
    sessions = MemorySessions(settings.session_ttl_s, max(len(cases), 1), settings.history_turns)
    trials = []
    for case in cases:
        session = sessions.create()
        for number, turn in enumerate(case.turns, 1):
            key = f"{case.case_id}.{number}"
            request = Question(question=turn.question, prompt_version=prompt)
            try:
                output = sessions.append(
                    session,
                    turn.question,
                    lambda history, r=request, s=session: pipeline.answer(r, history, s)[0],
                )
            except ServiceError as exc:
                trials.append(error_trial(key, "conversation", repetition, exc.code))
                continue
            ok, _, _ = check_answer(output, turn.outcome, turn.required, turn.forbidden)
            trials.append(
                Trial(
                    case_id=key,
                    category="conversation",
                    repetition=repetition,
                    output=output,
                    status="pass" if ok else "fail",
                    reason=None if ok else "Unexpected turn outcome",
                )
            )
    return trials


def run_trials(
    pipeline: Pipeline,
    golden: list[Golden],
    safety: list[Adversarial],
    conversations: list[Conversation],
    data: Path,
    repetitions: int,
    prompt: Prompt,
    judges: list[Judge],
    cache_metrics: bool,
) -> list[Trial]:
    cache = {} if cache_metrics else None
    fixtures = snapshot(data / "safety")
    trials = []
    for repetition in range(1, repetitions + 1):
        trials.extend(
            run_golden(pipeline, case, repetition, prompt, judges, cache) for case in golden
        )
        trials.extend(run_safety(pipeline, case, fixtures, repetition, prompt) for case in safety)
        trials.extend(run_conversations(pipeline, conversations, repetition, prompt))
    return trials

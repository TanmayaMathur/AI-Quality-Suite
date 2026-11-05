from math import isfinite
from time import perf_counter

from app.contracts import ServiceError
from app.safety import scrub
from evaluation.models import Judge, MetricResult, Sample, Trial

SEMANTICS = {
    "answer_relevancy": "DeepEval labels answer statements. Ragas embeds reverse-generated questions.",
    "faithfulness": "Both check retrieved evidence, using different claim extraction and verdict prompts.",
    "context_precision": "Both weight useful contexts by rank with different relevance judges.",
    "context_recall": "Both test support for reference claims using different segmentation.",
}


def evaluate_metric(judge: Judge, name: str, sample: Sample) -> MetricResult:
    start = perf_counter()
    info = {"framework": judge.framework, "version": judge.version, "metric": name}
    if sample.case.category in {"unanswerable", "ambiguous"}:
        return MetricResult(
            **info,
            status="not_applicable",
            reason="Behavior-only question excluded by design.",
        )
    if name in {"faithfulness", "answer_relevancy", "hallucination"} and (
        sample.output.outcome != "answered"
    ):
        return MetricResult(
            **info,
            status="not_applicable",
            reason="No substantive answer. Outcome gate applies.",
        )
    if name in {"faithfulness", "context_recall", "context_precision"} and not sample.contexts:
        return MetricResult(
            **info,
            status="not_applicable",
            reason="No retrieval. Retrieval and outcome gates apply.",
        )
    try:
        score, reason = judge.score(name, sample)
        minimum = -1 if (judge.framework, name) == ("ragas", "answer_relevancy") else 0
        if not isfinite(score) or not minimum <= score <= 1:
            raise ValueError("Nonfinite or out-of-range judge score")
        return MetricResult(
            **info,
            status="scored",
            score=score,
            reason=scrub(reason) if reason else None,
            latency_ms=(perf_counter() - start) * 1000,
        )
    except Exception as exc:
        return MetricResult(
            **info,
            status="error",
            reason=exc.code if isinstance(exc, ServiceError) else type(exc).__name__,
            latency_ms=(perf_counter() - start) * 1000,
        )


def compare_judges(trials: list[Trial]) -> list[dict]:
    rows = []
    for trial in trials:
        scores = {(m.framework, m.metric): m.score for m in trial.metrics if m.status == "scored"}
        for name, reason in SEMANTICS.items():
            left, right = scores.get(("deepeval", name)), scores.get(("ragas", name))
            if left is not None and right is not None:
                rows.append(
                    {
                        "case_id": trial.case_id,
                        "repetition": trial.repetition,
                        "metric": name,
                        "deepeval": left,
                        "ragas": right,
                        "ragas_minus_deepeval": right - left,
                        "method_difference": reason,
                    }
                )
    return rows

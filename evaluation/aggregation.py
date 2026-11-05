from collections import Counter, defaultdict
from statistics import fmean, pstdev

from app.telemetry import percentile
from evaluation.models import Trial

INJECTION_CATEGORIES = {
    "direct-injection",
    "indirect-injection",
    "conflicting-instructions",
    "untrusted-source",
}


def distribution(values: list[float]) -> dict:
    if not values:
        return dict.fromkeys(("mean", "stddev", "min", "max", "p50", "p95")) | {"count": 0}
    return {
        "count": len(values),
        "mean": fmean(values),
        "stddev": pstdev(values),
        "min": min(values),
        "max": max(values),
        "p50": percentile(values, 0.5),
        "p95": percentile(values, 0.95),
    }


def ratio(values) -> float | None:
    flags = list(values)
    return fmean(flags) if flags else None


def summarize(trials: list[Trial], hallucination_cutoff: float) -> dict:
    by_case = defaultdict(list)
    by_safety = defaultdict(list)
    metric_scores = defaultdict(list)
    metric_statuses = defaultdict(Counter)
    judge_latencies = []
    for trial in trials:
        by_case[trial.case_id].append(trial)
        if trial.safety is not None:
            by_safety[trial.category].append(trial.safety)
        for metric in trial.metrics:
            key = f"{metric.framework}.{metric.metric}"
            metric_statuses[key][metric.status] += 1
            if metric.score is not None:
                metric_scores[key].append(metric.score)
            if (
                metric.status != "not_applicable"
                and metric.framework != "deterministic"
                and (not metric.cached)
            ):
                judge_latencies.append(metric.latency_ms)
    repeated = {}
    for case_id, rows in by_case.items():
        scores = defaultdict(list)
        for row in rows:
            for metric in row.metrics:
                if metric.score is not None:
                    scores[f"{metric.framework}.{metric.metric}"].append(metric.score)
        repeated[case_id] = {
            "observations": len(rows),
            "failures": sum(row.status in {"fail", "error"} for row in rows),
            "unique_responses": len({row.output.answer for row in rows if row.output}),
            "latency_ms": distribution([row.output.latency_ms for row in rows if row.output]),
            "metrics": {name: distribution(values) for name, values in scores.items()},
        }

    outputs = [trial.output for trial in trials if trial.output]
    safety_rows = [row for rows in by_safety.values() for row in rows]
    status = Counter(trial.status for trial in trials)
    hallucinations = metric_scores["deepeval.hallucination"]
    costs = [answer.estimated_usd for answer in outputs if answer.estimated_usd is not None]
    return {
        "trials": dict(status),
        "request_count": len(trials),
        "error_rate": status["error"] / len(trials) if trials else None,
        "metrics": {
            name: {**distribution(metric_scores[name]), "statuses": dict(counts)}
            for name, counts in metric_statuses.items()
        },
        "golden_behavior_rate": ratio(t.status == "pass" for t in trials if t.case_id[0] == "G"),
        "conversation_pass_rate": ratio(
            t.status == "pass" for t in trials if t.category == "conversation"
        ),
        "hallucination_rate": ratio(score > hallucination_cutoff for score in hallucinations),
        "hallucination_evaluated": len(hallucinations),
        "hallucination_cutoff": hallucination_cutoff,
        "safety_pass_rate": ratio(row["pass"] for row in safety_rows),
        "injection_success_rate": ratio(
            row["marker_seen"]
            for category, rows in by_safety.items()
            if category in INJECTION_CATEGORIES
            for row in rows
        ),
        "synthetic_leakage_rate": ratio(row["leaked"] for row in safety_rows),
        "false_refusal_rate": ratio(row["false_refusal"] for row in by_safety["false-refusal"]),
        "safety_categories": {
            key: {
                "executed": len(rows),
                "passed": sum(row["pass"] for row in rows),
                "leaked": sum(row["leaked"] for row in rows),
                "marker_seen": sum(row["marker_seen"] for row in rows),
                "fixtures_exposed": sum(row["fixture_exposed"] for row in rows),
            }
            for key, rows in by_safety.items()
            if rows
        },
        "request_latency_ms": distribution([a.latency_ms for a in outputs]),
        "retrieval_latency_ms": distribution([a.retrieval_ms for a in outputs if a.retrieval_ms]),
        "generation_latency_ms": distribution(
            [a.generation_ms for a in outputs if a.generation_ms]
        ),
        "judge_latency_ms": distribution(judge_latencies),
        "generation_tokens": {
            direction: distribution(
                [count for answer in outputs if (count := getattr(answer, direction)) is not None]
            )
            for direction in ("input_tokens", "output_tokens")
        },
        "estimated_generation_usd": sum(costs) if costs else None,
        "estimated_cost_samples": len(costs),
        "repeatability": repeated,
    }

from collections import defaultdict
from hashlib import sha256
from statistics import fmean
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from evaluation.models import EvaluationRun, Gate, Trial


class Limit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Literal["min", "max"]
    threshold: float = Field(allow_inf_nan=False)
    max_regression: float = Field(ge=0, allow_inf_nan=False)


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hallucination_cutoff: float = Field(ge=0, le=1)
    case_drop: float = Field(gt=0, le=1)
    min_repetitions: int = Field(ge=1, le=5)
    limits: dict[str, Limit]


def measurement(summary: dict, name: str) -> float | None:
    if name == "request_p95_ms":
        return summary["request_latency_ms"]["p95"]
    if "." in name:
        return summary["metrics"].get(name, {}).get("mean")
    return summary.get(name)


def check_thresholds(
    summary: dict,
    policy: Policy,
    trials: list[Trial],
    judges: list[str],
    repetitions: int,
    include_safety: bool,
    include_conversations: bool,
) -> list[Gate]:
    skip = set()
    if "deepeval" not in judges:
        skip.add("hallucination_rate")
    if not include_safety:
        skip.update(
            {
                "safety_pass_rate",
                "synthetic_leakage_rate",
                "false_refusal_rate",
                "injection_success_rate",
            }
        )
    if not include_conversations:
        skip.add("conversation_pass_rate")
    gates = []
    if not judges:
        gates.append(
            Gate(
                name="judge_coverage",
                status="INCONCLUSIVE",
                reason="A semantic judge was not selected",
            )
        )
    if repetitions < policy.min_repetitions:
        gates.append(
            Gate(
                name="repetition_count",
                status="INCONCLUSIVE",
                reason=f"Requires at least {policy.min_repetitions} repetitions",
            )
        )
    for name, limit in policy.limits.items():
        if name in skip or ("." in name and name.split(".")[0] not in [*judges, "deterministic"]):
            continue
        value = measurement(summary, name)
        status = "INCONCLUSIVE"
        reason = "No applicable observations"
        if value is not None:
            passed = (
                value >= limit.threshold if limit.direction == "min" else value <= limit.threshold
            )
            status = "PASS" if passed else "FAIL"
            relation = ">=" if limit.direction == "min" else "<="
            reason = f"{value:.4g} observed. Requires {relation} {limit.threshold:.4g}."
        gates.append(Gate(name=name, status=status, reason=reason))
    for trial in trials:
        if trial.status == "error":
            gates.append(
                Gate(
                    name=f"{trial.case_id}/{trial.repetition}",
                    status="ERROR",
                    reason=trial.reason or "Trial failed to execute",
                )
            )
    return gates


def comparison_key(config: dict) -> str:
    import json

    return sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _by_case(trials: list[Trial]) -> dict:
    scores = defaultdict(list)
    for trial in trials:
        for metric in trial.metrics:
            if metric.score is not None:
                scores[(trial.case_id, f"{metric.framework}.{metric.metric}")].append(metric.score)
    return dict(scores)


def compare_baseline(
    current: EvaluationRun,
    baseline: EvaluationRun | None,
    policy: Policy,
    required: bool,
) -> tuple[list[Gate], list[dict]]:
    if baseline is None:
        return (
            [
                Gate(
                    name="baseline",
                    status="INCONCLUSIVE",
                    reason="No approved compatible baseline found",
                )
            ]
            if required
            else []
        ), []
    if current.comparison_key != baseline.comparison_key:
        return [
            Gate(
                name="baseline",
                status="INCONCLUSIVE",
                reason="Dataset, judge or controlled configuration differs",
            )
        ], []
    before, after = _by_case(baseline.trials), _by_case(current.trials)
    gates = []
    regressions = []
    for name, limit in policy.limits.items():
        old = measurement(baseline.summary, name)
        new = measurement(current.summary, name)
        if old is None:
            continue
        measured_metric = "deepeval.hallucination" if name == "hallucination_rate" else name
        aligned = all(
            len(before.get(key, [])) == len(after.get(key, []))
            for key in before.keys() | after.keys()
            if key[1] == measured_metric
        )
        if new is None or not aligned:
            gates.append(
                Gate(
                    name=f"baseline/{name}",
                    status="INCONCLUSIVE",
                    reason="Current observations do not match baseline coverage",
                )
            )
            continue
        deterioration = (old - new) if limit.direction == "min" else (new - old)
        passed = deterioration <= limit.max_regression + 1e-12
        gates.append(
            Gate(
                name=f"baseline/{name}",
                status="PASS" if passed else "FAIL",
                reason=f"{old:.4g} to {new:.4g}. Allowed deterioration {limit.max_regression:.4g}.",
            )
        )
    for (case, metric), values in before.items():
        current_scores = after.get((case, metric), [])
        if not current_scores:
            continue
        old, new = fmean(values), fmean(current_scores)
        drop = new - old if metric == "deepeval.hallucination" else old - new
        if drop >= policy.case_drop:
            regressions.append(
                {
                    "case_id": case,
                    "metric": metric,
                    "baseline": old,
                    "current": new,
                    "deterioration": drop,
                }
            )
    return gates, sorted(regressions, key=lambda row: row["deterioration"], reverse=True)

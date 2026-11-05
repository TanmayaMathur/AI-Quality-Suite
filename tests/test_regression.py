from pathlib import Path

from evaluation.aggregation import summarize
from evaluation.gates import Policy, check_thresholds, compare_baseline
from evaluation.models import EvaluationRun, MetricResult, Trial

POLICY = Policy.model_validate_json(Path("evaluation/policy.json").read_text())


def run(score: float, key: str = "same"):
    result = MetricResult(
        framework="deepeval",
        version="1",
        metric="faithfulness",
        status="scored",
        score=score,
    )
    trial = Trial(case_id="G001", category="factual", repetition=1, status="pass", metrics=[result])
    return EvaluationRun(
        run_id="example",
        timestamp="2026-01-01",
        git_sha=None,
        dataset_version="golden-v1",
        dataset_fingerprint="fixture",
        comparison_key=key,
        config={},
        trials=[trial],
        summary=summarize([trial], 0.5),
        gates=[],
    )


def test_regression_gate_catches_drop_even_above_absolute_floor():
    gates, _ = compare_baseline(run(0.78), run(0.95), POLICY, required=True)
    failed = [gate.name for gate in gates if gate.status == "FAIL"]
    assert failed == ["baseline/deepeval.faithfulness"]


def test_regression_lists_case_drop_and_rejects_mixed_versions():
    _, regressions = compare_baseline(run(0.7), run(0.96), POLICY, required=True)
    assert regressions[0]["case_id"] == "G001"
    gates, regressions = compare_baseline(run(0.7, "new"), run(0.96), POLICY, required=True)
    assert gates[0].status == "INCONCLUSIVE"
    assert not regressions


def test_required_baseline_unavailable_is_inconclusive():
    gates, _ = compare_baseline(run(0.9), None, POLICY, required=True)
    assert gates[0].status == "INCONCLUSIVE"


def test_judge_failure_is_an_error_not_a_missing_observation_pass():
    trial = Trial(
        case_id="G001", category="factual", repetition=1, status="error", reason="judge_timeout"
    )
    gates = check_thresholds(
        summarize([trial], 0.5), POLICY, [trial], ["deepeval"], 1, False, False
    )
    assert any(g.status == "ERROR" and g.reason == "judge_timeout" for g in gates)
    assert any(g.status == "INCONCLUSIVE" for g in gates)

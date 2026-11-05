from statistics import pstdev

import pytest

from evaluation.aggregation import distribution, summarize
from evaluation.datasets import read_dataset
from evaluation.execution import run_golden


class SampleJudge:
    framework = "deepeval"
    version = "test"
    names = ("faithfulness",)

    def __init__(self):
        self.calls = 0

    def score(self, name, sample):
        self.calls += 1
        return 0.9 - self.calls / 10, None


def test_repetitions_preserve_individual_responses_and_variance(pipeline):
    golden = read_dataset()[0][0]
    judge = SampleJudge()
    trials = []
    for run in range(1, 4):
        pipeline.model.reply = f"Variation {run}: Ethernet [1]."
        trials.append(run_golden(pipeline, golden, run, "grounded-v1", [judge]))
    assert judge.calls == 3
    assert [t.repetition for t in trials] == [1, 2, 3]
    summary = summarize(trials, 0.5)
    case = summary["repeatability"][golden.case_id]
    assert case["unique_responses"] == 3
    assert case["metrics"]["deepeval.faithfulness"]["mean"] == pytest.approx(0.7)
    assert case["metrics"]["deepeval.faithfulness"]["stddev"] == pytest.approx(
        pstdev([0.8, 0.7, 0.6])
    )
    assert summary["request_latency_ms"]["count"] == 3
    assert summary["estimated_generation_usd"] is None


def test_judge_cache_retains_each_generation_and_marks_reused_scores(pipeline):
    golden = read_dataset()[0][0]
    judge, cache = SampleJudge(), {}
    first = run_golden(pipeline, golden, 1, "grounded-v1", [judge], cache)
    second = run_golden(pipeline, golden, 2, "grounded-v1", [judge], cache)
    assert first.output.request_id != second.output.request_id
    assert judge.calls == 1
    assert second.metrics[-1].cached and second.metrics[-1].latency_ms == 0


def test_percentiles_are_nearest_rank_and_missing_is_explicit():
    assert distribution(list(range(1, 101)))["p95"] == 95
    assert distribution([])["p95"] is None

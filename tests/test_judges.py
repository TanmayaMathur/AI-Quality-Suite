import json
from importlib.util import find_spec

import httpx
import pytest

from app.contracts import Question, ServiceError
from evaluation.datasets import read_dataset
from evaluation.deepeval_runner import DeepEvalJudge
from evaluation.metrics import compare_judges, evaluate_metric
from evaluation.models import Sample, Trial
from evaluation.ragas_runner import RagasJudge


@pytest.fixture
def sample(pipeline):
    case = read_dataset()[0][0]
    output, passages = pipeline.answer(Question(question=case.question))
    return Sample(case, output, tuple(item.text for item in passages))


class Judge:
    framework = "deepeval"
    version = "fixture"

    def __init__(self, value):
        self.value = value

    def score(self, name, sample):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value, "The response used the bridge passage."


@pytest.mark.parametrize("value", [float("nan"), 1.01, ServiceError("judge_timeout", 504)])
def test_missing_or_invalid_scores_never_pass(sample, value):
    result = evaluate_metric(Judge(value), "faithfulness", sample)
    assert result.status == "error"
    assert result.score is None
    assert result.reason == ("judge_timeout" if isinstance(value, Exception) else "ValueError")


def test_compare_only_paired_semantically_related_scores(sample):
    score = evaluate_metric(Judge(0.8), "faithfulness", sample)
    ragas = score.model_copy(update={"framework": "ragas", "score": 0.9})
    hallucination = score.model_copy(update={"metric": "hallucination"})
    trial = Trial(
        case_id="G001",
        category="factual",
        repetition=1,
        status="pass",
        metrics=[score, ragas, hallucination],
    )
    rows = compare_judges([trial])
    assert len(rows) == 1
    assert rows[0]["ragas_minus_deepeval"] == pytest.approx(0.1)
    assert "claim" in rows[0]["method_difference"]


def test_ragas_cosine_relevancy_preserves_negative_observation(sample):
    judge = Judge(-0.2)
    judge.framework = "ragas"
    result = evaluate_metric(judge, "answer_relevancy", sample)
    assert result.status == "scored"
    assert result.score == -0.2
    assert evaluate_metric(judge, "faithfulness", sample).status == "error"


@pytest.mark.skipif(find_spec("deepeval") is None, reason="optional judge dependencies")
def test_deepeval_uses_reference_evidence_for_hallucination(sample):
    case = DeepEvalJudge.test_case(sample)
    assert case.context == [sample.case.evidence[0].quote]
    assert case.retrieval_context == list(sample.contexts)
    assert case.expected_output == sample.case.expected_answer


@pytest.mark.skipif(find_spec("deepeval") is None, reason="optional judge dependencies")
def test_deepeval_propagates_transport_timeout(sample):
    def handler(request):
        assert json.loads(request.content)["model"] == "fixture"
        raise httpx.ReadTimeout("internal address", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://local") as client:
        judge = DeepEvalJudge(client, "fixture", 42)
        result = evaluate_metric(judge, "faithfulness", sample)
    assert (result.status, result.reason) == ("error", "judge_timeout")


@pytest.mark.skipif(find_spec("ragas") is None, reason="optional judge dependencies")
def test_ragas_builds_pinned_metrics_and_shared_sample(sample):
    judge = RagasJudge("http://127.0.0.1:11434", "fixture", "bge-m3", 15, 42)
    case = judge.test_case(sample)
    assert case.user_input == sample.case.question
    assert case.retrieved_contexts == list(sample.contexts)
    assert case.reference == sample.case.expected_answer
    assert set(judge.metrics) == set(judge.names)

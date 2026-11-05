from asyncio import to_thread
from importlib.metadata import version

import httpx

from app.providers import request
from evaluation.models import Sample


class DeepEvalJudge:
    framework = "deepeval"
    names = (
        "answer_relevancy",
        "faithfulness",
        "context_precision",
        "context_recall",
        "hallucination",
    )

    def __init__(self, client: httpx.Client, model: str, seed: int):
        from deepeval.metrics import (
            AnswerRelevancyMetric,
            ContextualPrecisionMetric,
            ContextualRecallMetric,
            FaithfulnessMetric,
            HallucinationMetric,
        )
        from deepeval.models import DeepEvalBaseLLM

        self.version = version(self.framework)
        self.metrics = dict(
            zip(
                self.names,
                (
                    AnswerRelevancyMetric,
                    FaithfulnessMetric,
                    ContextualPrecisionMetric,
                    ContextualRecallMetric,
                    HallucinationMetric,
                ),
                strict=True,
            )
        )

        class LocalJudge(DeepEvalBaseLLM):
            def __init__(self):
                super().__init__(model_name=model)

            def load_model(self):
                return client

            def get_model_name(self):
                return f"ollama/{model}"

            def generate(self, prompt, schema=None):
                data = request(
                    client,
                    "judge",
                    "/api/chat",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "format": schema.model_json_schema() if schema else "json",
                        "options": {"temperature": 0, "seed": seed, "num_predict": 1200},
                        "stream": False,
                    },
                )
                output = data["message"]["content"]
                return schema.model_validate_json(output) if schema else output

            async def a_generate(self, prompt, schema=None):
                return await to_thread(self.generate, prompt, schema)

        self.judge = LocalJudge()

    @staticmethod
    def test_case(sample: Sample):
        from deepeval.test_case import LLMTestCase

        return LLMTestCase(
            input=sample.case.question,
            actual_output=sample.output.answer,
            expected_output=sample.case.expected_answer,
            context=[e.quote for e in sample.case.evidence],
            retrieval_context=list(sample.contexts),
        )

    def score(self, name: str, sample: Sample) -> tuple[float, str | None]:
        metric = self.metrics[name](model=self.judge, async_mode=False)
        score = metric.measure(self.test_case(sample), _show_indicator=False)
        return score, metric.reason

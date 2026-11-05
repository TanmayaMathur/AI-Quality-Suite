from importlib.metadata import version

from evaluation.models import Sample


class RagasJudge:
    framework = "ragas"
    names = ("answer_relevancy", "faithfulness", "context_precision", "context_recall")

    def __init__(
        self,
        base_url: str,
        model: str,
        embedding_model: str,
        timeout: float,
        seed: int,
    ):
        from langchain_ollama import ChatOllama, OllamaEmbeddings
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            Faithfulness,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
            ResponseRelevancy,
        )
        from ragas.run_config import RunConfig

        self.version = version(self.framework)
        if self.version != "0.2.15":
            raise RuntimeError("The Ragas adapter requires the locked 0.2.15 interface")
        run = RunConfig(timeout=timeout, max_retries=1, max_workers=1, seed=seed)
        chat = ChatOllama(
            base_url=base_url,
            model=model,
            format="json",
            temperature=0,
            seed=seed,
            num_predict=1200,
            client_kwargs={"timeout": timeout, "trust_env": False},
        )
        llm = LangchainLLMWrapper(chat, run_config=run)
        embeddings = LangchainEmbeddingsWrapper(
            OllamaEmbeddings(
                base_url=base_url,
                model=embedding_model,
                client_kwargs={"timeout": timeout, "trust_env": False},
            ),
            run_config=run,
        )
        self.metrics = {
            "answer_relevancy": ResponseRelevancy(llm=llm, embeddings=embeddings, strictness=1),
            "faithfulness": Faithfulness(llm=llm),
            "context_precision": LLMContextPrecisionWithReference(llm=llm),
            "context_recall": LLMContextRecall(llm=llm),
        }
        for metric in self.metrics.values():
            metric.init(run)

    @staticmethod
    def test_case(sample: Sample):
        from ragas import SingleTurnSample

        return SingleTurnSample(
            user_input=sample.case.question,
            response=sample.output.answer,
            retrieved_contexts=list(sample.contexts),
            reference=sample.case.expected_answer,
        )

    def score(self, name: str, sample: Sample) -> tuple[float, str | None]:
        score = self.metrics[name].single_turn_score(self.test_case(sample))
        return float(score), None

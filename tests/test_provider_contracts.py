import json
import sys

import httpx
import pytest

from app import ingest
from app.config import Settings
from app.contracts import Question, ServiceError
from app.providers import ChatModel, OllamaEmbeddings


def test_hosted_adapter_is_explicit_and_keeps_usage_optional():
    settings = Settings(
        _env_file=None,
        provider="hosted",
        allow_remote=True,
        hosted_url="https://judge.example/v1",
        hosted_key="synthetic-fixture",
        model="fixture-model",
        seed=42,
    )

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": settings.model}]})
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert body["seed"] == 42 and body["model"] == "fixture-model"
        assert [message["role"] for message in body["messages"]] == ["system", "user"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Wired Ethernet [1]."}}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 4},
            },
        )

    def local_handler(request):
        assert request.url.path == "/api/show"
        assert json.loads(request.content) == {"model": "bge-m3"}
        return httpx.Response(200, json={})

    with (
        httpx.Client(
            transport=httpx.MockTransport(handler), base_url=settings.hosted_url + "/"
        ) as client,
        httpx.Client(
            transport=httpx.MockTransport(local_handler), base_url=settings.ollama_url
        ) as local,
    ):
        generator = ChatModel(client, local, settings)
        generator.ready()
        result = generator.generate("system instructions", "question")
    assert result.input_tokens == 40
    assert result.output_tokens == 4


def test_ollama_embedding_contract_and_model_readiness():
    settings = Settings(_env_file=None, embedding_dimensions=2, seed=123)
    paths = []

    def handler(request):
        paths.append(request.url.path)
        body = json.loads(request.content)
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"model": body["model"]})
        if request.url.path == "/api/embed":
            assert body["truncate"] is False and body["input"] == ["bridge"]
            return httpx.Response(200, json={"embeddings": [[1.0, 0.0]]})
        assert body["options"]["seed"] == 123
        return httpx.Response(200, json={"message": {"content": "Ethernet [1]"}})

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=settings.ollama_url
    ) as local:
        model = ChatModel(local, local, settings)
        model.ready()
        assert OllamaEmbeddings(local, settings).embed(["bridge"]) == [[1.0, 0.0]]
        assert model.generate("rules", "question").input_tokens is None
    assert paths == ["/api/show", "/api/show", "/api/embed", "/api/chat"]


def test_price_estimates_only_exist_if_both_prices_and_counts_are_available(pipeline):
    pipeline.settings = pipeline.settings.model_copy(
        update={
            "usd_per_million_input": 1,
            "usd_per_million_output": 3,
        }
    )
    output, _ = pipeline.answer(Question(question="Does the bridge use a cable?"))
    assert output.estimated_usd == pytest.approx(0.000165)


def test_ingestion_cli_uses_root_and_returns_safe_dependency_error(
    monkeypatch, tmp_path, pipeline, capsys
):
    monkeypatch.setattr(sys, "argv", ["app.ingest", "--docs", str(tmp_path)])
    monkeypatch.setattr(ingest, "build_pipeline", lambda settings, stack: pipeline)

    def ingest_fixture(path):
        assert path == tmp_path
        return "fixture", 12

    pipeline.retriever.ingest = ingest_fixture
    assert ingest.main() == 0
    assert "Indexed 12 passages" in capsys.readouterr().out

    def fail(path):
        raise ServiceError("embedding_timeout", 504)

    pipeline.retriever.ingest = fail
    with pytest.raises(SystemExit) as error:
        ingest.main()
    assert error.value.code == 2
    assert capsys.readouterr().err == "Ingestion failed: embedding_timeout\n"

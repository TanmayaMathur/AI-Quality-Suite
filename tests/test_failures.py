from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from qdrant_client.http.exceptions import ResponseHandlingException

from app.config import Settings
from app.main import create_app
from app.providers import ChatModel, OllamaEmbeddings
from app.retrieval import VectorIndex


@pytest.mark.parametrize(
    ("scenario", "expected_status", "code"),
    [
        ("timeout", 504, "model_timeout"),
        ("network", 503, "model_unavailable"),
        ("bad-json", 503, "model_unavailable"),
        ("empty", 502, "model_invalid_response"),
    ],
)
def test_generation_dependency_failures(pipeline, scenario, expected_status, code):
    def handler(request):
        if scenario == "timeout":
            raise httpx.ReadTimeout("private detail", request=request)
        if scenario == "network":
            raise httpx.ConnectError("private detail", request=request)
        if scenario == "bad-json":
            return httpx.Response(200, text="invalid JSON")
        return httpx.Response(200, json={"message": {"content": ""}})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://localhost") as mock:
        pipeline.model = ChatModel(mock, mock, pipeline.settings)
        with TestClient(create_app(pipeline.settings, pipeline)) as client:
            answer = client.post("/ask", json={"question": "How does the Harbor Bridge work?"})
            assert answer.status_code == expected_status
            assert answer.json() == {"error": {"code": code}}
            assert client.get("/health").status_code == 200


def test_qdrant_transport_failure_is_safe_and_readiness_fails(pipeline):
    vectors = Mock()
    vectors.get_aliases.side_effect = ResponseHandlingException(OSError("private detail"))
    pipeline.retriever = VectorIndex(vectors, Mock(), pipeline.settings)
    with TestClient(create_app(pipeline.settings, pipeline)) as client:
        for response in [client.get("/ready"), client.post("/ask", json={"question": "bridge?"})]:
            assert response.status_code == 503
            assert response.json() == {"error": {"code": "vector_unavailable"}}


@pytest.mark.parametrize("payload", [{"embeddings": []}, {"wrong": "shape"}])
def test_embedding_invalid_response_is_bounded(pipeline, payload):
    def handler(request):
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://localhost") as mock:
        vectors = Mock()
        vectors.get_aliases.return_value.aliases = [
            Mock(alias_name=pipeline.settings.collection, collection_name="test"),
        ]
        pipeline.retriever = VectorIndex(
            vectors, OllamaEmbeddings(mock, pipeline.settings), pipeline.settings
        )
        with TestClient(create_app(pipeline.settings, pipeline)) as client:
            response = client.post("/ask", json={"question": "bridge?"})
            assert response.status_code == 502
            assert response.json() == {"error": {"code": "embedding_invalid_response"}}
            vectors.query_points.assert_not_called()


def test_config_refuses_implicit_remote_transfer():
    with pytest.raises(ValueError, match="Remote services require"):
        Settings(_env_file=None, ollama_url="https://ollama.example")
    with pytest.raises(ValueError, match="Hosted generation requires"):
        Settings(_env_file=None, provider="hosted")


def test_service_url_with_embedded_credential_is_rejected_without_echo():
    with pytest.raises(ValueError, match="without credentials") as error:
        Settings(_env_file=None, ollama_url="https://:fixture-secret@localhost")
    assert "fixture-secret" not in str(error.value)

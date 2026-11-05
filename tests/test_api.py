import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(pipeline):
    with TestClient(create_app(pipeline.settings, pipeline)) as client:
        yield client


def test_operational_endpoints(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}
    assert "/ask" in client.get("/openapi.json").json()["paths"]
    assert client.get("/metrics").json()["p95_ms"] is None
    reply = client.post("/ask", json={"question": "How does the Harbor Bridge connect?"})
    assert reply.status_code == 200
    body = reply.json()
    assert body["answer"] == "The Harbor Bridge uses Ethernet [1]."
    assert [s["document_id"] for s in body["sources"]] == ["bridge"]
    assert body["input_tokens"] == 120
    assert body["latency_ms"] >= body["generation_ms"] >= 0
    assert client.get("/metrics").json()["requests"] == 1


@pytest.mark.parametrize(
    "payload",
    [{"question": "   "}, {"question": "a" * 1501}, {"question": "valid", "unexpected": True}],
)
def test_invalid_input_has_safe_error(client, payload):
    reply = client.post("/ask", json=payload)
    assert reply.status_code == 422
    assert reply.json() == {"error": {"code": "invalid_request"}}
    assert client.get("/metrics").json()["error_rate"] == 1


def test_invalid_json(client):
    reply = client.post("/ask", content="{", headers={"Content-Type": "application/json"})
    assert reply.status_code == 422


def test_baseline_requires_opt_in(client):
    reply = client.post("/ask", json={"question": "How?", "prompt_version": "baseline-v1"})
    assert reply.status_code == 422
    assert reply.json()["error"]["code"] == "baseline_disabled"

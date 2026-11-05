import pytest
from fastapi.testclient import TestClient

from app.contracts import ServiceError
from app.main import create_app
from app.sessions import MemorySessions


def test_sessions_followup_switch_and_window(pipeline):
    store = MemorySessions(10, 3, 2)
    with TestClient(create_app(pipeline.settings, pipeline, store)) as client:
        first, second = [client.post("/sessions").json()["session_id"] for _ in range(2)]
        path = f"/sessions/{first}"
        assert (
            client.post(
                path + "/messages", json={"question": "How does Harbor Bridge connect?"}
            ).status_code
            == 200
        )
        assert client.get(f"/sessions/{second}/history").json() == []
        reply = client.post(path + "/messages", json={"question": "Does it need a cable?"})
        assert reply.json()["session_id"] == first
        assert "Harbor Bridge" in pipeline.retriever.query
        assert pipeline.model.user["dialogue"][0]["question"].startswith("How")
        pipeline.model.reply = "Drift uses 2.4 GHz [2]."
        assert (
            client.post(path + "/messages", json={"question": "Now switch to Drift."}).json()[
                "sources"
            ][0]["document_id"]
            == "relay"
        )
        assert [t["question"] for t in client.get(path + "/history").json()] == [
            "Does it need a cable?",
            "Now switch to Drift.",
        ]
        assert client.get("/sessions/unknown/history").status_code == 404


def test_capacity_expiration_and_no_history_on_failed_request():
    now = [0]
    sessions = MemorySessions(10, 1, 1, clock=lambda: now[0])
    first = sessions.create()
    with pytest.raises(ServiceError, match="session_capacity"):
        sessions.create()

    def fail(history):
        assert history == []
        raise ServiceError("model_timeout", 504)

    with pytest.raises(ServiceError, match="model_timeout"):
        sessions.append(first, "This must not persist.", fail)
    assert sessions.history(first) == []
    now[0] = 10
    with pytest.raises(ServiceError, match="session_not_found"):
        sessions.history(first)
    assert sessions.create() != first

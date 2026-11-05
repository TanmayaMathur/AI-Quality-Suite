import os
from contextlib import ExitStack
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import build_pipeline, create_app

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("AQS_RUN_LIVE") != "1", reason="explicit local live opt-in"),
]


def test_real_retrieval_and_model_generation_over_fastapi():
    settings = Settings(provider="ollama", allow_remote=False, temperature=0, seed=42)
    with ExitStack() as stack:
        pipeline = build_pipeline(settings, stack)
        pipeline.retriever.ingest(Path("data/docs"))
        with TestClient(create_app(settings, pipeline)) as client:
            assert client.get("/ready").status_code == 200
            response = client.post(
                "/ask",
                json={
                    "question": "Which battery model does the Lumenvale Morrow contact sensor use?",
                },
            )
        assert response.status_code == 200
        answer = response.json()
        assert answer["outcome"] == "answered"
        assert "CR2450" in answer["answer"]
        assert "morrow-sensor" in {source["document_id"] for source in answer["sources"]}
        assert answer["generation_ms"] > 0
        assert answer["output_tokens"] > 0

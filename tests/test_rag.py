import pytest
from qdrant_client import QdrantClient

from app.config import Settings
from app.contracts import Question
from app.retrieval import VectorIndex


class ColorEmbeddings:
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[1.0, 0.0] if "teal" in text else [0.0, 1.0] for text in texts]

    def revision(self):
        return "fixture-v1"


def test_llamaindex_chunks_qdrant_indexes_and_switches(tmp_path):
    (tmp_path / "teal.md").write_text("teal lamps use Thread. " * 24)
    (tmp_path / "rust.md").write_text("rust plugs use Ethernet.")
    settings = Settings(_env_file=None, embedding_dimensions=2, chunk_words=32, overlap_words=4)
    embedder = ColorEmbeddings()
    client = QdrantClient(":memory:")
    index = VectorIndex(client, embedder, settings)
    try:
        original, count = index.ingest(tmp_path)
        assert count > 2
        index.ready()
        calls = embedder.calls
        assert index.ingest(tmp_path) == (original, count)
        assert embedder.calls == calls
        before = index.retrieve("teal lamp?")
        assert all(p.source.document_id == "teal" for p in before)
        assert len({p.source.chunk_id for p in before}) == len(before)
        (tmp_path / "teal.md").unlink()
        assert index.ingest(tmp_path)[0] != original
        assert index.retrieve("teal lamp?") == []
    finally:
        client.close()


@pytest.mark.parametrize(
    "reply",
    ["UNKNOWN", "An unsupported claim.", "False [99]", "Bad [0]", "[1]", "UNKNOWN [1]"],
)
def test_unanswerable_or_invalid_citations_abstain(pipeline, reply):
    pipeline.model.reply = reply
    result, _ = pipeline.answer(Question(question="What is the warranty?"))
    assert result.outcome == "abstained"
    assert result.sources == []


def test_empty_retrieval_never_calls_model(pipeline):
    pipeline.retriever.passages = []
    result, passages = pipeline.answer(Question(question="What is the warranty?"))
    assert result.outcome == "abstained"
    assert result.generation_ms == 0
    assert passages == []
    assert pipeline.model.user is None


def test_citations_follow_output_order_and_deduplicate(pipeline):
    pipeline.model.reply = "Wi-Fi [2], Ethernet [1], and Wi-Fi again [2]."
    result, _ = pipeline.answer(Question(question="Compare the radios."))
    assert [s.document_id for s in result.sources] == ["relay", "bridge"]

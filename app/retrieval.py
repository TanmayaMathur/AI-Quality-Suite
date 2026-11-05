import re
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ApiException

from app.config import Settings
from app.contracts import Embedder, Passage, ServiceError, Source


class VectorIndex:
    def __init__(self, client: QdrantClient, embedder: Embedder, settings: Settings):
        self.client, self.embedder, self.settings = client, embedder, settings

    def _active(self) -> str:
        aliases = self.client.get_aliases().aliases
        for alias in aliases:
            if alias.alias_name == self.settings.collection:
                return alias.collection_name
        raise ServiceError("index_not_ingested", 503)

    def ready(self):
        try:
            self.client.get_collection(self._active())
        except (ApiException, OSError, ValueError):
            raise ServiceError("vector_unavailable", 503) from None

    def retrieve(self, query: str) -> list[Passage]:
        try:
            collection = self._active()
            vector = self.embedder.embed([query])[0]
            hits = self.client.query_points(
                collection,
                query=vector,
                limit=self.settings.top_k,
                score_threshold=self.settings.score_floor,
                with_payload=True,
            ).points
            return [
                Passage(
                    Source(
                        document_id=hit.payload["document_id"],
                        chunk_id=str(hit.id),
                        relevance_score=hit.score,
                    ),
                    hit.payload["text"],
                )
                for hit in hits
            ]
        except (ApiException, OSError, ValueError, KeyError, TypeError):
            raise ServiceError("vector_unavailable", 503) from None

    def ingest(self, directory: Path) -> tuple[str, int]:
        from llama_index.core.node_parser import SentenceSplitter

        settings = self.settings
        splitter = SentenceSplitter(
            chunk_size=settings.chunk_words,
            chunk_overlap=settings.overlap_words,
            tokenizer=str.split,
            chunking_tokenizer_fn=lambda text: re.split(r"(?<=[.!?])(?=\s)", text),
            secondary_chunking_regex=r"[^,.;!?]+[,.;!?]?",
        )
        chunks = [
            (path.stem, ordinal, chunk)
            for path in sorted(directory.glob("*.md"))
            for ordinal, chunk in enumerate(splitter.split_text(path.read_text(encoding="utf-8")))
            if chunk.strip()
        ]
        if not chunks:
            raise ValueError("No nonempty Markdown source documents")
        digest = sha256(
            repr(
                (
                    "word-splitter-v1",
                    settings.embedding_model,
                    self.embedder.revision(),
                    settings.embedding_dimensions,
                    chunks,
                )
            ).encode()
        ).hexdigest()[:20]
        name = f"{settings.collection}_{digest}"
        try:
            aliases = self.client.get_aliases().aliases
            active = next(
                (a.collection_name for a in aliases if a.alias_name == settings.collection),
                None,
            )
            if active == name:
                return name, len(chunks)
            if not self.client.collection_exists(name):
                self.client.create_collection(
                    name,
                    vectors_config=models.VectorParams(
                        size=settings.embedding_dimensions,
                        distance=models.Distance.COSINE,
                    ),
                )
            for start in range(0, len(chunks), 16):
                batch = chunks[start : start + 16]
                vectors = self.embedder.embed([chunk for _, _, chunk in batch])
                points = [
                    models.PointStruct(
                        id=str(uuid5(NAMESPACE_URL, f"{doc}/{ordinal}/{chunk}")),
                        vector=vector,
                        payload={"document_id": doc, "text": chunk, "ordinal": ordinal},
                    )
                    for (doc, ordinal, chunk), vector in zip(batch, vectors, strict=True)
                ]
                self.client.upsert(name, points, wait=True)
            updates = []
            if active:
                updates.append(
                    models.DeleteAliasOperation(
                        delete_alias=models.DeleteAlias(alias_name=settings.collection),
                    )
                )
            updates.append(
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(
                        collection_name=name, alias_name=settings.collection
                    ),
                )
            )
            self.client.update_collection_aliases(updates)
            return name, len(chunks)
        except (ApiException, OSError):
            raise ServiceError("vector_unavailable", 503) from None

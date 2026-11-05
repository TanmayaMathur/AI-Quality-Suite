from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field

Prompt = Literal["baseline-v1", "grounded-v1"]


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=1500)
    prompt_version: Prompt = "grounded-v1"

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}


class Source(BaseModel):
    document_id: str
    chunk_id: str
    relevance_score: float


class Answer(BaseModel):
    answer: str
    outcome: Literal["answered", "abstained", "refused"]
    sources: list[Source]
    request_id: str
    session_id: str | None = None
    latency_ms: float
    retrieval_ms: float = 0
    generation_ms: float = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_usd: float | None = None


class Turn(BaseModel):
    question: str
    answer: str


@dataclass(frozen=True)
class Passage:
    source: Source
    text: str


@dataclass(frozen=True)
class Generation:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ServiceError(Exception):
    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.code = code
        self.status = status


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def revision(self) -> str: ...


class Generator(Protocol):
    def generate(self, system: str, user: str) -> Generation: ...

    def ready(self) -> None: ...


class Retriever(Protocol):
    def retrieve(self, query: str) -> list[Passage]: ...

    def ready(self) -> None: ...

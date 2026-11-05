from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AQS_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    ollama_url: str = "http://127.0.0.1:11434"
    qdrant_url: str = "http://127.0.0.1:6333"
    collection: str = Field(default="lumenvale", pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    embedding_model: str = "bge-m3"
    embedding_dimensions: int = Field(default=1024, ge=1, le=8192)
    provider: Literal["ollama", "hosted"] = "ollama"
    model: str = "qwen2.5:3b"
    hosted_url: str = ""
    hosted_key: SecretStr | None = None
    allow_remote: bool = False
    timeout_s: float = Field(default=90, gt=0, le=600)
    temperature: float = Field(default=0.2, ge=0, le=2)
    seed: int | None = None
    max_tokens: int = Field(default=384, ge=32, le=2048)
    chunk_words: int = Field(default=150, ge=32, le=600)
    overlap_words: int = Field(default=20, ge=0)
    top_k: int = Field(default=4, ge=1, le=12)
    score_floor: float = Field(default=0.25, ge=-1, le=1)
    session_ttl_s: float = Field(default=1800, gt=0)
    session_capacity: int = Field(default=500, ge=1)
    history_turns: int = Field(default=4, ge=1, le=12)
    allow_baseline: bool = False
    refusal: str = "I can help with public Lumenvale product information only."
    abstention: str = "I do not have enough verified information to answer that."
    input_guard: bool = True
    usd_per_million_input: float | None = Field(default=None, ge=0)
    usd_per_million_output: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_configuration(self):
        if self.overlap_words >= self.chunk_words:
            raise ValueError("Chunk overlap must be smaller than the chunk size")
        for url in (self.ollama_url, self.qdrant_url, self.hosted_url):
            if not url:
                continue
            parsed = urlsplit(url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Service URLs must use HTTP(S) without credentials or queries")
            if not self.allow_remote and parsed.hostname not in {
                "localhost",
                "127.0.0.1",
                "::1",
                "qdrant",
                "ollama",
            }:
                raise ValueError("Remote services require AQS_ALLOW_REMOTE=true")
        if self.provider == "hosted" and not (
            self.allow_remote and self.hosted_key and self.hosted_url.startswith("https://")
        ):
            raise ValueError("Hosted generation requires opt-in, HTTPS, and an API key")
        return self

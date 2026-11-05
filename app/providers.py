from math import isfinite

import httpx

from app.config import Settings
from app.contracts import Generation, ServiceError


def request(client: httpx.Client, service: str, path: str, **kwargs):
    try:
        response = client.request("POST" if "json" in kwargs else "GET", path, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        raise ServiceError(f"{service}_timeout", 504) from None
    except (httpx.HTTPError, ValueError):
        raise ServiceError(f"{service}_unavailable", 503) from None


def ollama_digests(client: httpx.Client, names: list[str]) -> dict[str, str]:
    tags = request(client, "model", "/api/tags")
    try:
        available = {item["name"]: item["digest"] for item in tags["models"]}
    except (TypeError, KeyError):
        raise ServiceError("model_invalid_response", 502) from None
    revisions = {}
    for name in names:
        key = name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"
        digest = available.get(key)
        if not digest:
            raise ServiceError("required_model_not_pulled", 503)
        revisions[name] = digest
    return revisions


class OllamaEmbeddings:
    def __init__(self, client: httpx.Client, settings: Settings):
        self.client = client
        self.settings = settings

    def revision(self) -> str:
        name = self.settings.embedding_model
        return ollama_digests(self.client, [name])[name]

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = request(
            self.client,
            "embedding",
            "/api/embed",
            json={"model": self.settings.embedding_model, "input": texts, "truncate": False},
        )
        try:
            vectors = payload["embeddings"]
            if len(vectors) != len(texts) or any(
                len(v) != self.settings.embedding_dimensions or not all(map(isfinite, v))
                for v in vectors
            ):
                raise ValueError
            return vectors
        except (KeyError, TypeError, ValueError):
            raise ServiceError("embedding_invalid_response", 502) from None


class ChatModel:
    def __init__(self, client: httpx.Client, local: httpx.Client, settings: Settings):
        self.client, self.local, self.settings = client, local, settings

    def ready(self):
        request(
            self.local,
            "embedding",
            "/api/show",
            json={"model": self.settings.embedding_model},
        )
        if self.settings.provider == "ollama":
            request(self.local, "model", "/api/show", json={"model": self.settings.model})
        else:
            request(self.client, "model", "models")

    def generate(self, system: str, user: str) -> Generation:
        settings = self.settings
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        payload = {"model": settings.model, "messages": messages, "stream": False}
        if settings.provider == "ollama":
            options = {"temperature": settings.temperature, "num_predict": settings.max_tokens}
            if settings.seed is not None:
                options["seed"] = settings.seed
            data = request(
                self.client,
                "model",
                "/api/chat",
                json={**payload, "options": options},
            )
        else:
            options = {"temperature": settings.temperature, "max_tokens": settings.max_tokens}
            if settings.seed is not None:
                options["seed"] = settings.seed
            data = request(
                self.client,
                "model",
                "chat/completions",
                json={**payload, **options},
            )
        try:
            if settings.provider == "ollama":
                text = data["message"]["content"]
                tokens = (data.get("prompt_eval_count"), data.get("eval_count"))
            else:
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                tokens = (usage.get("prompt_tokens"), usage.get("completion_tokens"))
            if not isinstance(text, str) or not text.strip():
                raise ValueError
            return Generation(text, *(n if type(n) is int and n >= 0 else None for n in tokens))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise ServiceError("model_invalid_response", 502) from None

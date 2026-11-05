import json
import logging
from contextlib import ExitStack, asynccontextmanager
from time import perf_counter

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient

from app.config import Settings
from app.contracts import Answer, Question, ServiceError, Turn
from app.pipeline import Pipeline
from app.providers import ChatModel, OllamaEmbeddings
from app.retrieval import VectorIndex
from app.safety import scrub
from app.sessions import MemorySessions, SessionStore
from app.telemetry import Telemetry

logger = logging.getLogger("uvicorn.error.ai_quality_suite")


def build_pipeline(settings: Settings, stack: ExitStack) -> Pipeline:
    local = stack.enter_context(
        httpx.Client(
            base_url=settings.ollama_url,
            timeout=settings.timeout_s,
            trust_env=False,
        )
    )
    model_client = local
    if settings.provider == "hosted":
        model_client = stack.enter_context(
            httpx.Client(
                base_url=settings.hosted_url.rstrip("/") + "/",
                timeout=settings.timeout_s,
                headers={"Authorization": f"Bearer {settings.hosted_key.get_secret_value()}"},
                trust_env=False,
            )
        )
    vectors = QdrantClient(
        url=settings.qdrant_url,
        timeout=min(settings.timeout_s, 10),
        check_compatibility=False,
        trust_env=False,
    )
    stack.callback(vectors.close)
    index = VectorIndex(vectors, OllamaEmbeddings(local, settings), settings)
    return Pipeline(index, ChatModel(model_client, local, settings), settings)


def create_app(
    settings: Settings | None = None,
    pipeline: Pipeline | None = None,
    sessions: SessionStore | None = None,
) -> FastAPI:
    settings = settings or Settings()
    sessions = sessions or MemorySessions(
        settings.session_ttl_s,
        settings.session_capacity,
        settings.history_turns,
    )
    telemetry = Telemetry()

    @asynccontextmanager
    async def lifespan(api: FastAPI):
        with ExitStack() as stack:
            api.state.pipeline = pipeline or build_pipeline(settings, stack)
            yield

    api = FastAPI(title="AI Quality Suite", version="0.1.0", lifespan=lifespan)

    @api.middleware("http")
    async def measure(request: Request, call_next):
        start = perf_counter()
        response = await call_next(request)
        if request.method == "POST":
            latency = (perf_counter() - start) * 1000
            telemetry.record(latency, response.status_code >= 400)
            logger.info(
                json.dumps(
                    {
                        "event": "request",
                        "status": response.status_code,
                        "latency_ms": round(latency, 2),
                    }
                )
            )
        return response

    @api.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError):
        return JSONResponse(status_code=error.status, content={"error": {"code": error.code}})

    @api.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request"}})

    @api.get("/health")
    def health():
        return {"status": "ok"}

    @api.get("/ready")
    def ready(request: Request):
        request.app.state.pipeline.ready()
        return {"status": "ready"}

    @api.post("/ask")
    def ask(question: Question, request: Request) -> Answer:
        return request.app.state.pipeline.answer(question)[0]

    @api.post("/sessions", status_code=201)
    def create_session():
        return {"session_id": sessions.create()}

    @api.post("/sessions/{session_id}/messages")
    def message(session_id: str, question: Question, request: Request) -> Answer:
        return sessions.append(
            session_id,
            scrub(question.question),
            lambda history: request.app.state.pipeline.answer(question, history, session_id)[0],
        )

    @api.get("/sessions/{session_id}/history")
    def history(session_id: str) -> list[Turn]:
        return sessions.history(session_id)

    @api.get("/metrics")
    def metrics():
        return telemetry.snapshot()

    return api


app = create_app()

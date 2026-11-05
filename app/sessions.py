from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Protocol
from uuid import uuid4

from app.contracts import Answer, ServiceError, Turn

Reply = Callable[[list[Turn]], Answer]


class SessionStore(Protocol):
    def create(self) -> str: ...
    def history(self, key: str) -> list[Turn]: ...
    def append(self, key: str, question: str, reply: Reply) -> Answer: ...


@dataclass
class Session:
    expires: float
    turns: list[Turn] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)


class MemorySessions:
    def __init__(self, ttl: float, capacity: int, history_turns: int, clock=monotonic):
        self.ttl, self.capacity, self.history_turns = ttl, capacity, history_turns
        self.clock = clock
        self.sessions: dict[str, Session] = {}
        self.lock = Lock()

    def create(self) -> str:
        with self.lock:
            now = self.clock()
            self.sessions = {
                key: s for key, s in self.sessions.items() if s.expires > now or s.lock.locked()
            }
            if len(self.sessions) >= self.capacity:
                raise ServiceError("session_capacity", 429)
            key = uuid4().hex
            self.sessions[key] = Session(now + self.ttl)
            return key

    def _get(self, key: str) -> Session:
        with self.lock:
            session = self.sessions.get(key)
            if session is None or session.expires <= self.clock():
                raise ServiceError("session_not_found", 404)
            return session

    def history(self, key: str) -> list[Turn]:
        session = self._get(key)
        with session.lock:
            return [turn.model_copy() for turn in session.turns]

    def append(self, key: str, question: str, reply: Reply) -> Answer:
        session = self._get(key)
        with session.lock:
            if self._get(key) is not session:
                raise ServiceError("session_not_found", 404)
            answer = reply(session.turns.copy())
            session.turns = [
                *session.turns,
                Turn(question=question, answer=answer.answer),
            ][-self.history_turns :]
            session.expires = self.clock() + self.ttl
            return answer

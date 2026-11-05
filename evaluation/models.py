from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from app.contracts import Answer
from evaluation.datasets import Golden


@dataclass(frozen=True)
class Sample:
    case: Golden
    output: Answer
    contexts: tuple[str, ...]


class MetricResult(BaseModel):
    framework: str
    version: str
    metric: str
    status: Literal["scored", "error", "not_applicable"]
    score: float | None = Field(default=None, ge=-1, le=1, allow_inf_nan=False)
    reason: str | None = None
    latency_ms: float = 0
    cached: bool = False

    @model_validator(mode="after")
    def score_matches_status(self):
        if (self.score is not None) != (self.status == "scored"):
            raise ValueError("Only scored metrics have numeric values")
        if (
            self.score is not None
            and self.score < 0
            and (self.framework, self.metric) != ("ragas", "answer_relevancy")
        ):
            raise ValueError("Only Ragas cosine-based relevancy can be negative")
        return self


class Judge(Protocol):
    framework: str
    version: str
    names: tuple[str, ...]

    def score(self, name: str, sample: Sample) -> tuple[float, str | None]: ...


class Trial(BaseModel):
    case_id: str
    category: str
    repetition: int
    status: Literal["pass", "fail", "error", "observed"]
    output: Answer | None = None
    retrieved_documents: list[str] = Field(default_factory=list)
    metrics: list[MetricResult] = Field(default_factory=list)
    reason: str | None = None
    safety: dict[str, bool] | None = None


class Gate(BaseModel):
    name: str
    status: Literal["PASS", "FAIL", "INCONCLUSIVE", "ERROR"]
    reason: str


class EvaluationRun(BaseModel):
    run_id: str
    timestamp: str
    git_sha: str | None
    dataset_version: str
    dataset_fingerprint: str
    comparison_key: str
    config: dict
    trials: list[Trial]
    summary: dict
    gates: list[Gate]
    baseline_run_id: str | None = None
    baseline_eligible: bool = False
    regressions: list[dict] = Field(default_factory=list)
    comparisons: list[dict] = Field(default_factory=list)
    promptfoo: dict | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def decision(self) -> str:
        states = {gate.status for gate in self.gates}
        if self.errors or "ERROR" in states:
            return "ERROR"
        if "FAIL" in states:
            return "FAIL"
        if "INCONCLUSIVE" in states or not states:
            return "INCONCLUSIVE"
        return "PASS"

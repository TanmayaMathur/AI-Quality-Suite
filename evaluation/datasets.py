import argparse
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

DATA = Path("data")


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_id: str
    question: str = Field(min_length=8, max_length=1500)
    evaluation_notes: str = Field(min_length=10)


class Evidence(BaseModel):
    document_id: str
    quote: str = Field(min_length=20)


class Golden(Record):
    case_id: str = Field(pattern=r"^G[0-9]{3}$")
    expected_answer: str = Field(min_length=8)
    source_documents: list[str]
    category: Literal[
        "factual",
        "multi-hop",
        "comparison",
        "numerical",
        "context-dependent",
        "unanswerable",
        "ambiguous",
        "source-attribution",
    ]
    tags: list[str] = Field(min_length=1)
    difficulty: Literal["easy", "medium", "hard"]
    evidence: list[Evidence]
    must_include: list[str]


class Adversarial(Record):
    case_id: str = Field(pattern=r"^S[0-9]{3}$")
    category: Literal[
        "direct-injection",
        "indirect-injection",
        "rule-bypass",
        "synthetic-leakage",
        "false-refusal",
        "conflicting-instructions",
        "untrusted-source",
    ]
    expected_outcome: Literal["answered", "deny"]
    required: list[str]
    forbidden: list[str]
    fixture: str | None = Field(pattern=r"^[a-z-]+[0-9]+$")


T = TypeVar("T", bound=Record)


def load_records(path: Path, schema: type[T]) -> list[T]:
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            records.append(schema.model_validate_json(line))
        except ValidationError as exc:
            raise ValueError(f"{path.name}:{number}: invalid {schema.__name__} record") from exc
    for field in ("case_id", "question"):
        values = [getattr(row, field).casefold() for row in records]
        if len(values) != len(set(values)):
            raise ValueError(f"{path.name}: duplicate {field}")
    return records


def snapshot(directory: Path) -> dict[str, str]:
    return {path.stem: path.read_text(encoding="utf-8") for path in sorted(directory.glob("*.md"))}


def read_dataset(root: Path = DATA) -> tuple[list[Golden], list[Adversarial], dict]:
    golden = load_records(root / "golden_v1.jsonl", Golden)
    safety = load_records(root / "adversarial.jsonl", Adversarial)
    documents, fixtures = snapshot(root / "docs"), snapshot(root / "safety")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for row in golden:
        ids = {item.document_id for item in row.evidence}
        if ids != set(row.source_documents) or len(row.source_documents) != len(ids):
            raise ValueError(f"{row.case_id}: evidence and source IDs differ")
        if bool(ids) == (row.category == "unanswerable"):
            raise ValueError(f"{row.case_id}: incorrect evidence for answerability")
        for span in row.evidence:
            if span.quote not in documents.get(span.document_id, ""):
                raise ValueError(f"{row.case_id}: evidence quote absent from {span.document_id}")
    for attack in safety:
        if attack.fixture is not None and attack.fixture not in fixtures:
            raise ValueError(f"{attack.case_id}: fixture not found")
        if attack.expected_outcome == "answered" and not attack.required:
            raise ValueError(f"{attack.case_id}: public answer requires a factual check")
        if any(not term.strip() for term in [*attack.required, *attack.forbidden]):
            raise ValueError(f"{attack.case_id}: empty safety assertion")
    counts = {
        "golden_count": len(golden),
        "adversarial_count": len(safety),
        "document_count": len(documents),
        "safety_fixture_count": len(fixtures),
        "golden_categories": dict(Counter(row.category for row in golden)),
        "adversarial_categories": dict(Counter(row.category for row in safety)),
    }
    if (
        len(golden) < 60
        or len(documents) < 10
        or len(counts["golden_categories"]) != 8
        or len(counts["adversarial_categories"]) != 7
        or min(counts["adversarial_categories"].values()) < 5
    ):
        raise ValueError("Dataset does not meet required coverage")
    for field, actual in counts.items():
        if actual != manifest.get(field):
            raise ValueError(f"Manifest mismatch for {field}")
    fingerprint = sha256(
        json.dumps(
            {
                "golden": [row.model_dump() for row in golden],
                "safety": [row.model_dump() for row in safety],
                "documents": documents,
                "fixtures": fixtures,
                "manifest": manifest,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return golden, safety, {**manifest, "fingerprint": fingerprint, "validation": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate synthetic evaluation fixtures")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--output", type=Path, default=Path("reports/dataset-validation.json"))
    args = parser.parse_args()
    try:
        _, _, result = read_dataset(args.data)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Dataset validation failed: {exc}\n")
    output = json.dumps(result, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from evaluation.datasets import DATA, read_dataset


def make_cases(data: Path, output: Path, limit: int | None, case_ids: list[str]):
    golden, _, _ = read_dataset(data)
    if case_ids:
        requested = set(case_ids)
        golden = [case for case in golden if case.case_id in requested]
        if {case.case_id for case in golden} != requested:
            raise ValueError("Unknown promptfoo case ID")
    tests = [
        {
            "description": case.case_id,
            "vars": {
                "case_id": case.case_id,
                "question": case.question,
                "category": case.category,
                "reference": case.model_dump_json(),
            },
        }
        for case in golden[:limit]
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8")
    return len(tests)


def summarize(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    grouped = defaultdict(Counter)
    pairs = defaultdict(dict)
    for row in data["results"]["results"]:
        prompt = row.get("prompt", {})
        label = prompt.get("label") or prompt.get("raw")
        if label not in {"baseline-v1", "grounded-v1"}:
            raise ValueError("Unexpected promptfoo prompt label")
        variables = row.get("vars") or row.get("testCase", {}).get("vars", {})
        case_id = variables.get("case_id")
        if not case_id or label in pairs[case_id] or type(row.get("success")) is not bool:
            raise ValueError("Missing or duplicate promptfoo result")
        grouped[label]["total"] += 1
        grouped[label]["passed" if row["success"] else "failed"] += 1
        status = "pass" if row["success"] else "fail"
        components = (row.get("gradingResult") or {}).get("componentResults", [])
        judge_error = any(
            (item.get("reason") or "").startswith("JUDGE_EXECUTION_ERROR") for item in components
        )
        if row.get("failureReason") == 2 or judge_error:
            grouped[label]["errors"] += 1
            status = "error"
        pairs[case_id][label] = {
            "status": status,
            "category": variables.get("category"),
            "failed_checks": [
                item.get("reason") or "Unspecified assertion failure"
                for item in components
                if not item.get("pass")
            ],
        }
    expected = {"baseline-v1", "grounded-v1"}
    if not pairs or any(set(pair) != expected for pair in pairs.values()):
        raise ValueError("Promptfoo output does not contain paired cases")
    return {
        "prompts": dict(grouped),
        "cases": dict(pairs),
        "grounded_minus_baseline_pass_rate": (
            grouped["grounded-v1"]["passed"] - grouped["baseline-v1"]["passed"]
        )
        / len(pairs),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or summarize the promptfoo comparison")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--output", type=Path, default=Path("reports/promptfoo-cases.json"))
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--summarize", type=Path)
    args = parser.parse_args()
    try:
        if args.summarize:
            print(json.dumps(summarize(args.summarize), indent=2))
        elif args.max_cases is not None and args.max_cases < 1:
            raise ValueError("--max-cases must be positive")
        else:
            count = make_cases(args.data, args.output, args.max_cases, args.case_id)
            print(f"Wrote {count} shared cases to {args.output}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Promptfoo input/output error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

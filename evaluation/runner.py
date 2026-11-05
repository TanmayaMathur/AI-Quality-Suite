import argparse
import json
import os
import platform
import sqlite3
import subprocess
from contextlib import ExitStack
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic import TypeAdapter

from app.config import Settings
from app.contracts import ServiceError
from app.main import build_pipeline
from app.pipeline import PROMPTS
from app.providers import ollama_digests, request
from database.repository import Repository
from evaluation.aggregation import summarize
from evaluation.datasets import DATA, Golden, read_dataset
from evaluation.deepeval_runner import DeepEvalJudge
from evaluation.execution import Conversation, run_trials
from evaluation.gates import Policy, check_thresholds, compare_baseline, comparison_key
from evaluation.metrics import compare_judges
from evaluation.models import EvaluationRun, Gate, Judge
from evaluation.promptfoo import summarize as summarize_promptfoo
from evaluation.ragas_runner import RagasJudge
from evaluation.reporting import write_atomic, write_reports

EXIT_CODES = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2, "ERROR": 3}


def git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def select_cases(cases: list[Golden], ids: list[str], limit: int) -> list[Golden]:
    if ids:
        requested = set(ids)
        cases = [case for case in cases if case.case_id in requested]
        if requested != {case.case_id for case in cases}:
            raise ValueError("Unknown golden case ID")
        if len(cases) > limit:
            raise ValueError("Requested case IDs exceed --max-cases")
    return cases[:limit]


def local_models(client: httpx.Client, names: list[str]) -> tuple[str, dict[str, str]]:
    runtime = request(client, "model", "/api/version")["version"]
    return runtime, ollama_digests(client, names)


def judges_for(names: list[str], client: httpx.Client, settings: Settings, args) -> list[Judge]:
    judges = []
    if "deepeval" in names:
        judges.append(DeepEvalJudge(client, args.judge_model, args.judge_seed))
    if "ragas" in names:
        judges.append(
            RagasJudge(
                settings.ollama_url,
                args.judge_model,
                settings.embedding_model,
                settings.timeout_s,
                args.judge_seed,
            )
        )
    return judges


def load_baseline(path: Path) -> EvaluationRun:
    data = json.loads(path.read_text(encoding="utf-8"))
    run = EvaluationRun.model_validate(data["accepted_run"])
    if data.get("export_version") != 1 or run.decision != "PASS" or not run.baseline_eligible:
        raise ValueError("Baseline file must be a reviewed approval export of a full passing run")
    return run


def evaluate(args, repo: Repository) -> EvaluationRun:
    golden, safety, manifest = read_dataset(args.data)
    selected = select_cases(golden, args.case_id, args.max_cases)
    safety_cases = [] if args.skip_safety else safety[: args.max_safety_cases]
    all_conversations = TypeAdapter(list[Conversation]).validate_json(
        (args.data / "conversations.json").read_bytes()
    )
    if (
        len({c.case_id for c in all_conversations}) != len(all_conversations)
        or not all_conversations
    ):
        raise ValueError("Conversation case IDs must be unique and the suite must be nonempty")
    conversations = [] if args.skip_conversations else all_conversations
    policy = Policy.model_validate_json(args.policy.read_bytes())
    settings = Settings()
    if settings.provider == "hosted" and not (
        args.permit_hosted and args.max_cases <= 12 and args.skip_safety and args.skip_conversations
    ):
        raise ValueError("Hosted evaluation requires explicit opt-in and at most 12 golden cases")
    names = {"both": ["deepeval", "ragas"], "deterministic": []}.get(
        args.framework,
        [args.framework],
    )
    controlled = {
        "suite_version": 1,
        "dataset_fingerprint": manifest["fingerprint"],
        "golden_cases": [c.case_id for c in selected],
        "safety_cases": [c.case_id for c in safety_cases],
        "conversations": [case.model_dump(mode="json") for case in conversations],
        "repetitions": args.repetitions,
        "temperature": settings.temperature,
        "seed": settings.seed,
        "generation_limit": settings.max_tokens,
        "judge_model": args.judge_model if names else None,
        "judge_seed": args.judge_seed if names else None,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "top_k": settings.top_k,
        "score_floor": settings.score_floor,
        "chunk_words": settings.chunk_words,
        "overlap_words": settings.overlap_words,
        "history_turns": settings.history_turns,
        "input_guard": settings.input_guard,
        "refusal": settings.refusal,
        "abstention": settings.abstention,
        "cache_metrics": args.cache_metrics,
        "policy": policy.model_dump(),
    }
    config = {
        **controlled,
        "provider": settings.provider,
        "model": settings.model,
        "prompt_version": args.prompt_version,
        "prompt_sha256": sha256(PROMPTS[args.prompt_version].encode()).hexdigest(),
        "document_version": manifest["document_version"],
        "pricing_usd_per_million_input": settings.usd_per_million_input,
        "pricing_usd_per_million_output": settings.usd_per_million_output,
    }
    trials, errors = [], []
    try:
        with ExitStack() as stack:
            local = stack.enter_context(
                httpx.Client(
                    base_url=settings.ollama_url,
                    timeout=settings.timeout_s,
                    trust_env=False,
                )
            )
            judges = judges_for(names, local, settings, args)
            controlled["judge_versions"] = {judge.framework: judge.version for judge in judges}
            local_names = [settings.embedding_model]
            if settings.provider == "ollama":
                local_names.append(settings.model)
            if names:
                local_names.append(args.judge_model)
            runtime, digests = local_models(local, local_names)
            config.update({"ollama_version": runtime, "model_digests": digests})
            controlled.update(
                {
                    "embedding_digest": digests[settings.embedding_model],
                    "judge_digest": digests.get(args.judge_model) if names else None,
                    "ollama_version": runtime,
                    "latency_platform": f"{platform.system()}-{platform.machine()}",
                }
            )
            evaluation_settings = settings.model_copy(
                update={
                    "collection": settings.collection[:75] + "_eval",
                }
            )
            pipeline = build_pipeline(evaluation_settings, stack)
            config["indexed_collection"], config["indexed_passages"] = pipeline.retriever.ingest(
                args.data / "docs"
            )
            pipeline.ready()
            trials = run_trials(
                pipeline,
                selected,
                safety_cases,
                conversations,
                args.data,
                args.repetitions,
                args.prompt_version,
                judges,
                args.cache_metrics,
            )
    except ServiceError as exc:
        errors.append(exc.code)
    except (ImportError, KeyError, OSError, TypeError, ValueError, RuntimeError) as exc:
        errors.append(type(exc).__name__)
    config.update(controlled)
    summary = summarize(trials, policy.hallucination_cutoff)
    gates = check_thresholds(
        summary,
        policy,
        trials,
        names,
        args.repetitions,
        bool(safety_cases),
        bool(conversations),
    )
    run = EvaluationRun(
        run_id=uuid4().hex,
        timestamp=datetime.now(UTC).isoformat(),
        git_sha=git_sha(),
        dataset_version=manifest["dataset_version"],
        dataset_fingerprint=manifest["fingerprint"],
        comparison_key=comparison_key(controlled),
        config=config,
        trials=trials,
        summary=summary,
        gates=gates,
        errors=errors,
        comparisons=compare_judges(trials),
        baseline_eligible=(
            len(selected) == len(golden)
            and len(safety_cases) == len(safety)
            and bool(conversations)
            and len(names) == 2
            and args.repetitions >= 3
            and not args.cache_metrics
            and settings.provider == "ollama"
        ),
    )
    if args.promptfoo_json:
        try:
            run.promptfoo = summarize_promptfoo(args.promptfoo_json)
            if any(row.get("errors", 0) for row in run.promptfoo["prompts"].values()):
                run.errors.append("promptfoo_execution_error")
        except (OSError, ValueError, KeyError, TypeError):
            run.errors.append("promptfoo_report_invalid")
    try:
        baseline = (
            load_baseline(args.baseline_file)
            if args.baseline_file
            else repo.baseline(run.comparison_key)
        )
        run.baseline_run_id = baseline.run_id if baseline else None
        checks, run.regressions = compare_baseline(run, baseline, policy, args.require_baseline)
        run.gates.extend(checks)
    except (OSError, ValueError, KeyError, sqlite3.Error):
        run.gates.append(Gate(name="baseline", status="ERROR", reason="Baseline could not be read"))
    try:
        repo.save(run)
    except (OSError, sqlite3.Error, ValueError):
        run.errors.append("database_write_failed")
    return run


def main() -> int:
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    parser = argparse.ArgumentParser(
        description="Run local RAG quality evaluation and release gates"
    )
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--policy", type=Path, default=Path("evaluation/policy.json"))
    parser.add_argument("--db", type=Path, default=Path("state/evaluations.sqlite"))
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument(
        "--framework", choices=["both", "deepeval", "ragas", "deterministic"], default="both"
    )
    parser.add_argument("--judge-model", default=os.getenv("AQS_JUDGE_MODEL", "qwen2.5:3b"))
    parser.add_argument("--judge-seed", type=int, default=42)
    parser.add_argument("--prompt-version", choices=tuple(PROMPTS), default="grounded-v1")
    parser.add_argument("--repetitions", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--max-cases", type=int, default=12)
    parser.add_argument("--max-safety-cases", type=int, default=35)
    parser.add_argument("--skip-safety", action="store_true")
    parser.add_argument("--skip-conversations", action="store_true")
    parser.add_argument("--cache-metrics", action="store_true")
    parser.add_argument("--permit-hosted", action="store_true")
    parser.add_argument("--require-baseline", action="store_true")
    parser.add_argument("--baseline-file", type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--approve", metavar="RUN_ID")
    action.add_argument("--report-run", metavar="RUN_ID")
    parser.add_argument("--export-baseline", type=Path)
    parser.add_argument("--promptfoo-json", type=Path)
    args = parser.parse_args()
    if args.max_cases < 1 or args.max_safety_cases < 1:
        parser.error("case limits must be positive")
    if args.export_baseline and not args.approve:
        parser.error("--export-baseline requires --approve")
    repo = Repository(args.db)
    try:
        if args.approve:
            approved = repo.approve(args.approve)
            if args.export_baseline:
                write_atomic(
                    args.export_baseline,
                    json.dumps(
                        {
                            "export_version": 1,
                            "accepted_run": approved.model_dump(mode="json"),
                        },
                        indent=2,
                    ),
                )
            print(f"Approved baseline {approved.run_id}")
            return 0
        if args.report_run:
            run = repo.get(args.report_run)
            write_reports(run, args.reports)
            print(f"Rendered {run.run_id} to {args.reports}")
            return 0
        run = evaluate(args, repo)
        write_reports(run, args.reports)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        parser.exit(3, f"Evaluation could not complete ({type(exc).__name__}): {exc}\n")
    print(
        f"{run.decision} {run.run_id} · {len(run.trials)} trials · {args.reports / 'latest.html'}"
    )
    return EXIT_CODES[run.decision]


if __name__ == "__main__":
    raise SystemExit(main())

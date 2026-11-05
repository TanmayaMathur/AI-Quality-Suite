import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from evaluation.models import EvaluationRun

SCHEMA = Path(__file__).with_name("schema.sql")


class Repository:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys = ON")
            current = db.execute("PRAGMA user_version").fetchone()[0]
            if current == 0:
                db.executescript(
                    f"BEGIN IMMEDIATE;\n{SCHEMA.read_text(encoding='utf-8')}"
                    "\nPRAGMA user_version = 1; COMMIT;"
                )
            elif current != 1:
                raise ValueError(f"Unsupported database schema version {current}")
            with db:
                yield db
        finally:
            db.close()

    def save(self, run: EvaluationRun):
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO evaluation_runs (
                    run_id, timestamp, git_sha, dataset_version, dataset_fingerprint,
                    comparison_key, prompt_version, provider, model, decision, run_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    run.run_id,
                    run.timestamp,
                    run.git_sha,
                    run.dataset_version,
                    run.dataset_fingerprint,
                    run.comparison_key,
                    run.config["prompt_version"],
                    run.config["provider"],
                    run.config["model"],
                    run.decision,
                    run.model_dump_json(),
                ),
            )
            for trial in run.trials:
                key = run.run_id, trial.case_id, trial.repetition
                answer = trial.output
                db.execute(
                    "INSERT INTO evaluation_cases VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        *key,
                        trial.category,
                        trial.status,
                        answer.answer if answer else None,
                        trial.reason,
                    ),
                )
                db.executemany(
                    "INSERT INTO metric_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            *key,
                            m.framework,
                            m.metric,
                            m.version,
                            m.status,
                            m.score,
                            m.reason,
                            m.latency_ms,
                            m.cached,
                        )
                        for m in trial.metrics
                    ],
                )
                if trial.safety is not None:
                    db.execute(
                        "INSERT INTO safety_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            *key,
                            *(
                                trial.safety[flag]
                                for flag in (
                                    "pass",
                                    "marker_seen",
                                    "leaked",
                                    "false_refusal",
                                    "fixture_exposed",
                                )
                            ),
                        ),
                    )
                if answer is not None:
                    db.execute(
                        "INSERT INTO performance_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            *key,
                            answer.latency_ms,
                            answer.retrieval_ms,
                            answer.generation_ms,
                            answer.input_tokens,
                            answer.output_tokens,
                            answer.estimated_usd,
                        ),
                    )
            db.executemany(
                "INSERT INTO regression_results VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run.run_id,
                        row["case_id"],
                        row["metric"],
                        run.baseline_run_id,
                        row["baseline"],
                        row["current"],
                        row["deterioration"],
                    )
                    for row in run.regressions
                ],
            )

    def baseline(self, key: str) -> EvaluationRun | None:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT run_json FROM evaluation_runs
                WHERE comparison_key = ? AND approved_at IS NOT NULL AND decision = 'PASS'
                ORDER BY approved_at DESC, run_id DESC LIMIT 1
            """,
                (key,),
            ).fetchone()
        return EvaluationRun.model_validate_json(row[0]) if row else None

    def get(self, run_id: str) -> EvaluationRun:
        with self.connect() as db:
            row = db.execute(
                "SELECT run_json FROM evaluation_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if not row:
            raise ValueError("Run was not found")
        return EvaluationRun.model_validate_json(row[0])

    def approve(self, run_id: str) -> EvaluationRun:
        run = self.get(run_id)
        if run.decision != "PASS" or not run.baseline_eligible:
            raise ValueError("Baseline requires a passing full run without cached judge results")
        with self.connect() as db:
            db.execute(
                "UPDATE evaluation_runs SET approved_at = ? WHERE run_id = ?",
                (datetime.now(UTC).isoformat(), run_id),
            )
        return run

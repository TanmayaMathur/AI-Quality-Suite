import json
import sqlite3

import pytest

from app.contracts import Question
from database.repository import Repository
from evaluation.aggregation import summarize
from evaluation.models import EvaluationRun, Gate, MetricResult, Trial
from evaluation.reporting import write_reports


@pytest.fixture
def recorded_run(pipeline):
    output, _ = pipeline.answer(
        Question(
            question="Which cable does the bridge use?",
        )
    )
    trial = Trial(
        case_id="S001",
        repetition=1,
        category="direct-injection",
        status="pass",
        output=output,
        metrics=[
            MetricResult(
                framework="deepeval",
                version="1",
                metric="faithfulness",
                status="scored",
                score=0.91,
                reason="Cited",
            )
        ],
        safety={
            "pass": True,
            "marker_seen": False,
            "leaked": False,
            "false_refusal": False,
            "fixture_exposed": False,
        },
    )
    return EvaluationRun(
        run_id="example",
        timestamp="2026-01-01T00:00:00+00:00",
        git_sha=None,
        dataset_version="golden-v1",
        dataset_fingerprint="test",
        comparison_key="a",
        config={"prompt_version": "grounded-v1", "provider": "ollama", "model": "fixture"},
        trials=[trial],
        summary=summarize([trial], 0.5),
        baseline_eligible=True,
        gates=[Gate(name="sample", status="PASS", reason="Checks passed <script>")],
        baseline_run_id="prior",
        regressions=[
            {
                "case_id": "S001",
                "metric": "deepeval.faithfulness",
                "baseline": 0.99,
                "current": 0.91,
                "deterioration": 0.08,
            }
        ],
    )


def test_sqlite_migrates_persists_and_returns_only_compatible_approvals(tmp_path, recorded_run):
    repo = Repository(tmp_path / "runs.sqlite")
    repo.save(recorded_run)
    assert repo.baseline("a") is None
    assert repo.approve("example").run_id == "example"
    assert repo.baseline("a").trials[0].metrics[0].score == 0.91
    assert repo.baseline("different") is None
    with repo.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute("SELECT input_tokens FROM performance_results").fetchone()[0] == 120
        assert db.execute("SELECT passed FROM safety_results").fetchone()[0] == 1
        assert db.execute("SELECT baseline_run_id FROM regression_results").fetchone()[0] == "prior"
    with pytest.raises(ValueError, match="not found"):
        repo.approve("missing")


def test_database_failure_rolls_back_entire_run(tmp_path, recorded_run):
    repo = Repository(tmp_path / "runs.sqlite")
    recorded_run.trials.append(recorded_run.trials[0])
    with pytest.raises(sqlite3.IntegrityError):
        repo.save(recorded_run)
    with repo.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM evaluation_runs").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM evaluation_cases").fetchone()[0] == 0


def test_reports_escape_data_and_keep_timestamped_copies(tmp_path, recorded_run):
    write_reports(recorded_run, tmp_path)
    assert sorted(path.suffix for path in tmp_path.iterdir()) == [
        ".html",
        ".html",
        ".json",
        ".json",
        ".md",
        ".md",
    ]
    html = (tmp_path / "latest.html").read_text(encoding="utf-8")
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert "Not evaluated" in html
    raw = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert raw["decision"] == "PASS"
    assert raw["trials"][0]["output"]["answer"].endswith("[1].")
    assert "deepeval.faithfulness" in (tmp_path / "latest.md").read_text(encoding="utf-8")

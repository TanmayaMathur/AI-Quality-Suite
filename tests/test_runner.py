import json
import sys
from pathlib import Path

import pytest

from app.contracts import ServiceError
from database.repository import Repository
from evaluation import runner
from evaluation.datasets import read_dataset


@pytest.fixture
def cli(tmp_path, monkeypatch):
    db, reports = tmp_path / "state.sqlite", tmp_path / "reports"
    args = [
        "evaluation.runner",
        "--framework",
        "deterministic",
        "--case-id",
        "G001",
        "--repetitions",
        "1",
        "--max-safety-cases",
        "2",
        "--db",
        str(db),
        "--reports",
        str(reports),
    ]
    monkeypatch.setattr(sys, "argv", args)
    return db, reports


def test_runner_missing_services_records_real_error_in_report(cli, monkeypatch):
    db, reports = cli

    def unavailable(client, names):
        raise ServiceError("model_unavailable", 503)

    monkeypatch.setattr(runner, "local_models", unavailable)
    assert runner.main() == 3
    report = json.loads((reports / "latest.json").read_text(encoding="utf-8"))
    assert report["errors"] == ["model_unavailable"]
    assert report["trials"] == []
    assert report["decision"] == "ERROR"
    with Repository(db).connect() as connection:
        assert connection.execute("SELECT decision FROM evaluation_runs").fetchone()[0] == "ERROR"


def test_cli_runs_all_selected_layers_and_surfaces_database_failure(cli, pipeline, monkeypatch):
    _, reports = cli
    pipeline.retriever.ingest = lambda path: ("fixture", 2)
    monkeypatch.setattr(runner, "build_pipeline", lambda settings, stack: pipeline)
    monkeypatch.setattr(
        runner,
        "local_models",
        lambda client, names: (
            "test",
            dict.fromkeys(names, "digest"),
        ),
    )

    def write_failed(self, run):
        raise OSError("private location")

    monkeypatch.setattr(Repository, "save", write_failed)
    assert runner.main() == 3
    report = json.loads((reports / "latest.json").read_text(encoding="utf-8"))
    assert "database_write_failed" in report["errors"]
    assert len(report["trials"]) == 10
    assert not report["baseline_eligible"]
    assert "private location" not in json.dumps(report)


def test_selection_and_baseline_export_validation(tmp_path):
    golden = read_dataset()[0]
    assert [case.case_id for case in runner.select_cases(golden, ["G005"], 1)] == ["G005"]
    with pytest.raises(ValueError, match="Unknown"):
        runner.select_cases(golden, ["G999"], 1)
    with pytest.raises(ValueError, match="exceed"):
        runner.select_cases(golden, ["G005", "G006"], 1)
    with pytest.raises(KeyError):
        path = Path(tmp_path / "baseline.json")
        path.write_text("{}")
        runner.load_baseline(path)

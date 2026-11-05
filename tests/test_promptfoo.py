import json
from pathlib import Path

import pytest

from evaluation.promptfoo import make_cases, summarize


def test_promptfoo_uses_the_shared_golden_records(tmp_path):
    path = tmp_path / "cases.json"
    assert make_cases(Path("data"), path, None, ["G005"]) == 1
    row = json.loads(path.read_text())[0]
    assert row["description"] == "G005"
    assert json.loads(row["vars"]["reference"])["evidence"][0]["document_id"] == "drift-relay"
    with pytest.raises(ValueError, match="Unknown"):
        make_cases(Path("data"), path, None, ["G000"])


def test_promptfoo_comparison_rejects_missing_and_pairs_complete_rows(tmp_path):
    path = tmp_path / "result.json"
    rows = [
        {"prompt": {"label": label}, "vars": {"case_id": "G001"}, "success": success}
        for label, success in [("grounded-v1", True), ("baseline-v1", False)]
    ]
    rows[1].update(failureReason=1, error="Ordinary assertion failure")
    path.write_text(json.dumps({"results": {"results": rows[:1]}}))
    with pytest.raises(ValueError, match="paired"):
        summarize(path)
    path.write_text(json.dumps({"results": {"results": rows}}))
    result = summarize(path)
    assert result["prompts"]["baseline-v1"]["failed"] == 1
    assert result["prompts"]["baseline-v1"].get("errors", 0) == 0
    assert result["grounded_minus_baseline_pass_rate"] == 1

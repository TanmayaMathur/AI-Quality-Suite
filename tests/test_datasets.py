import json
import shutil
from pathlib import Path

import pytest

from evaluation.datasets import Golden, load_records, read_dataset


def test_frozen_dataset_and_manifest_agree():
    golden, safety, report = read_dataset()
    assert len(golden) == report["golden_count"] == 66
    assert len(safety) == report["adversarial_count"] == 35
    assert len(report["fingerprint"]) == 64
    assert report["validation"] == "PASS"


@pytest.mark.parametrize("payload", ["{", '{"case_id":"G001"}'])
def test_dataset_rejects_malformed_record(tmp_path, payload):
    path = tmp_path / "bad.jsonl"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad.jsonl:1"):
        load_records(path, Golden)


def test_dataset_rejects_duplicate_questions(tmp_path):
    original = Path("data/golden_v1.jsonl").read_text(encoding="utf-8").splitlines()[0]
    copy = json.loads(original)
    copy["case_id"] = "G999"
    path = tmp_path / "duplicate.jsonl"
    path.write_text(f"{original}\n{json.dumps(copy)}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate question"):
        load_records(path, Golden)


def test_dataset_rejects_a_reference_span_removed_from_the_handbook(tmp_path):
    root = tmp_path / "data"
    shutil.copytree("data", root)
    path = root / "docs" / "harbor-bridge.md"
    original = path.read_text(encoding="utf-8")
    path.write_text(original.replace("wired Ethernet", "wired fiber"), encoding="utf-8")
    with pytest.raises(ValueError, match="G001: evidence quote absent"):
        read_dataset(root)

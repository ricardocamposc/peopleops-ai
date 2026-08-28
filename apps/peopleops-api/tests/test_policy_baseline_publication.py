import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "ops"))
from publish_policy_baseline import publish


def _run(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "manifest.json").write_text(
        json.dumps({"execution": "real_peopleops_api", "dataset_case_count": 1})
    )
    (run / "dataset.jsonl").write_text('{"case_id":"case-1"}\n')
    (run / "metrics.json").write_text('{}\n')
    (run / "report.md").write_text('# Policy RAG evaluation\n')
    (run / "predictions.jsonl").write_text('{"case_id":"case-1","synthetic_corpus":true}\n')
    return run


def test_published_baseline_structure(tmp_path):
    destination = publish(_run(tmp_path), tmp_path / "baselines", "regression-v2")
    assert sorted(item.name for item in destination.iterdir()) == [
        "dataset.jsonl",
        "manifest.json",
        "metrics.json",
        "predictions.jsonl",
        "report.md",
    ]


def test_publish_does_not_overwrite(tmp_path):
    run = _run(tmp_path)
    baselines = tmp_path / "baselines"
    publish(run, baselines, "regression-v2")
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        publish(run, baselines, "regression-v2")

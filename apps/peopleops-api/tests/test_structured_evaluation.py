import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2].parents[0]
ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(ROOT / "ops"))

from structured_hr_baseline import _load_cases  # noqa: E402
from publish_structured_baseline import publish  # noqa: E402


def test_structured_datasets_are_ground_truth_only() -> None:
    for filename in ("structured_hr_analysis_v2.jsonl", "structured_hr_holdout_v1.jsonl"):
        cases = _load_cases(ROOT / "evaluation" / "cases" / filename)
        assert cases
        assert all("observed" not in case for case in cases)


def test_publisher_refuses_incomplete_or_overwrite(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "manifest.json").write_text(json.dumps({"execution": "real_peopleops_mcp_hris", "dataset_case_count": 1}))
    with pytest.raises(SystemExit, match="run is incomplete"):
        publish(run, tmp_path / "published")

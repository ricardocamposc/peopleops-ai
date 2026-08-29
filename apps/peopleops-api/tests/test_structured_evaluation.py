import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2].parents[0]
ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(ROOT / "ops"))

from structured_hr_baseline import _evaluate, _load_cases  # noqa: E402
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


def test_evaluator_separates_metric_function_field_and_alias() -> None:
    response = {
        "status": "completed",
        "semantic_request": {"required_capabilities": ["payroll"], "entities": ["payroll"]},
        "query_plan": {"queries": [{"query": {
            "entities": ["payroll", "department"],
            "metrics": [{"function": "sum", "field": "payroll.net_amount", "alias": "Total"}],
            "dimensions": ["department.name"],
        }}]},
        "evidence": [{"type": "structured_data", "result_verification": {"status": "VALID"}}],
    }
    record = _evaluate({
        "id": "metric-contract", "question": "total payroll by department", "expected_answerable": True,
        "expected_capabilities": ["payroll"], "expected_entities": ["payroll", "department"],
        "expected_metric_functions": ["sum"], "expected_metric_fields": ["payroll.net_amount"],
        "expected_dimensions": ["department.name"],
    }, response)
    assert record["checks"]["conceptual_query_validity"] is True
    assert record["checks"]["metric_function_recall"] is True
    assert record["checks"]["metric_field_recall"] is True
    assert record["checks"]["dimension_accuracy"] is True


def test_evaluator_counts_only_negative_cases_for_abstention() -> None:
    response = {"status": "insufficient_data", "semantic_request": {}, "evidence": []}
    record = _evaluate({"id": "negative", "question": "unsupported", "expected_answerable": False}, response)
    assert record["checks"]["answerability"] is True
    assert record["checks"]["workflow_execution_success"] is True
    assert record["checks"]["provider_execution_success"] is None

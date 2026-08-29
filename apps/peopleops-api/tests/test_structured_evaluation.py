import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2].parents[0]
ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(ROOT / "ops"))

from structured_hr_baseline import _evaluate, _load_cases, _time_scope_matches  # noqa: E402
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
        "evaluation_trace": {
            "provider_validations": [{"accepted": True}],
            "provider_executions": [{"success": True}],
        },
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


def test_time_scope_is_compared_semantically() -> None:
    assert _time_scope_matches(
        {"kind": "relative_window", "days": 45},
        [{"time_scope": {"type": "date_range", "start": "2025-01-01", "end": "2025-02-14"}}],
    ) is True
    assert _time_scope_matches(
        {"kind": "explicit_period", "value": "2025-02"},
        [{"time_scope": {"type": "payroll_period", "value": "2025-02"}}],
    ) is True


def test_period_comparison_requires_independent_provider_executions() -> None:
    queries = [
        {"time_scope": {"type": "payroll_period", "value": "2025-01"}},
        {"time_scope": {"type": "payroll_period", "value": "2025-02"}},
    ]
    assert _time_scope_matches({"kind": "period_comparison", "expected_query_count": 2}, queries, {"provider_executions": [{"success": True}, {"success": True}]}) is True
    assert _time_scope_matches({"kind": "period_comparison", "expected_query_count": 2}, queries, {"provider_executions": [{"success": True}]}) is False


def test_provider_validation_and_execution_are_independent() -> None:
    record = _evaluate(
        {"id": "provider-stages", "question": "query", "expected_answerable": True, "expected_capabilities": ["workforce"]},
        {
            "status": "failed",
            "semantic_request": {"required_capabilities": ["workforce"]},
            "query_plan": {"queries": [{"query": {"entities": ["employee"]}}]},
            "evaluation_trace": {
                "provider_validations": [{"accepted": True}],
                "provider_executions": [{"success": False, "error_code": "QUERY_EXECUTION_ERROR"}],
            },
        },
    )
    assert record["checks"]["conceptual_query_validity"] is True
    assert record["checks"]["provider_execution_success"] is False
    assert record["diagnostics"]["failed_layer"] == "PROVIDER_EXECUTION_DEFECT"


def test_metrics_are_structured_with_denominators() -> None:
    from structured_hr_baseline import _metric

    records = [{"checks": {"answerability": True}}, {"checks": {"answerability": False}}]
    metric = _metric(records, "answerability")
    assert metric == {"value": 0.5, "successes": 1, "eligible_cases": 2}

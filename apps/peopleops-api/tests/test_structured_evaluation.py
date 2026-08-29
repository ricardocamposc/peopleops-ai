import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2].parents[0]
ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(ROOT / "ops"))

from structured_hr_baseline import (  # noqa: E402
    _evaluate,
    _load_cases,
    _time_scope_matches,
)
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


def _response_with_validation(*, errors: list[str], catalog_valid: bool = False) -> dict:
    return {
        "status": "insufficient_data",
        "semantic_request": {"required_capabilities": ["workforce"], "entities": ["employee"]},
        "query_plan": {"queries": [{"query": {"entities": ["employee"], "select": [{"field": "employee.fake_field"}]}}]},
        "evaluation_trace": {
            "provider_validations": [{"accepted": False, "errors": errors, "catalog_valid": catalog_valid}],
            "provider_executions": [],
        },
    }


def test_invalid_planner_field_is_not_attributed_to_mcp() -> None:
    record = _evaluate(
        {"id": "invalid-field", "question": "q", "expected_answerable": True, "expected_capabilities": ["workforce"]},
        _response_with_validation(errors=["unknown field: employee.fake_field"]),
    )
    assert record["diagnostics"]["failed_layer"] == "PEOPLEOPS_PLAN_DEFECT"


def test_unknown_entity_and_relationship_are_planner_defects() -> None:
    for error in ("unknown entity: turnover", "unknown relationship: employee_turnover"):
        record = _evaluate(
            {"id": "invalid-query", "question": "q", "expected_answerable": True, "expected_capabilities": ["workforce"]},
            _response_with_validation(errors=[error]),
        )
        assert record["diagnostics"]["failed_layer"] == "PEOPLEOPS_PLAN_DEFECT"


def test_catalog_valid_query_rejected_by_provider_is_mcp_defect() -> None:
    record = _evaluate(
        {"id": "provider-bug", "question": "q", "expected_answerable": True, "expected_capabilities": ["workforce"]},
        _response_with_validation(errors=["provider rejected valid conceptual query"], catalog_valid=True),
    )
    assert record["diagnostics"]["failed_layer"] == "MCP_VALIDATION_DEFECT"


def test_zero_rows_uses_authoritative_provider_execution_trace() -> None:
    record = _evaluate(
        {"id": "zero", "question": "q", "expected_answerable": True, "expected_zero_rows": True},
        {
            "status": "insufficient_data",
            "semantic_request": {},
            "evaluation_trace": {
                "provider_validations": [{"accepted": True}],
                "provider_executions": [{"success": True, "row_count": 0, "result_verification_status": "ZERO_ROWS"}],
            },
        },
    )
    assert record["checks"]["zero_result"] is True


def test_zero_rows_is_false_when_rows_are_returned() -> None:
    record = _evaluate(
        {"id": "not-zero", "question": "q", "expected_answerable": True, "expected_zero_rows": True},
        {
            "status": "completed",
            "semantic_request": {},
            "evaluation_trace": {
                "provider_validations": [{"accepted": True}],
                "provider_executions": [{"success": True, "row_count": 2, "result_verification_status": "VALID"}],
            },
        },
    )
    assert record["checks"]["zero_result"] is False


def test_authorization_denial_is_evaluated_when_trace_is_consistent() -> None:
    record = _evaluate(
        {"id": "denied", "question": "q", "expected_answerable": False, "expected_capabilities": ["payroll"], "expected_authorization": "denied"},
        {
            "status": "pending_human_review",
            "semantic_request": {"required_capabilities": ["payroll"]},
            "evaluation_trace": {"authorization": {"required": True, "scope_present": False, "decision": "denied"}},
        },
    )
    assert record["checks"]["authorization"] is True


def test_contradictory_historical_authorization_is_not_evaluable() -> None:
    record = _evaluate(
        {"id": "contradictory-auth", "question": "q", "expected_capabilities": ["payroll"], "expected_authorization": "denied"},
        {
            "status": "pending_human_review",
            "semantic_request": {"required_capabilities": ["payroll"]},
            "evaluation_trace": {"authorization": {"required": False, "scope_present": False, "decision": "granted"}},
        },
    )
    assert record["checks"]["authorization"] is None

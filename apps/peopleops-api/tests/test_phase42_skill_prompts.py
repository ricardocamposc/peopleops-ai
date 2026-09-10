from __future__ import annotations

from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda

import direct_sqlalchemy_phase42 as phase42
import direct_sqlalchemy_phase42_skills as skills


PLACEHOLDERS = (
    "{{data_model}}",
    "{{reference_date}}",
    "{{reference_year}}",
    "{{reference_month}}",
    "{{reference_day}}",
    "{{current_period}}",
    "{{timezone}}",
)


class FakeChatModel:
    def __init__(self, responses: list[phase42.QueryProgrammerResponse]) -> None:
        self.responses = list(responses)

    def with_structured_output(self, _output_model: Any) -> RunnableLambda:
        return RunnableLambda(lambda _input: self.responses.pop(0))


def _query_response(sqlalchemy: str) -> phase42.QueryProgrammerResponse:
    return phase42.QueryProgrammerResponse(
        status="QUERY",
        sqlalchemy=sqlalchemy,
        interpretation="Retrieve approved overtime minutes.",
        assumptions=[],
        missing_information=[],
        models_used=["Overtime"],
        relationships_used=[],
        retrieved_measures=["approved overtime minutes"],
        retrieved_dimensions=[],
        applied_filters=[],
        applied_temporal_constraints=[],
        grouping_implemented=[],
        requirement_coverage=[],
    )


def _runtime(responses: list[phase42.QueryProgrammerResponse]) -> skills.SkillPromptRuntime:
    runtime = object.__new__(skills.SkillPromptRuntime)
    runtime.model_config = {"sqlalchemy_query_developer": "fake-model"}
    runtime.models = {"sqlalchemy_query_developer": FakeChatModel(responses)}
    runtime.query_skill_templates = skills._skill_templates()
    return runtime


def _payload(*, repair_type: str | None = None) -> dict[str, Any]:
    previous_query = (
        _query_response("select(Overtime.approved_minutes)").model_dump(mode="json")
        if repair_type
        else None
    )
    deterministic_validation_result = None
    senior_review = None
    if repair_type == "TECHNICAL":
        deterministic_validation_result = {
            "technically_valid": False,
            "diagnostics": [
                {
                    "stage": "PYTHON_SYNTAX",
                    "code": "PYTHON_SYNTAX",
                    "exception_type": "SyntaxError",
                    "message": "'(' was never closed",
                    "line": 1,
                    "offset": 7,
                    "text": "select(",
                    "source": "select(",
                }
            ],
        }
    if repair_type == "SEMANTIC":
        senior_review = {
            "status": "REVISE",
            "summary": "Preserve the required employee dimension.",
            "material_issues": [],
        }
    return {
        "query_task": {
            "original_user_request": "List overtime minutes",
            "clarified_request": "List overtime minutes",
            "business_intent": "retrieve overtime",
            "domain": ["overtime"],
            "required_information": ["approved overtime minutes"],
            "measures": ["approved overtime minutes"],
            "dimensions": [],
            "filters": [],
            "temporal_requirements": [],
            "grouping_requirements": [],
            "ordering_requirements": [],
            "comparison_requirements": [],
            "data_retrieval_request": "Retrieve approved overtime minutes.",
            "downstream_analysis": [],
            "required_sources": ["HRIS_STRUCTURED_DATA"],
            "assumptions": [],
            "ambiguities": [],
            "unsupported_requirements": [],
            "sensitivity": [],
        },
        "data_model": phase42._catalog(),
        "reference_context": phase42.REFERENCE_CONTEXT,
        "repair_type": repair_type,
        "repair_attempt": 1 if repair_type else 0,
        "previous_query": previous_query,
        "deterministic_validation_result": deterministic_validation_result,
        "senior_review": senior_review,
    }


def test_skill_router_selects_generate_for_initial_call() -> None:
    assert skills.select_query_programmer_skill(None) == "GENERATE"


def test_skill_router_selects_technical_repair_for_both_technical_paths() -> None:
    assert skills.select_query_programmer_skill("TECHNICAL") == "TECHNICAL_REPAIR"
    assert (
        skills.select_query_programmer_skill("INTERNAL_SELF_REPAIR")
        == "TECHNICAL_REPAIR"
    )


def test_skill_router_selects_semantic_repair() -> None:
    assert skills.select_query_programmer_skill("SEMANTIC") == "SEMANTIC_REPAIR"


def test_skill_router_rejects_unknown_repair_type() -> None:
    with pytest.raises(ValueError, match="Unsupported Query Programmer repair_type"):
        skills.select_query_programmer_skill("UNKNOWN")


def test_each_skill_prompt_has_context_exactly_once() -> None:
    prompts = (
        skills.QUERY_GENERATE_PROMPT,
        skills.QUERY_TECHNICAL_REPAIR_PROMPT,
        skills.QUERY_SEMANTIC_REPAIR_PROMPT,
    )
    for prompt in prompts:
        for placeholder in PLACEHOLDERS:
            assert prompt.count(placeholder) == 1


def test_skill_prompts_have_distinct_responsibilities() -> None:
    assert "query-generation skill" in skills.QUERY_GENERATE_PROMPT
    assert "technical debugger and repairer" in skills.QUERY_TECHNICAL_REPAIR_PROMPT
    assert "semantic implementation repairer" in skills.QUERY_SEMANTIC_REPAIR_PROMPT


def test_technical_repair_prompt_requires_diagnostic_reasoning() -> None:
    prompt = skills.QUERY_TECHNICAL_REPAIR_PROMPT
    assert "line, offset, text, and source" in prompt
    assert "Do not merely adjust parentheses" in prompt
    assert "PYTHON_SYNTAX" in prompt
    assert "SQLALCHEMY_BUILD" in prompt
    assert "SQLALCHEMY_COMPILE" in prompt


def test_semantic_repair_keeps_functional_requirement_authoritative() -> None:
    prompt = skills.QUERY_SEMANTIC_REPAIR_PROMPT
    assert "Functional Requirement is the source of truth" in prompt
    assert "do not obey feedback that conflicts" in prompt
    assert "comparison preservation" in prompt


def test_internal_self_repair_switches_from_generate_to_technical_repair() -> None:
    runtime = _runtime(
        [
            _query_response("select("),
            _query_response("select(Overtime.approved_minutes)"),
        ]
    )

    result, metadata = runtime.invoke_query_programmer(
        input_payload=_payload(),
        output_model=phase42.QueryProgrammerResponse,
    )

    assert result.sqlalchemy == "select(Overtime.approved_minutes)"
    invocations = metadata["query_programmer_invocations"]
    assert metadata["query_programmer_invocation_count"] == 2
    assert [item["skill"] for item in invocations] == [
        "GENERATE",
        "TECHNICAL_REPAIR",
    ]
    assert invocations[0]["repair_type"] is None
    assert invocations[1]["repair_type"] == "INTERNAL_SELF_REPAIR"
    assert "previous_query" in invocations[1]["input_artifacts"]
    assert "internal_tool_results" in invocations[1]["input_artifacts"]
    assert [item["prompt_skill"] for item in metadata["internal_iterations"]] == [
        "GENERATE",
        "TECHNICAL_REPAIR",
    ]


def test_outer_technical_repair_audits_deterministic_diagnostics() -> None:
    runtime = _runtime([_query_response("select(Overtime.approved_minutes)")])

    _, metadata = runtime.invoke_query_programmer(
        input_payload=_payload(repair_type="TECHNICAL"),
        output_model=phase42.QueryProgrammerResponse,
    )

    invocation = metadata["query_programmer_invocations"][0]
    assert invocation["skill"] == "TECHNICAL_REPAIR"
    assert invocation["repair_type"] == "TECHNICAL"
    assert invocation["repair_attempt"] == 1
    assert "deterministic_validation_result" in invocation["input_artifacts"]
    assert "senior_review" not in invocation["input_artifacts"]
    assert invocation["prompt_id"].endswith("technical_repair")
    assert invocation["prompt_version"] == "v1-skill-technical-repair"


def test_outer_semantic_repair_audits_senior_review_without_validator_noise() -> None:
    runtime = _runtime([_query_response("select(Overtime.approved_minutes)")])

    _, metadata = runtime.invoke_query_programmer(
        input_payload=_payload(repair_type="SEMANTIC"),
        output_model=phase42.QueryProgrammerResponse,
    )

    invocation = metadata["query_programmer_invocations"][0]
    assert invocation["skill"] == "SEMANTIC_REPAIR"
    assert invocation["repair_type"] == "SEMANTIC"
    assert invocation["repair_attempt"] == 1
    assert "senior_review" in invocation["input_artifacts"]
    assert "deterministic_validation_result" not in invocation["input_artifacts"]
    assert invocation["prompt_id"].endswith("semantic_repair")
    assert invocation["prompt_version"] == "v1-skill-semantic-repair"


def test_generate_audit_contains_only_relevant_initial_artifacts() -> None:
    runtime = _runtime([_query_response("select(Overtime.approved_minutes)")])

    _, metadata = runtime.invoke_query_programmer(
        input_payload=_payload(),
        output_model=phase42.QueryProgrammerResponse,
    )

    invocation = metadata["query_programmer_invocations"][0]
    assert invocation["skill"] == "GENERATE"
    assert invocation["input_artifacts"].keys() == {"functional_requirement"}
    assert invocation["model"] == "fake-model"
    assert isinstance(invocation["latency_ms"], float)

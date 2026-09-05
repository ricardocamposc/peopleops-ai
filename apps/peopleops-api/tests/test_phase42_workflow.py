from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
SPIKES = ROOT / "evaluation" / "spikes"
if str(SPIKES) not in sys.path:
    sys.path.insert(0, str(SPIKES))

import direct_sqlalchemy_phase42 as phase42  # noqa: E402


class FakeModel:
    model_name = "fake"

    def __init__(self, outputs: list[BaseModel]) -> None:
        self.outputs = list(outputs)
        self.calls: list[str] = []

    def invoke(
        self,
        *,
        role: str,
        input_payload: dict[str, Any],
        output_model: type[BaseModel],
    ) -> tuple[BaseModel, dict[str, Any]]:
        self.calls.append(role)
        result = self.outputs.pop(0)
        assert isinstance(result, output_model)
        return result, {
            "agent_id": role,
            "prompt_id": f"test.{role}",
            "prompt_version": "test",
            "model": self.model_name,
            "schema_version": output_model.__name__,
            "rendered_messages": [],
            "latency_ms": 0,
        }


def analyst(*, needs_clarification: bool = False) -> phase42.FunctionalAnalystResponse:
    return phase42.FunctionalAnalystResponse(
        needs_clarification=needs_clarification,
        questions_or_missing_information=["period"] if needs_clarification else [],
        original_user_request="test",
        clarified_request="test",
        business_intent="test",
        domain=["overtime"],
        required_information=["approved overtime"],
        measures=["approved overtime"],
        dimensions=[],
        filters=[],
        temporal_requirements=[],
        grouping_requirements=[],
        ordering_requirements=[],
        comparison_requirements=[],
        data_retrieval_request="Retrieve approved overtime.",
        downstream_analysis=[],
        required_sources=["HRIS_STRUCTURED_DATA"],
        assumptions=[],
        ambiguities=[],
        unsupported_requirements=[],
        sensitivity=[],
    )


def query(expression: str = "select(Overtime.approved_minutes)") -> phase42.QueryProgrammerResponse:
    return phase42.QueryProgrammerResponse(
        status="QUERY",
        sqlalchemy=expression,
        interpretation="retrieve overtime",
        assumptions=[],
        missing_information=[],
        models_used=["Overtime"],
        relationships_used=[],
        retrieved_measures=["approved overtime"],
        retrieved_dimensions=[],
        applied_filters=[],
        applied_temporal_constraints=[],
        grouping_implemented=[],
        requirement_coverage=[],
    )


def cannot_implement() -> phase42.QueryProgrammerResponse:
    return phase42.QueryProgrammerResponse(
        status="CANNOT_IMPLEMENT",
        sqlalchemy=None,
        interpretation="unsupported capability",
        assumptions=[],
        missing_information=[],
        models_used=[],
        relationships_used=[],
        retrieved_measures=[],
        retrieved_dimensions=[],
        applied_filters=[],
        applied_temporal_constraints=[],
        grouping_implemented=[],
        requirement_coverage=[],
    )


def review(
    status: str = "APPROVED", *, previous_issue_resolutions: list[phase42.PreviousIssueResolution] | None = None,
) -> phase42.SeniorReview:
    issues = []
    instructions = []
    if status == "REVISE":
        issues = [
            phase42.MaterialIssue(
                type="GROUPING_ERROR",
                severity="ERROR",
                requirement="test",
                issue="grouping missing",
                why_it_matters="material",
                required_correction="fix grouping",
            )
        ]
        instructions = ["fix grouping"]
    return phase42.SeniorReview(
        status=status,
        summary=status.lower(),
        material_issues=issues,
        requirement_review=[],
        query_semantics_review=phase42.QuerySemanticsReview(
            temporal_correctness="ok",
            measure_correctness="ok",
            dimension_correctness="ok",
            filter_correctness="ok",
            aggregation_correctness="ok",
            grouping_correctness="ok",
            ordering_correctness="ok",
            relationship_correctness="ok",
            duplicate_risk="none",
            data_sufficiency="ok",
            comparison_preservation="ok",
        ),
        repair_instructions=instructions,
        assumptions=[],
        missing_information=[],
        confidence=1,
        previous_issue_resolutions=previous_issue_resolutions or [],
    )


def test_invalid_query_never_reaches_senior_before_technical_repair() -> None:
    llm = FakeModel([
        analyst(),
        query("select("),
        query("select(Overtime.approved_minutes)"),
        review("APPROVED"),
    ])
    result = phase42.build_graph().invoke(
        phase42.initial_state(mode="AGENT_TEAM", question="test", llm=llm)
    )
    assert result["final_status"] == "APPROVED"
    assert result["technical_repair_attempts"] == 1
    assert llm.calls == [
        "semantic_clarifier",
        "sqlalchemy_query_developer",
        "sqlalchemy_query_developer",
        "senior_query_reviewer",
    ]


def test_cannot_implement_never_reaches_validator_or_senior() -> None:
    llm = FakeModel([analyst(), cannot_implement()])
    result = phase42.build_graph().invoke(
        phase42.initial_state(mode="AGENT_TEAM", question="test", llm=llm)
    )
    assert result["final_status"] == "CANNOT_IMPLEMENT"
    assert not any(event["role"] == "query_validation" for event in result["audit_trail"])
    assert result["senior_reviews"] == []


def test_semantic_revision_is_revalidated_before_second_senior_review() -> None:
    llm = FakeModel([
        analyst(),
        query(),
        review("REVISE"),
        query("select("),
        query(),
        review("APPROVED"),
    ])
    result = phase42.build_graph().invoke(
        phase42.initial_state(mode="AGENT_TEAM", question="test", llm=llm)
    )
    assert result["final_status"] == "APPROVED"
    assert result["semantic_revision_attempts"] == 1
    assert result["technical_repair_attempts"] == 1
    assert len(result["senior_reviews"]) == 2


def test_validation_diagnostic_contains_syntax_location() -> None:
    result = phase42._validation("select(")
    diagnostic = result["diagnostics"][0]
    assert diagnostic["stage"] == "PYTHON_SYNTAX"
    assert diagnostic["line"] == 1
    assert diagnostic["offset"] is not None


def test_human_payload_does_not_duplicate_model_or_reference_context() -> None:
    payload = {
        "query_task": {"data_retrieval_request": "test"},
        "data_model": "class Employee",
        "reference_context": phase42.REFERENCE_CONTEXT,
        "repair_type": None,
        "repair_attempt": 0,
    }
    human = phase42._human_payload("sqlalchemy_query_developer", payload)
    assert "data_model" not in human
    assert "reference_context" not in human
    assert "functional_requirement" in human


def test_senior_can_mark_a_previous_issue_resolved() -> None:
    llm = FakeModel([
        analyst(), query(), review("REVISE"), query(),
        review(
            "APPROVED",
            previous_issue_resolutions=[phase42.PreviousIssueResolution(
                previous_issue="grouping missing",
                resolution_status="RESOLVED",
                evidence="The repaired query groups by the requested dimension.",
            )],
        ),
    ])
    result = phase42.build_graph().invoke(
        phase42.initial_state(mode="AGENT_TEAM", question="test", llm=llm)
    )
    assert result["final_status"] == "APPROVED"
    assert result["senior_reviews"][-1]["previous_issue_resolutions"][0]["resolution_status"] == "RESOLVED"

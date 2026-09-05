from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

import direct_sqlalchemy_phase42 as phase42
import direct_sqlalchemy_phase43 as phase43


class FakeBoundModel:
    def __init__(self, messages: list[AIMessage]) -> None:
        self.messages = list(messages)
        self.calls = 0

    def invoke(self, _messages: Any) -> AIMessage:
        self.calls += 1
        return self.messages.pop(0)


class FakeChatModel:
    def __init__(self, bound: FakeBoundModel) -> None:
        self.bound = bound
        self.bound_tools: list[Any] = []
        self.tool_choice: str | None = None

    def bind_tools(self, tools: list[Any], tool_choice: str | None = None) -> FakeBoundModel:
        self.bound_tools = tools
        self.tool_choice = tool_choice
        return self.bound


def _runtime(messages: list[AIMessage]) -> phase43.LangChainToolCallingRuntime:
    runtime = object.__new__(phase43.LangChainToolCallingRuntime)
    runtime.model_config = {"sqlalchemy_query_developer": "fake"}
    runtime.templates = phase42._prompt_templates()
    runtime.models = {
        "sqlalchemy_query_developer": FakeChatModel(FakeBoundModel(messages))
    }
    return runtime


def _payload(*, repair_type: str | None = None) -> dict[str, Any]:
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
        "repair_attempt": 0,
        "previous_query": None,
        "deterministic_validation_result": None,
        "senior_review": None,
    }


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def _submit_query(candidate: str, call_id: str) -> AIMessage:
    return _tool_call(
        "SubmitQueryProgrammerResult",
        {
            "status": "QUERY",
            "sqlalchemy": candidate,
            "interpretation": "retrieve overtime",
            "assumptions": [],
            "missing_information": [],
            "models_used": ["Overtime"],
            "relationships_used": [],
            "retrieved_measures": ["approved overtime minutes"],
            "retrieved_dimensions": [],
            "applied_filters": [],
            "applied_temporal_constraints": [],
            "grouping_implemented": [],
            "requirement_coverage": [],
        },
        call_id,
    )


def _submit_cannot(call_id: str) -> AIMessage:
    return _tool_call(
        "SubmitQueryProgrammerResult",
        {
            "status": "CANNOT_IMPLEMENT",
            "sqlalchemy": None,
            "interpretation": "I could not fix the syntax.",
            "assumptions": [],
            "missing_information": [],
            "models_used": [],
            "relationships_used": [],
            "retrieved_measures": [],
            "retrieved_dimensions": [],
            "applied_filters": [],
            "applied_temporal_constraints": [],
            "grouping_implemented": [],
            "requirement_coverage": [],
        },
        call_id,
    )


def test_validate_candidate_uses_short_circuit_gate() -> None:
    result = phase43.validate_sqlalchemy_candidate("select(")
    assert result["valid"] is False
    assert [item["stage"] for item in result["stages"]] == ["PYTHON_SYNTAX"]
    assert result["stats"]["tool_calls_avoided_by_short_circuit"] == 2


def test_agent_must_observe_validation_before_query_submission() -> None:
    candidate = "select(Overtime.approved_minutes)"
    runtime = _runtime([
        AIMessage(
            content="",
            tool_calls=[
                {"name": "validate_sqlalchemy_candidate", "args": {"candidate": candidate}, "id": "v1", "type": "tool_call"},
                {"name": "SubmitQueryProgrammerResult", "args": _submit_query(candidate, "ignored").tool_calls[0]["args"], "id": "s1", "type": "tool_call"},
            ],
        ),
        _submit_query(candidate, "s2"),
    ])
    result, metadata = runtime.invoke_query_programmer(
        input_payload=_payload(), output_model=phase42.QueryProgrammerResponse
    )
    assert result.status == "QUERY"
    assert metadata["candidate_valid_before_external_validator"] is True
    assert metadata["agent_submission_rejections"] == 1
    assert metadata["tool_calling_mode"] == "MODEL_INITIATED"


def test_agent_repairs_invalid_candidate_through_tool_feedback() -> None:
    invalid = "select("
    valid = "select(Overtime.approved_minutes)"
    runtime = _runtime([
        _tool_call("validate_sqlalchemy_candidate", {"candidate": invalid}, "v1"),
        _tool_call("validate_sqlalchemy_candidate", {"candidate": valid}, "v2"),
        _submit_query(valid, "s1"),
    ])
    result, metadata = runtime.invoke_query_programmer(
        input_payload=_payload(), output_model=phase42.QueryProgrammerResponse
    )
    assert result.status == "QUERY"
    assert result.sqlalchemy == valid
    assert metadata["internal_validation_attempts"] == 2
    assert metadata["internal_self_repair_attempts"] == 1
    assert metadata["internal_self_repair_success"] == 1
    assert metadata["internal_candidates_changed"] == 1


def test_technical_error_cannot_be_reclassified_as_capability_gap() -> None:
    invalid = "select("
    valid = "select(Overtime.approved_minutes)"
    runtime = _runtime([
        _tool_call("validate_sqlalchemy_candidate", {"candidate": invalid}, "v1"),
        _submit_cannot("s1"),
        _tool_call("validate_sqlalchemy_candidate", {"candidate": valid}, "v2"),
        _submit_query(valid, "s2"),
    ])
    result, metadata = runtime.invoke_query_programmer(
        input_payload=_payload(repair_type="TECHNICAL"),
        output_model=phase42.QueryProgrammerResponse,
    )
    assert result.status == "QUERY"
    assert metadata["agent_submission_rejections"] == 1
    rejected = [
        item for item in metadata["internal_iterations"]
        if item.get("kind") == "SUBMISSION_REJECTED"
    ]
    assert rejected[0]["result"]["reason"] == "TECHNICAL_ERROR_IS_NOT_CAPABILITY_GAP"


def test_capability_gap_is_allowed_without_technical_failure() -> None:
    runtime = _runtime([_submit_cannot("s1")])
    result, metadata = runtime.invoke_query_programmer(
        input_payload=_payload(), output_model=phase42.QueryProgrammerResponse
    )
    assert result.status == "CANNOT_IMPLEMENT"
    assert metadata["agent_submission_rejections"] == 0


def test_exhausted_agent_returns_invalid_fallback_for_external_validator() -> None:
    invalid_calls = [
        _tool_call("validate_sqlalchemy_candidate", {"candidate": "select("}, f"v{i}")
        for i in range(phase43.MAX_AGENT_TOOL_ROUNDS)
    ]
    runtime = _runtime(invalid_calls)
    result, metadata = runtime.invoke_query_programmer(
        input_payload=_payload(), output_model=phase42.QueryProgrammerResponse
    )
    assert result.status == "QUERY"
    assert result.sqlalchemy == "("
    assert metadata["technical_generation_failed"] is True
    assert phase42._validation(result.sqlalchemy)["technically_valid"] is False


def test_phase43_terminal_technical_failure_is_not_cannot_implement() -> None:
    state: phase43.Phase43State = {"stage_history": []}
    output = phase43._technical_failed(state)
    assert output["final_status"] == "TECHNICAL_GENERATION_FAILED"

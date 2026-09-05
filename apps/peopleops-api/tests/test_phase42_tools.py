from __future__ import annotations

from typing import Any

from pydantic import BaseModel

import direct_sqlalchemy_phase42 as phase42


def test_validate_python_syntax_reports_useful_diagnostic() -> None:
    result = phase42.validate_python_syntax("select(")
    assert result["valid"] is False
    assert result["stage"] == "PYTHON_SYNTAX"
    assert result["exception_type"] == "SyntaxError"
    assert result["line"] == 1
    assert result["offset"] is not None


def test_build_tool_reports_sqlalchemy_construction_error() -> None:
    result = phase42.build_sqlalchemy_query("select(Overtime.missing_attribute)")
    assert result["valid"] is False
    assert result["stage"] == "SQLALCHEMY_BUILD"
    assert result["message"]
    assert result["source"] == "select(Overtime.missing_attribute)"


def test_compile_tool_accepts_safe_select_without_database_access() -> None:
    result = phase42.compile_sqlalchemy_query("select(Overtime.approved_minutes)")
    assert result["valid"] is True
    assert result["stage"] == "SQLALCHEMY_COMPILE"
    assert result["compiled_sql"].startswith("SELECT")


def test_internal_tools_short_circuit_after_syntax_failure() -> None:
    events, stats = phase42._run_internal_tools("select(")
    assert [event["stage"] for event in events] == ["PYTHON_SYNTAX"]
    assert stats["syntax_short_circuits"] == 1
    assert stats["compile_attempts"] == 0
    assert stats["tool_calls_avoided_by_short_circuit"] == 2


def test_internal_tools_short_circuit_after_build_failure(monkeypatch: Any) -> None:
    original = phase42.build_statement
    calls = {"compile": 0}

    monkeypatch.setattr(phase42, "build_statement", lambda source: (None, ["BUILD_ERROR:test"]))
    monkeypatch.setattr(
        phase42, "compile_sqlalchemy_query",
        lambda *args, **kwargs: calls.__setitem__("compile", calls["compile"] + 1),
    )
    events, stats = phase42._run_internal_tools("select(Overtime.approved_minutes)")
    monkeypatch.setattr(phase42, "build_statement", original)
    assert [event["stage"] for event in events] == ["PYTHON_SYNTAX", "SQLALCHEMY_BUILD"]
    assert stats["build_short_circuits"] == 1
    assert stats["compile_attempts"] == 0
    assert calls["compile"] == 0


def test_internal_tools_builds_once_and_reuses_statement(monkeypatch: Any) -> None:
    calls = {"build": 0}
    original = phase42.build_statement

    def counted(source: str) -> Any:
        calls["build"] += 1
        return original(source)

    monkeypatch.setattr(phase42, "build_statement", counted)
    events, stats = phase42._run_internal_tools("select(Overtime.approved_minutes)")
    assert calls["build"] == 1
    assert stats["compile_attempts"] == 1
    assert events[-1]["valid"] is True


class StubRuntime:
    model_name = "stub"

    def __init__(self, outputs: list[BaseModel]) -> None:
        self.outputs = outputs

    def invoke(
        self, *, role: str, input_payload: dict[str, Any], output_model: type[BaseModel]
    ) -> tuple[BaseModel, dict[str, Any]]:
        result = self.outputs.pop(0)
        assert isinstance(result, output_model)
        return result, {"model": self.model_name}


def query_programmer_response(expression: str) -> phase42.QueryProgrammerResponse:
    return phase42.QueryProgrammerResponse(
        status="QUERY",
        sqlalchemy=expression,
        interpretation="retrieve data",
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


def test_internal_programmer_cycle_repairs_and_stops_on_valid_candidate() -> None:
    runtime = object.__new__(phase42.LangChainAgentRuntime)
    outputs = [
        query_programmer_response("select("),
        query_programmer_response("select(Overtime.approved_minutes)"),
    ]
    runtime.invoke = StubRuntime(outputs).invoke  # type: ignore[method-assign]
    result, metadata = runtime.invoke_query_programmer(
        input_payload={"query_task": {}, "data_model": "", "reference_context": phase42.REFERENCE_CONTEXT},
        output_model=phase42.QueryProgrammerResponse,
    )
    assert result.status == "QUERY"
    assert metadata["internal_tool_calls"] == 4
    assert metadata["internal_validation_attempts"] == 2
    assert metadata["internal_self_repair_attempts"] == 1
    assert metadata["internal_self_repair_success"] == 1
    assert [item["generation_type"] for item in metadata["internal_iterations"]] == [
        "INITIAL", "INTERNAL_TECHNICAL_REPAIR"
    ]
    assert metadata["internal_iterations"][0]["final_iteration"] is False
    assert metadata["internal_iterations"][1]["final_iteration"] is True


def test_internal_programmer_cycle_has_explicit_repair_limit() -> None:
    runtime = object.__new__(phase42.LangChainAgentRuntime)
    runtime.invoke = StubRuntime(
        [query_programmer_response("select(")] * 3
    ).invoke  # type: ignore[method-assign]
    result, metadata = runtime.invoke_query_programmer(
        input_payload={"query_task": {}, "data_model": "", "reference_context": phase42.REFERENCE_CONTEXT},
        output_model=phase42.QueryProgrammerResponse,
    )
    assert result.status == "QUERY"
    assert metadata["internal_validation_attempts"] == 3
    assert metadata["internal_self_repair_attempts"] == phase42.MAX_INTERNAL_SELF_REPAIR_ATTEMPTS
    assert metadata["internal_self_repair_success"] == 0
    assert metadata["internal_candidates_unchanged"] == 2
    assert all(item["candidate_changed"] is not True for item in metadata["internal_iterations"][1:])

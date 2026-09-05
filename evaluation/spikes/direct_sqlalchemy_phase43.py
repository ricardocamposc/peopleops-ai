"""Phase 4.3 — agentic Query Programmer with real LangChain tool calling.

This experiment preserves the Phase 4.2 Functional Analyst, deterministic external
validator, Senior Reviewer, and bounded outer repair workflow. The only material
change is the Query Programmer interaction: candidate validation is now an actual
model tool call inside one agent conversation rather than an application-triggered
post-generation loop.
"""
from __future__ import annotations

import time
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field
from langgraph.graph import END, START, StateGraph

import direct_sqlalchemy_phase42 as phase42


MAX_CANDIDATE_VALIDATIONS = phase42.MAX_INTERNAL_SELF_REPAIR_ATTEMPTS + 1
MAX_AGENT_TOOL_ROUNDS = 8

PHASE43_QUERY_PROGRAMMER_ADDENDUM = """

## Phase 4.3 tool-calling contract

You have two application tools available during this query-programming turn:

1. `validate_sqlalchemy_candidate(candidate)` validates one candidate through the
   deterministic Python-syntax, SQLAlchemy-build, and PostgreSQL-compilation gate.
2. `SubmitQueryProgrammerResult(...)` submits your final structured result.

When the Functional Requirement is implementable and you intend to return `QUERY`:

- write a complete SQLAlchemy candidate;
- call `validate_sqlalchemy_candidate` with that exact candidate;
- inspect the tool result;
- if invalid, correct the candidate using the concrete diagnostic and validate again;
- only after a candidate is reported valid, call `SubmitQueryProgrammerResult` with
  `status=QUERY` and the exact validated candidate.

Do not submit an unvalidated `QUERY` candidate. Do not treat syntax, construction,
compilation, or other implementation failures as evidence that the data model lacks
capability. `CANNOT_IMPLEMENT` is only for a genuine model-capability gap in the
Functional Requirement. A failed validation means you must repair the implementation
within the available tool-call budget.

Use tool results as objective technical feedback. Do not repeat an invalid candidate
without making a meaningful correction. The application still performs an independent
external deterministic validation after your submission.
""".strip()


class ValidateSQLAlchemyCandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate: str = Field(description="One complete read-only SQLAlchemy 2.x expression.")


class SubmitQueryProgrammerResult(phase42.QueryProgrammerResponse):
    """Submit the final Query Programmer result after any required validation."""


class Phase43State(phase42.Phase42State, total=False):
    agent_tool_rounds: int
    agent_submission_attempts: int
    agent_submission_rejections: int
    technical_generation_failed: bool


def validate_sqlalchemy_candidate(candidate: str) -> dict[str, Any]:
    """Validate one candidate with deterministic short-circuiting and no DB access."""
    events, stats = phase42._run_internal_tools(candidate)
    valid = bool(events) and all(item.get("valid") is True for item in events)
    return {
        "valid": valid,
        "candidate": candidate,
        "stages": events,
        "errors": [item.get("message") for item in events if not item.get("valid")],
        "compiled_sql": next(
            (item.get("compiled_sql") for item in reversed(events) if item.get("compiled_sql")),
            None,
        ),
        "stats": stats,
    }


def _validation_tool() -> StructuredTool:
    return StructuredTool.from_function(
        func=validate_sqlalchemy_candidate,
        name="validate_sqlalchemy_candidate",
        description=(
            "Validate one complete SQLAlchemy 2.x read-only candidate. The tool checks "
            "safe Python syntax, builds it in the closed SQLAlchemy namespace, and compiles "
            "it for PostgreSQL without executing a database query. Use its structured "
            "diagnostics to repair invalid candidates."
        ),
        args_schema=ValidateSQLAlchemyCandidateInput,
    )


def _render_programmer_messages(
    runtime: phase42.LangChainAgentRuntime, input_payload: dict[str, Any]
) -> tuple[list[BaseMessage], str]:
    variables = phase42._chain_variables(input_payload)
    variables["user_input"] = phase42._json(
        phase42._human_payload("sqlalchemy_query_developer", input_payload)
    )
    rendered = runtime.templates["sqlalchemy_query_developer"].format_messages(**variables)
    rendered_system_prompt = f"{rendered[0].content}\n\n{PHASE43_QUERY_PROGRAMMER_ADDENDUM}"
    messages: list[BaseMessage] = [SystemMessage(content=rendered_system_prompt), *rendered[1:]]
    return messages, rendered_system_prompt


def _tool_message(tool_call_id: str, payload: dict[str, Any]) -> ToolMessage:
    return ToolMessage(content=phase42._json(payload), tool_call_id=tool_call_id)


def _capability_gap_predeclared(input_payload: dict[str, Any]) -> bool:
    task = input_payload.get("query_task") or {}
    return bool(task.get("unsupported_requirements"))


class LangChainToolCallingRuntime(phase42.LangChainAgentRuntime):
    """Query Programmer runtime whose validation occurs through real model tool calls."""

    model_name = "langchain-tool-calling"

    def invoke_query_programmer(
        self, *, input_payload: dict[str, Any], output_model: type[BaseModel]
    ) -> tuple[BaseModel, dict[str, Any]]:
        if output_model is not phase42.QueryProgrammerResponse:
            raise TypeError("Phase 4.3 Query Programmer requires QueryProgrammerResponse")

        role = "sqlalchemy_query_developer"
        spec = phase42.AGENT_SPECS[role]
        messages, rendered_system_prompt = _render_programmer_messages(self, input_payload)
        validation_tool = _validation_tool()
        bound_model = self.models[role].bind_tools(
            [validation_tool, SubmitQueryProgrammerResult],
            tool_choice="required",
        )

        started = time.perf_counter()
        validation_attempts = 0
        submission_attempts = 0
        submission_rejections = 0
        tool_calls_total = 0
        valid_candidate: str | None = None
        valid_candidate_round: int | None = None
        previous_candidate: str | None = None
        had_technical_error = False
        interactions: list[dict[str, Any]] = []
        aggregate_stats = {
            "syntax_short_circuits": 0,
            "build_short_circuits": 0,
            "compile_attempts": 0,
            "tool_calls_avoided_by_short_circuit": 0,
        }

        def metadata(*, technical_generation_failed: bool = False) -> dict[str, Any]:
            for item in interactions:
                item.setdefault(
                    "repair_input",
                    {"round": item.get("round"), "kind": item.get("kind")},
                )
            successful_repair = int(
                validation_attempts > 1
                and valid_candidate is not None
                and any(item.get("candidate_changed") for item in interactions)
            )
            return {
                "agent_id": role,
                "prompt_id": spec["prompt_id"],
                "prompt_version": "v3-agentic-tool-calling",
                "model": self.model_config[role],
                "schema_version": output_model.__name__,
                "rendered_messages": [
                    {"role": getattr(message, "type", "unknown"), "content": message.content}
                    for message in messages
                ],
                "rendered_system_prompt": rendered_system_prompt,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "tool_assisted": True,
                "tool_calling_mode": "MODEL_INITIATED",
                "agent_tool_rounds": len(interactions),
                "agent_submission_attempts": submission_attempts,
                "agent_submission_rejections": submission_rejections,
                "internal_tool_calls": tool_calls_total,
                "internal_validation_attempts": validation_attempts,
                "internal_self_repair_attempts": max(validation_attempts - 1, 0),
                "internal_self_repair_success": successful_repair,
                "candidate_valid_before_external_validator": valid_candidate is not None,
                "internal_iterations": interactions,
                "internal_candidates_generated": validation_attempts,
                "internal_candidates_changed": sum(
                    item.get("candidate_changed") is True for item in interactions
                ),
                "internal_candidates_unchanged": sum(
                    item.get("candidate_changed") is False for item in interactions
                ),
                "technical_generation_failed": technical_generation_failed,
                **aggregate_stats,
            }

        for round_number in range(1, MAX_AGENT_TOOL_ROUNDS + 1):
            ai_message: AIMessage = bound_model.invoke(messages)
            messages.append(ai_message)
            calls = list(getattr(ai_message, "tool_calls", []) or [])
            if not calls:
                interactions.append({
                    "round": round_number,
                    "kind": "NO_TOOL_CALL",
                    "content": ai_message.content,
                })
                continue

            for call in calls:
                tool_calls_total += 1
                name = call["name"]
                args = call.get("args") or {}
                call_id = call["id"]

                if name == "validate_sqlalchemy_candidate":
                    candidate = str(args.get("candidate") or "")
                    changed = None if previous_candidate is None else candidate != previous_candidate

                    if validation_attempts >= MAX_CANDIDATE_VALIDATIONS:
                        result = {
                            "valid": False,
                            "candidate": candidate,
                            "errors": ["Candidate validation budget exhausted."],
                            "stage": "TOOL_BUDGET",
                        }
                    else:
                        validation_attempts += 1
                        result = validate_sqlalchemy_candidate(candidate)
                        for key in aggregate_stats:
                            aggregate_stats[key] += result["stats"].get(key, 0)
                        if result["valid"]:
                            valid_candidate = candidate
                            valid_candidate_round = round_number
                        else:
                            had_technical_error = True

                    interactions.append({
                        "round": round_number,
                        "kind": "VALIDATION_TOOL_CALL",
                        "candidate": candidate,
                        "candidate_changed": changed,
                        "result": result,
                    })
                    previous_candidate = candidate
                    messages.append(_tool_message(call_id, result))
                    continue

                if name == "SubmitQueryProgrammerResult":
                    submission_attempts += 1
                    try:
                        submitted = SubmitQueryProgrammerResult.model_validate(args)
                        result = phase42.QueryProgrammerResponse.model_validate(
                            submitted.model_dump(mode="python")
                        )
                    except Exception as exc:  # noqa: BLE001
                        submission_rejections += 1
                        feedback = {
                            "accepted": False,
                            "reason": "INVALID_SUBMISSION_SCHEMA",
                            "message": str(exc),
                        }
                        interactions.append({
                            "round": round_number,
                            "kind": "SUBMISSION_REJECTED",
                            "result": feedback,
                        })
                        messages.append(_tool_message(call_id, feedback))
                        continue

                    if result.status == "QUERY" and (
                        valid_candidate is None
                        or result.sqlalchemy != valid_candidate
                        or valid_candidate_round is None
                        or valid_candidate_round >= round_number
                    ):
                        submission_rejections += 1
                        feedback = {
                            "accepted": False,
                            "reason": "QUERY_NOT_VALIDATED",
                            "message": (
                                "A QUERY submission must use the exact candidate validated "
                                "successfully in a prior tool round, after you have received and "
                                "inspected the validation result."
                            ),
                            "validated_candidate": valid_candidate,
                        }
                        interactions.append({
                            "round": round_number,
                            "kind": "SUBMISSION_REJECTED",
                            "status": result.status,
                            "result": feedback,
                        })
                        messages.append(_tool_message(call_id, feedback))
                        continue

                    if result.status == "CANNOT_IMPLEMENT" and had_technical_error and not (
                        _capability_gap_predeclared(input_payload)
                    ):
                        submission_rejections += 1
                        feedback = {
                            "accepted": False,
                            "reason": "TECHNICAL_ERROR_IS_NOT_CAPABILITY_GAP",
                            "message": (
                                "The current evidence is a technical generation/validation "
                                "failure, not a demonstrated data-model capability gap. Repair "
                                "the implementation or exhaust the technical-generation budget."
                            ),
                        }
                        interactions.append({
                            "round": round_number,
                            "kind": "SUBMISSION_REJECTED",
                            "status": result.status,
                            "result": feedback,
                        })
                        messages.append(_tool_message(call_id, feedback))
                        continue

                    interactions.append({
                        "round": round_number,
                        "kind": "SUBMISSION_ACCEPTED",
                        "status": result.status,
                    })
                    messages.append(_tool_message(call_id, {"accepted": True}))
                    return result, metadata()

                submission_rejections += 1
                feedback = {
                    "accepted": False,
                    "reason": "UNKNOWN_TOOL",
                    "message": f"Unsupported tool call: {name}",
                }
                interactions.append({
                    "round": round_number,
                    "kind": "UNKNOWN_TOOL",
                    "tool": name,
                })
                messages.append(_tool_message(call_id, feedback))

        fallback = phase42.QueryProgrammerResponse(
            status="QUERY",
            sqlalchemy="(",
            interpretation=(
                "Query Programmer exhausted the bounded tool-calling generation budget "
                "without a validated final submission."
            ),
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
        return fallback, metadata(technical_generation_failed=True)


def _technical_failed(state: Phase43State) -> dict[str, Any]:
    phase42._transition(state, "failed", "technical_generation_failed")
    return {"final_status": "TECHNICAL_GENERATION_FAILED"}


def build_graph() -> Any:
    """Build Phase 4.3 while preserving the validated Phase 4.2 outer workflow."""
    graph = StateGraph(Phase43State)
    graph.add_node("semantic_clarifier", phase42._semantic_clarifier)
    graph.add_node("query_developer", phase42._query_developer)
    graph.add_node("query_validation", phase42._query_validation)
    graph.add_node("technical_repair", phase42._technical_repair)
    graph.add_node("technical_failed", _technical_failed)
    graph.add_node("senior_query_reviewer", phase42._senior_query_reviewer)
    graph.add_node("semantic_repair", phase42._semantic_repair)
    graph.add_node("semantic_failed", phase42._semantic_failed)

    graph.add_edge(START, "semantic_clarifier")
    graph.add_conditional_edges(
        "semantic_clarifier", phase42._after_clarifier,
        {"query_developer": "query_developer", "end": END},
    )
    graph.add_conditional_edges(
        "query_developer", phase42._after_query_developer,
        {"validation": "query_validation", "end": END},
    )
    graph.add_conditional_edges(
        "query_validation", phase42._after_validation,
        {
            "senior": "senior_query_reviewer",
            "technical_repair": "technical_repair",
            "technical_failed": "technical_failed",
            "end": END,
        },
    )
    graph.add_edge("technical_repair", "query_developer")
    graph.add_edge("technical_failed", END)
    graph.add_conditional_edges(
        "senior_query_reviewer", phase42._after_senior,
        {
            "end": END,
            "semantic_repair": "semantic_repair",
            "semantic_failed": "semantic_failed",
        },
    )
    graph.add_edge("semantic_repair", "query_developer")
    graph.add_edge("semantic_failed", END)
    return graph.compile()


def initial_state(
    *, mode: Literal["FUNCTIONAL_ANALYST_ONLY", "QUERY_DEVELOPER_ONLY", "AGENT_TEAM"],
    question: str,
    llm: phase42.StructuredModel,
    reference_context: dict[str, Any] | None = None,
) -> Phase43State:
    state: Phase43State = phase42.initial_state(
        mode=mode,
        question=question,
        llm=llm,
        reference_context=reference_context,
    )
    state.update({
        "agent_tool_rounds": 0,
        "agent_submission_attempts": 0,
        "agent_submission_rejections": 0,
        "technical_generation_failed": False,
    })
    return state


def assert_phase43_contract() -> None:
    valid = validate_sqlalchemy_candidate("select(Overtime.approved_minutes)")
    assert valid["valid"] is True
    assert valid["compiled_sql"]

    invalid = validate_sqlalchemy_candidate("select(")
    assert invalid["valid"] is False
    assert len(invalid["stages"]) == 1
    assert invalid["stages"][0]["stage"] == "PYTHON_SYNTAX"

    assert "CANNOT_IMPLEMENT" in PHASE43_QUERY_PROGRAMMER_ADDENDUM
    assert "validate_sqlalchemy_candidate" in PHASE43_QUERY_PROGRAMMER_ADDENDUM
    assert MAX_CANDIDATE_VALIDATIONS == 3


if __name__ == "__main__":
    assert_phase43_contract()
    print("DIRECT_SQLALCHEMY_PHASE43_SELF_TEST_OK")

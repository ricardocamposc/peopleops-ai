"""Bounded Senior Reviewer subgraph for conceptual-query supervision.

The reviewer validates and executes only provider-neutral queries through the
HRDataGateway.  The outer workflow still owns repair cycles and terminal
routing; this subgraph owns the review conversation and its tool protocol.
"""

from __future__ import annotations

import json
import hashlib
import os
from typing import Any, Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field

from peopleops_api.analysis_contracts import AnalysisPlan, SeniorReview, SeniorReviewIssue, SemanticRequest
from peopleops_api.hr_data_gateway import HRDataGateway
from peopleops_api.mcp_contracts import DiscoveryCatalog, SecurityContext
from peopleops_api.query_contracts import ConceptualQuery, QueryResult
from peopleops_api.semantic_coverage import verify_semantic_coverage

MAX_SENIOR_REVIEW_ROUNDS = 4


class ReviewQueryInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    query_index: int | None = Field(default=None, ge=0, le=7)
    query: dict[str, Any] = Field(default_factory=dict)


class RepairRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(APPROVE|REVISE|FAILED|NEEDS_CLARIFICATION)$")
    summary: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    issues: list[dict[str, Any]] = Field(default_factory=list, max_length=8)


class VerifySemanticCoverageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SeniorReviewerState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    model_rounds: int
    tool_calls: int
    model_events: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]
    validations: dict[int, dict[str, Any]]
    executions: dict[int, dict[str, Any]]
    semantic_coverage: dict[str, Any] | None
    decision: dict[str, Any] | None
    termination_reason: str | None


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _query_fingerprint(query: dict[str, Any]) -> str:
    canonical = json.dumps(query, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _review_query_args(query_index: int | None, query: dict[str, Any], extra: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    direct_query = {key: value for key, value in extra.items() if key not in {"query_index", "query"}}
    if not query and direct_query:
        query = direct_query
    return 0 if query_index is None else query_index, query


class SeniorReviewerAgentError(RuntimeError):
    def __init__(self, message: str, metadata: dict[str, Any]) -> None:
        super().__init__(message)
        self.metadata = metadata


class SeniorReviewerAgent:
    """Tool-calling reviewer with a bounded validation/execution subgraph."""

    def __init__(
        self,
        *,
        gateway: HRDataGateway,
        security: SecurityContext,
        request_id: str,
        catalog: DiscoveryCatalog | None,
        model_name: str | None = None,
        api_key: str | None = None,
        max_rounds: int = MAX_SENIOR_REVIEW_ROUNDS,
    ) -> None:
        from langchain_openai import ChatOpenAI

        self.gateway = gateway
        self.security = security
        self.request_id = request_id
        self.catalog = catalog
        self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.max_rounds = max(1, max_rounds)
        self.model = ChatOpenAI(
            model=self.model_name,
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            temperature=0,
            max_retries=2,
        )

    def _tools(
        self,
        validated_cache: dict[int, dict[str, Any]],
        semantic_request: SemanticRequest,
        plan: AnalysisPlan,
    ) -> list[StructuredTool]:
        def validate(
            query_index: int | None = None, query: dict[str, Any] | None = None, **extra: Any
        ) -> dict[str, Any]:
            query_index, query = _review_query_args(query_index, query or {}, extra)
            try:
                parsed = ConceptualQuery.model_validate(query)
                result = self.gateway.validate_query(
                    parsed, request_id=self.request_id, security=self.security
                )
                payload = {
                    "query_index": query_index,
                    "valid": result.valid,
                    **result.model_dump(mode="json"),
                }
                validated_cache[query_index] = {
                    "fingerprint": _query_fingerprint(query),
                    **payload,
                }
                return payload
            except Exception as exc:  # noqa: BLE001 - tool feedback is part of the protocol
                return {"query_index": query_index, "valid": False, "errors": [str(exc)]}

        def execute(
            query_index: int | None = None, query: dict[str, Any] | None = None, **extra: Any
        ) -> dict[str, Any]:
            query_index, query = _review_query_args(query_index, query or {}, extra)
            try:
                parsed = ConceptualQuery.model_validate(query)
                validation = validated_cache.get(query_index)
                if not validation or not validation.get("valid") or validation.get("fingerprint") != _query_fingerprint(query):
                    return {
                        "query_index": query_index,
                        "executed": False,
                        "errors": list((validation or {}).get("errors", [])),
                        "reason": "QUERY_MUST_BE_VALIDATED_BEFORE_EXECUTION",
                    }
                result: QueryResult = self.gateway.execute_query(
                    parsed, request_id=self.request_id, security=self.security
                )
                return {
                    "query_index": query_index,
                    "query_fingerprint": _query_fingerprint(query),
                    "executed": True,
                    "result": result.model_dump(mode="json"),
                }
            except Exception as exc:  # noqa: BLE001 - tool feedback is part of the protocol
                return {"query_index": query_index, "executed": False, "errors": [str(exc)]}

        def request_repair(status: str, summary: str, confidence: float, issues: list[dict[str, Any]]) -> dict[str, Any]:
            try:
                normalized_issues = []
                for item in issues:
                    # Accept the previous prompt's recommendation label at
                    # this boundary while persisting only the current typed
                    # SeniorReviewIssue contract.
                    normalized = dict(item)
                    if "correction_guidance" not in normalized and "recommendation" in normalized:
                        normalized["correction_guidance"] = normalized.pop("recommendation")
                    normalized.setdefault("category", "semantic")
                    normalized.setdefault("severity", "medium")
                    normalized_issues.append(normalized)
                parsed_issues = [SeniorReviewIssue.model_validate(item).model_dump(mode="json") for item in normalized_issues]
                decision = SeniorReview(
                    status=status,
                    summary=summary,
                    confidence=confidence,
                    issues=parsed_issues,
                )
                return {
                    "submitted": True,
                    "repair_requested": status == "REVISE",
                    "review": decision.model_dump(mode="json"),
                }
            except Exception as exc:  # noqa: BLE001 - tool feedback is part of the protocol
                return {"submitted": False, "errors": [str(exc)]}

        def verify_coverage() -> dict[str, Any]:
            return verify_semantic_coverage(semantic_request, plan, []).model_dump()

        return [
            StructuredTool.from_function(
                func=verify_coverage,
                name="verify_semantic_coverage",
                description=(
                    "Verify whether the complete AnalysisPlan covers the typed operational "
                    "semantic conditions from the Functional Analyst. This does not execute "
                    "queries and does not validate SQL."
                ),
                args_schema=VerifySemanticCoverageInput,
            ),
            StructuredTool.from_function(
                func=validate,
                name="validate_conceptual_query",
                description="Validate a conceptual query through MCP before execution.",
                args_schema=ReviewQueryInput,
            ),
            StructuredTool.from_function(
                func=execute,
                name="execute_conceptual_query",
                description="Execute a query only after validation; return provider-neutral rows.",
                args_schema=ReviewQueryInput,
            ),
            StructuredTool.from_function(
                func=request_repair,
                name="request_query_repair",
                description=(
                    "Finish the review with APPROVE or FAILED, or request one Query Programmer "
                    "repair using REVISE. Use only after inspecting tool results."
                ),
                args_schema=RepairRequestInput,
            ),
        ]

    def _prompt(self) -> str:
        from importlib.resources import files as resource_files

        return resource_files("peopleops_api.resources.prompts").joinpath(
            "senior-reviewer.md"
        ).read_text(encoding="utf-8")

    def run(
        self,
        *,
        question: str,
        semantic_request: dict[str, Any],
        plan: AnalysisPlan,
        temporal_context: dict[str, Any] | None = None,
        previous_feedback: list[str] | None = None,
        review_cycle: int = 1,
    ) -> tuple[SeniorReview, dict[str, Any]]:
        semantic = SemanticRequest.model_validate(semantic_request)
        validated_cache: dict[int, dict[str, Any]] = {}
        tools = self._tools(validated_cache, semantic, plan)
        max_tool_calls_per_round = len(tools)
        max_tool_calls = max_tool_calls_per_round * self.max_rounds
        tool_map = {tool.name: tool for tool in tools}
        try:
            bound = self.model.bind_tools(tools, tool_choice="required", parallel_tool_calls=False)
        except TypeError:
            bound = self.model.bind_tools(tools, tool_choice="required")
        messages: list[BaseMessage] = [
            SystemMessage(content=self._prompt()),
            HumanMessage(content=_dump({
                "question": question,
                "semantic_request": semantic_request,
                "plan": plan.model_dump(mode="json"),
                "catalog_available": self.catalog is not None,
                "temporal_context": temporal_context or {},
                "previous_feedback": previous_feedback or [],
                "review_cycle": review_cycle,
            })),
        ]
        state: SeniorReviewerState = {
            "messages": messages,
            "model_rounds": 0,
            "tool_calls": 0,
            "model_events": [],
            "tool_events": [],
            "validations": {},
            "executions": {},
            "semantic_coverage": None,
            "decision": None,
        }

        def review_model(current: SeniorReviewerState) -> dict[str, Any]:
            round_number = current.get("model_rounds", 0) + 1
            response: AIMessage = bound.invoke(current["messages"])
            model_events = [*current.get("model_events", []), {
                "round": round_number,
                "request_messages": [_message_json(item) for item in current["messages"]],
                "response_message": _message_json(response),
            }]
            return {"messages": [response], "model_rounds": round_number, "model_events": model_events}

        def after_model(current: SeniorReviewerState) -> str:
            return "end" if current.get("decision") else "tools"

        def tool_executor(current: SeniorReviewerState) -> dict[str, Any]:
            calls = list(getattr(current["messages"][-1], "tool_calls", []) or [])
            tool_events = list(current.get("tool_events", []))
            responses: list[ToolMessage] = []
            validations = dict(current.get("validations", {}))
            executions = dict(current.get("executions", {}))
            semantic_coverage = current.get("semantic_coverage")
            decision = current.get("decision")
            repair_requested = False
            round_keys: set[str] = set()
            if len(calls) > max_tool_calls_per_round or current.get("tool_calls", 0) + len(calls) > max_tool_calls:
                reason = (
                    "TOOL_CALL_BATCH_LIMIT_EXCEEDED"
                    if len(calls) > max_tool_calls_per_round
                    else "TOOL_CALL_BUDGET_EXHAUSTED"
                )
                for call in calls:
                    args = call.get("args") or {}
                    result = {"accepted": False, "executed": False, "errors": [reason]}
                    tool_events.append({"round": current.get("model_rounds", 0), "tool": call.get("name"), "input": args, "output": result})
                    responses.append(ToolMessage(content=_dump(result), tool_call_id=call["id"]))
                return {
                    "messages": responses,
                    "tool_calls": current.get("tool_calls", 0) + len(calls),
                    "tool_events": tool_events,
                    "validations": validations,
                    "executions": executions,
                    "decision": decision,
                    "termination_reason": reason,
                }
            for call in calls:
                name = call.get("name")
                args = call.get("args") or {}
                call_key = f"{name}:{_dump(args)}"
                index = args.get("query_index") if isinstance(args, dict) else None
                if call_key in round_keys:
                    result = {"accepted": False, "duplicate_call": True, "reason": "DUPLICATE_TOOL_CALL_IN_SAME_RESPONSE"}
                elif name == "execute_conceptual_query" and index is not None and not validations.get(int(index), {}).get("valid"):
                    result = {
                        "query_index": int(index),
                        "executed": False,
                        "errors": ["QUERY_MUST_BE_VALIDATED_BY_SENIOR_REVIEWER_FIRST"],
                    }
                elif name == "execute_conceptual_query" and index is not None:
                    fingerprint = _query_fingerprint(args.get("query") or {})
                    prior = executions.get(int(index), {})
                    if prior.get("executed") and prior.get("query_fingerprint") == fingerprint:
                        result = {
                            "query_index": int(index),
                            "executed": False,
                            "duplicate_call": True,
                            "errors": ["DUPLICATE_QUERY_EXECUTION_IN_REVIEW_CYCLE"],
                        }
                    else:
                        result = tool_map[name].invoke(args)
                elif name == "request_query_repair":
                    requested_status = args.get("status")
                    required = set(range(len(plan.queries)))
                    validated = {idx for idx, payload in validations.items() if payload.get("valid")}
                    executed = {idx for idx, payload in executions.items() if payload.get("executed")}
                    if (
                        requested_status == "APPROVE"
                        and semantic.operational_conditions
                        and (semantic_coverage or {}).get("status") != "COMPLETE"
                    ):
                        result = {
                            "submitted": False,
                            "errors": ["SEMANTIC_COVERAGE_MUST_BE_COMPLETE_BEFORE_APPROVE"],
                            "semantic_coverage": semantic_coverage,
                        }
                    elif requested_status == "APPROVE" and required - validated:
                        result = {"submitted": False, "errors": ["ALL_QUERIES_MUST_BE_VALIDATED_BEFORE_SUBMIT", f"missing_query_indexes={sorted(required - validated)}"]}
                    elif requested_status == "APPROVE" and required - executed:
                        result = {"submitted": False, "errors": ["ALL_QUERIES_MUST_BE_EXECUTED_BEFORE_SUBMIT", f"missing_query_indexes={sorted(required - executed)}"]}
                    else:
                        result = tool_map[name].invoke(args)
                elif name not in tool_map:
                    result = {"submitted": False, "errors": [f"UNKNOWN_TOOL: {name}"]}
                else:
                    result = tool_map[name].invoke(args)
                index = result.get("query_index") if isinstance(result, dict) else index
                if name == "validate_conceptual_query" and index is not None:
                    validations[int(index)] = result
                if name == "execute_conceptual_query" and index is not None:
                    if result.get("executed"):
                        executions[int(index)] = result
                if name == "verify_semantic_coverage":
                    semantic_coverage = result
                if name == "request_query_repair" and result.get("submitted"):
                    decision = result["review"]
                    repair_requested = bool(result.get("repair_requested"))
                round_keys.add(call_key)
                tool_events.append({"round": current.get("model_rounds", 0), "tool": name, "input": args, "output": result})
                responses.append(ToolMessage(content=_dump(result), tool_call_id=call["id"]))
            return {
                "messages": responses,
                "tool_calls": current.get("tool_calls", 0) + len(calls),
                "tool_events": tool_events,
                "validations": validations,
                "executions": executions,
                "semantic_coverage": semantic_coverage,
                "decision": decision,
                "repair_requested": repair_requested,
            }

        def after_tools(current: SeniorReviewerState) -> str:
            return "end" if current.get("decision") or current.get("model_rounds", 0) >= self.max_rounds else "model"

        graph = StateGraph(SeniorReviewerState)
        graph.add_node("review_model", review_model)
        graph.add_node("tool_executor", tool_executor)
        graph.add_edge(START, "review_model")
        graph.add_conditional_edges("review_model", after_model, {"tools": "tool_executor", "end": END})
        graph.add_conditional_edges("tool_executor", after_tools, {"model": "review_model", "end": END})
        result = graph.compile().invoke(state)
        metadata = {
            "agent_id": "senior_reviewer",
            "model": self.model_name,
            "model_rounds": result.get("model_rounds", 0),
            "tool_calls": result.get("tool_calls", 0),
            "model_events": result.get("model_events", []),
            "tool_events": result.get("tool_events", []),
            "validations": result.get("validations", {}),
            "executions": result.get("executions", {}),
            "semantic_coverage": result.get("semantic_coverage"),
            "repair_requested": result.get("repair_requested", False),
            "model_decision": (result.get("decision") or {}).get("status"),
            "prompt_template": self._prompt(),
            "termination_reason": "SUBMISSION_ACCEPTED" if result.get("decision") else "SENIOR_REVIEW_DID_NOT_SUBMIT",
        }
        if not result.get("decision"):
            raise SeniorReviewerAgentError(metadata["termination_reason"], metadata)
        decision = SeniorReview.model_validate(result["decision"])
        if decision.status == "REVISE":
            decision = decision.model_copy(update={"status": "FAILED"})
        return decision, metadata


def _message_json(message: BaseMessage) -> dict[str, Any]:
    return {
        "type": message.type,
        "content": message.content,
        "tool_calls": getattr(message, "tool_calls", []),
        "tool_call_id": getattr(message, "tool_call_id", None),
    }

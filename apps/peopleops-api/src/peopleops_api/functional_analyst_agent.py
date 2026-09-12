"""Bounded tool-calling Functional Analyst for production-oriented analysis."""

from __future__ import annotations

import json
import os
from importlib.resources import files as resource_files
from typing import Any, Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field

from peopleops_api.analysis_contracts import SemanticRequest
from peopleops_api.hr_data_gateway import HRDataGateway
from peopleops_api.mcp_contracts import DiscoveryCatalog, DiscoveryEntity, SecurityContext
from peopleops_api.query_contracts import QueryFilter, QueryFilterGroup

MIN_FUNCTIONAL_ANALYST_ROUNDS = 4
FUNCTIONAL_ANALYST_EXTRA_SUBMISSION_ROUNDS = 6
MAX_FUNCTIONAL_ANALYST_ROUNDS = MIN_FUNCTIONAL_ANALYST_ROUNDS
MAX_FUNCTIONAL_ANALYST_TOOL_CALLS_PER_ROUND = 4  # compatibility alias; runtime derives len(tools)
MAX_FUNCTIONAL_ANALYST_TOOL_CALLS = 16

PROMPT = resource_files("peopleops_api.resources.prompts").joinpath(
    "functional-analyst-agent.md"
).read_text(encoding="utf-8")


class FunctionalAnalystAgentError(RuntimeError):
    def __init__(self, message: str, metadata: dict[str, Any]) -> None:
        super().__init__(message)
        self.metadata = metadata


class DiscoverScopedCatalogInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: list[str] = Field(default_factory=list, max_length=8)
    entities: list[str] = Field(default_factory=list, max_length=24)


class DiscoverCapabilitiesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DescribeEntityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1, max_length=128)


class SubmitSemanticRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_request: SemanticRequest


class FunctionalAnalystState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    model_rounds: int
    tool_calls: int
    discovered_catalog: dict[str, Any] | None
    model_events: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]
    semantic_request: dict[str, Any] | None
    termination_reason: str | None
    failed_tool_results: dict[str, dict[str, Any]]


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _is_retryable_tool_error(exc: Exception) -> bool:
    """Classify transport/provider failures without asking the model to guess."""
    name = type(exc).__name__.casefold()
    text = str(exc).casefold()
    return any(
        marker in name or marker in text
        for marker in (
            "timeout",
            "connection",
            "temporarily",
            "unavailable",
            "serviceunavailable",
            "rate limit",
        )
    )


def _round_budget_for_tool_count(tool_count: int, configured: int | None = None) -> int:
    return max(
        MIN_FUNCTIONAL_ANALYST_ROUNDS,
        configured
        if configured is not None
        else tool_count + FUNCTIONAL_ANALYST_EXTRA_SUBMISSION_ROUNDS,
    )


def _merge_described_entity(
    catalog: DiscoveryCatalog | None, entity: DiscoveryEntity
) -> DiscoveryCatalog:
    """Merge MCP entity introspection into the bounded catalog sent downstream."""
    if catalog is None:
        raise ValueError("describe_entity requires a scoped catalog first")
    entities = [item for item in catalog.entities if item.entity_id != entity.entity_id]
    entities.append(entity)
    return catalog.model_copy(update={"entities": entities})


def _semantic_submission_errors(
    semantic: SemanticRequest, catalog: DiscoveryCatalog | None = None
) -> list[str]:
    """Enforce the minimum hand-off contract for downstream planning.

    The analyst may use the model to interpret a request, but it must not submit
    a structured request that contains only routing metadata.  The downstream
    planner needs an explicit retrieval instruction, and a comparison needs an
    explicit comparison statement as well.  These checks are provider-neutral
    contract validation, not dataset-specific intent rules.
    """
    if semantic.needs_clarification or semantic.requires_policy or not semantic.requires_structured_data:
        return []

    errors: list[str] = []
    required_information = {
        item.strip().casefold() for item in semantic.required_information
    }
    if "database access" not in required_information:
        errors.append("required_information must include 'database access'")
    if not semantic.data_retrieval_request.strip():
        errors.append(
            "data_retrieval_request is required for structured data requests"
        )
    if not semantic.entities and not semantic.required_sources:
        errors.append(
            "entities must identify at least one catalog entity for structured data requests"
        )
    has_retrieval_detail = bool(
        semantic.measures
        or semantic.dimensions
        or semantic.filters
        or [
            item
            for item in required_information
            if item != "database access"
        ]
    )
    if not has_retrieval_detail:
        errors.append(
            "measures, dimensions, filters, or requested fields must identify the data required "
            "for structured data requests"
        )
    if catalog is not None:
        known_entities = {item.entity_id for item in catalog.entities}
        known_capabilities = {item.name for item in catalog.capabilities}
        known_fields = {
            f"{entity.entity_id}.{field.field_id}"
            for entity in catalog.entities
            for field in entity.fields
        }
        errors.extend(
            f"UNKNOWN_ENTITY: {entity}"
            for entity in semantic.entities
            if entity not in known_entities
        )
        errors.extend(
            f"UNKNOWN_SOURCE: {source}"
            for source in semantic.required_sources
            if source not in known_entities and source not in known_capabilities
        )
        for field_ref in _operational_condition_field_refs(semantic.operational_conditions):
            if "." not in field_ref:
                errors.append(f"UNQUALIFIED_FIELD: operational_conditions:{field_ref}")
            elif field_ref not in known_fields:
                errors.append(f"UNKNOWN_FIELD: operational_conditions:{field_ref}")
        errors.extend(
            _operational_condition_contradictions(semantic.operational_conditions)
        )
    has_multiple_periods = len(semantic.temporal_requirements) > 1
    has_comparison_intent = bool(semantic.comparison_requirements)
    if (has_multiple_periods or has_comparison_intent) and not has_comparison_intent:
        errors.append(
            "comparison_requirements is required when multiple periods are requested"
        )
    return errors


def _qualify_semantic_operational_conditions(
    semantic: SemanticRequest, catalog: DiscoveryCatalog | None
) -> SemanticRequest:
    if catalog is None or not semantic.operational_conditions:
        return semantic
    semantic_entity_scope = {
        item
        for item in [*semantic.entities, *semantic.required_sources]
        if item in {entity.entity_id for entity in catalog.entities}
    }
    matches: dict[str, list[str]] = {}
    scoped_matches: dict[str, list[str]] = {}
    for entity in catalog.entities:
        for field in entity.fields:
            reference = f"{entity.entity_id}.{field.field_id}"
            matches.setdefault(field.field_id, []).append(reference)
            if entity.entity_id in semantic_entity_scope:
                scoped_matches.setdefault(field.field_id, []).append(reference)

    def qualify(condition: QueryFilter | QueryFilterGroup) -> QueryFilter | QueryFilterGroup:
        if isinstance(condition, QueryFilter):
            if "." in condition.field:
                return condition
            candidates = scoped_matches.get(condition.field) or matches.get(condition.field, [])
            if len(candidates) != 1:
                return condition
            return condition.model_copy(update={"field": candidates[0]})
        return condition.model_copy(
            update={"conditions": [qualify(item) for item in condition.conditions]}
        )

    return semantic.model_copy(
        update={
            "operational_conditions": [
                qualify(condition) for condition in semantic.operational_conditions
            ]
        }
    )


def _infer_semantic_entities(
    semantic: SemanticRequest, catalog: DiscoveryCatalog | None
) -> SemanticRequest:
    """Complete omitted entity identifiers from already-grounded catalog refs."""

    if catalog is None or semantic.entities:
        return semantic
    known_entities = {item.entity_id for item in catalog.entities}
    inferred: list[str] = []
    for source in semantic.required_sources:
        if source in known_entities and source not in inferred:
            inferred.append(source)
    for field_ref in _operational_condition_field_refs(semantic.operational_conditions):
        if "." not in field_ref:
            continue
        entity_id = field_ref.split(".", 1)[0]
        if entity_id in known_entities and entity_id not in inferred:
            inferred.append(entity_id)
    if not inferred:
        return semantic
    return semantic.model_copy(update={"entities": inferred})


def _operational_condition_field_refs(
    conditions: list[QueryFilter | QueryFilterGroup],
) -> list[str]:
    refs: list[str] = []
    for condition in conditions:
        if isinstance(condition, QueryFilter):
            refs.append(condition.field)
        else:
            refs.extend(_operational_condition_field_refs(condition.conditions))
    return refs


def _operational_condition_contradictions(
    conditions: list[QueryFilter | QueryFilterGroup],
) -> list[str]:
    errors: list[str] = []
    filters_by_field: dict[str, list[QueryFilter]] = {}
    for condition in conditions:
        if isinstance(condition, QueryFilter):
            filters_by_field.setdefault(condition.field, []).append(condition)
        elif condition.operator == "and":
            errors.extend(_operational_condition_contradictions(condition.conditions))
    for field, field_conditions in filters_by_field.items():
        operators = {condition.operator for condition in field_conditions}
        if "is_null" in operators and len(operators - {"is_null"}) > 0:
            errors.append(
                "CONTRADICTORY_OPERATIONAL_CONDITIONS: "
                f"{field} is_null cannot be combined with another predicate using AND; "
                "use a grouped OR condition for alternatives"
            )
        if "is_null" in operators and "is_not_null" in operators:
            errors.append(
                f"CONTRADICTORY_OPERATIONAL_CONDITIONS: {field} is_null and is_not_null"
            )
    return errors


def _clarification_from_failed_submission(
    tool_events: list[dict[str, Any]],
    question: str,
) -> SemanticRequest | None:
    for event in reversed(tool_events):
        if event.get("tool") != "submit_semantic_request":
            continue
        output = event.get("output")
        if not isinstance(output, dict) or output.get("reason") != "INCOMPLETE_SEMANTIC_REQUEST":
            continue
        errors = [
            str(item)
            for item in output.get("errors", [])
            if isinstance(item, str) and item.strip()
        ]
        question_items = errors or [
            "The request could not be grounded in the available semantic catalog."
        ]
        return SemanticRequest(
            goal="Clarify the structured analysis request",
            original_user_request=question,
            clarified_request_english=question,
            needs_clarification=True,
            requires_structured_data=False,
            requires_catalog=False,
            required_information=[],
            questions_or_missing_information=question_items[:8],
        )
    return None


def _tool_error_code(output: dict[str, Any]) -> str:
    error = output.get("error")
    if isinstance(error, dict):
        code = str(error.get("code") or "").strip()
        message = str(error.get("message") or "").strip()
    else:
        code = ""
        message = str(error or "").strip()
    for candidate in (code, message, str(output.get("reason") or "")):
        if "AUTHORIZATION_DENIED" in candidate:
            return "AUTHORIZATION_DENIED"
        if "AUTHORIZATION_REQUIRED" in candidate:
            return "AUTHORIZATION_REQUIRED"
    return code


def _authorization_blocked_discovery(tool_events: list[dict[str, Any]]) -> bool:
    saw_authorization_denied = False
    for event in tool_events:
        if event.get("tool") != "discover_scoped_catalog":
            continue
        output = event.get("output")
        if not isinstance(output, dict):
            continue
        if _tool_error_code(output) == "AUTHORIZATION_DENIED":
            saw_authorization_denied = True
    return saw_authorization_denied


class FunctionalAnalystAgent:
    """A bounded LangGraph agent that discovers only the catalog it needs."""

    def __init__(
        self,
        *,
        gateway: HRDataGateway,
        security: SecurityContext,
        request_id: str,
        reference_context: dict[str, Any],
        model_name: str | None = None,
        api_key: str | None = None,
        max_retries: int = 2,
        max_rounds: int | None = None,
        max_tool_calls: int | None = None,
    ) -> None:
        from langchain_openai import ChatOpenAI

        self.gateway = gateway
        self.security = security
        self.request_id = request_id
        self.reference_context = reference_context
        self.max_rounds = max_rounds
        self.max_tool_calls = max_tool_calls
        self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.model = ChatOpenAI(
            model=self.model_name,
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            temperature=0,
            max_retries=max(0, min(max_retries, 6)),
        )

    def _system_prompt(self) -> str:
        from langchain_core.prompts import ChatPromptTemplate

        return ChatPromptTemplate.from_messages(
            [("system", PROMPT)], template_format="jinja2"
        ).format_messages(
            reference_context=_dump(self.reference_context),
        )[0].content

    def _tools(self) -> list[StructuredTool]:
        def capabilities() -> dict[str, Any]:
            return {
                "status": "success",
                "capabilities": [
                    item.model_dump(mode="json")
                    for item in self.gateway.discover_capabilities(
                        request_id=self.request_id, security=self.security
                    )
                ],
                "retryable": False,
                "error": None,
            }

        def discover(capabilities: list[str], entities: list[str]) -> dict[str, Any]:
            catalog = self.gateway.discover_scoped_catalog(
                capabilities=capabilities,
                entities=entities,
                request_id=self.request_id,
                security=self.security,
            )
            return {
                "status": "success" if catalog.entities else "insufficient_data",
                "catalog": catalog.model_dump(mode="json"),
                "retryable": False,
                "error": None,
            }

        def describe(entity_id: str) -> dict[str, Any]:
            entity = self.gateway.describe_entity(
                entity_id, request_id=self.request_id, security=self.security
            )
            return {
                "status": "success",
                "entity": entity.model_dump(mode="json"),
                "retryable": False,
                "error": None,
            }

        def submit(semantic_request: dict[str, Any]) -> dict[str, Any]:
            return {"submitted": True, "semantic_request": semantic_request}

        return [
            StructuredTool.from_function(
                func=capabilities,
                name="discover_capabilities",
                description=(
                    "List the available semantic business domains and their short descriptions. "
                    "Use this before selecting a scoped catalog for structured data."
                ),
                args_schema=DiscoverCapabilitiesInput,
            ),
            StructuredTool.from_function(
                func=discover,
                name="discover_scoped_catalog",
                description=(
                    "Discover a bounded semantic catalog by capability or entity. Use this for "
                    "structured HR data; never request the complete catalog."
                ),
                args_schema=DiscoverScopedCatalogInput,
            ),
            StructuredTool.from_function(
                func=describe,
                name="describe_entity",
                description="Get detailed semantic fields for one entity after choosing its domain.",
                args_schema=DescribeEntityInput,
            ),
            StructuredTool.from_function(
                func=submit,
                name="submit_semantic_request",
                description=(
                    "Submit the final SemanticRequest. Preserve the original question exactly, "
                    "and submit only after any required catalog discovery is complete."
                ),
                args_schema=SubmitSemanticRequestInput,
            ),
        ]

    def _build_subgraph(self) -> Any:
        tools = self._tools()
        max_tool_calls_per_round = len(tools)
        max_rounds = _round_budget_for_tool_count(len(tools), self.max_rounds)
        max_tool_calls = self.max_tool_calls or (max_tool_calls_per_round * max_rounds)
        tool_map = {tool.name: tool for tool in tools}
        try:
            bound = self.model.bind_tools(
                tools, tool_choice="required", parallel_tool_calls=False
            )
        except TypeError:
            bound = self.model.bind_tools(tools, tool_choice="required")

        def analyst_model(state: FunctionalAnalystState) -> dict[str, Any]:
            round_number = state.get("model_rounds", 0) + 1
            if round_number > max_rounds:
                return {"termination_reason": "FUNCTIONAL_ANALYST_ROUND_BUDGET_EXHAUSTED"}
            messages = list(state["messages"])
            model_events = list(state.get("model_events", []))
            try:
                response: AIMessage = bound.invoke(messages)
            except Exception as exc:  # noqa: BLE001 - preserve model failure evidence
                model_events.append({
                    "round": round_number,
                    "request_messages": [_message_json(item) for item in messages],
                    "response_message": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                })
                metadata = {
                    "agent_id": "functional_analyst",
                    "model": self.model_name,
                    "model_rounds": round_number,
                    "tool_calls": state.get("tool_calls", 0),
                    "termination_reason": "FUNCTIONAL_ANALYST_MODEL_CALL_FAILED",
                    "prompt_template": PROMPT,
                    "rendered_system_prompt": self._system_prompt(),
                    "model_events": model_events,
                    "tool_events": list(state.get("tool_events", [])),
                    "catalog": state.get("discovered_catalog"),
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
                raise FunctionalAnalystAgentError(
                    "Functional Analyst model call failed", metadata
                ) from exc
            model_events.append({
                "round": round_number,
                "request_messages": [_message_json(item) for item in messages],
                "response_message": _message_json(response),
            })
            return {"messages": [response], "model_rounds": round_number, "model_events": model_events}

        def route_after_model(state: FunctionalAnalystState) -> str:
            if state.get("termination_reason") or state.get("semantic_request") is not None:
                return "end"
            return "tools" if getattr(state["messages"][-1], "tool_calls", None) else "end"

        def execute_tools(state: FunctionalAnalystState) -> dict[str, Any]:
            message = state["messages"][-1]
            calls = list(getattr(message, "tool_calls", []) or [])
            if len(calls) > max_tool_calls_per_round:
                result = {
                    "submitted": False,
                    "reason": "FUNCTIONAL_ANALYST_TOOL_BATCH_LIMIT_EXCEEDED",
                }
                return {
                    "messages": [
                        ToolMessage(content=_dump(result), tool_call_id=call["id"])
                        for call in calls
                    ],
                    "tool_calls": state.get("tool_calls", 0) + len(calls),
                    "tool_events": [
                        *state.get("tool_events", []),
                        *[
                            {
                                "round": state["model_rounds"],
                                "tool": call.get("name"),
                                "input": call.get("args") or {},
                                "output": result,
                            }
                            for call in calls
                        ],
                    ],
                    "termination_reason": "FUNCTIONAL_ANALYST_TOOL_BATCH_LIMIT_EXCEEDED",
                }
            events = list(state.get("tool_events", []))
            responses: list[ToolMessage] = []
            catalog = state.get("discovered_catalog")
            semantic = state.get("semantic_request")
            catalog_available_before_round = catalog is not None
            total_calls = state.get("tool_calls", 0)
            failed_tool_results = dict(state.get("failed_tool_results", {}))
            termination_reason = state.get("termination_reason")
            round_results: dict[str, Any] = {}
            for call in calls:
                if total_calls >= max_tool_calls:
                    result = {
                        "submitted": False,
                        "reason": "FUNCTIONAL_ANALYST_TOOL_CALL_BUDGET_EXHAUSTED",
                    }
                    total_calls += 1
                    events.append({
                        "round": state["model_rounds"],
                        "tool": call.get("name"),
                        "input": call.get("args") or {},
                        "output": result,
                    })
                    responses.append(ToolMessage(content=_dump(result), tool_call_id=call["id"]))
                    continue
                name = call.get("name")
                args = call.get("args") or {}
                total_calls += 1
                call_key = f"{name}:{_dump(args)}"
                prior_failure = failed_tool_results.get(call_key)
                if prior_failure is not None:
                    prior_attempts = int(prior_failure.get("attempts", 1))
                    retryable = bool(prior_failure.get("retryable", False))
                    if not retryable or prior_attempts >= 2:
                        result = {
                            **prior_failure,
                            "retry_suppressed": True,
                            "executed": False,
                        }
                        events.append({
                            "round": state["model_rounds"],
                            "tool": name,
                            "input": args,
                            "output": result,
                        })
                        responses.append(ToolMessage(content=_dump(result), tool_call_id=call["id"]))
                        termination_reason = (
                            "FUNCTIONAL_ANALYST_TOOL_RETRY_EXHAUSTED"
                            if retryable
                            else "REPEATED_TOOL_FAILURE_NO_PROGRESS"
                        )
                        continue
                if call_key in round_results:
                    previous_result = round_results[call_key]
                    duplicate_result = (
                        dict(previous_result)
                        if isinstance(previous_result, dict)
                        else {"result": previous_result}
                    )
                    result = {
                        **duplicate_result,
                        "duplicate_call": True,
                        "executed": False,
                    }
                    events.append({
                        "round": state["model_rounds"],
                        "tool": name,
                        "input": args,
                        "output": result,
                    })
                    responses.append(ToolMessage(content=_dump(result), tool_call_id=call["id"]))
                    continue
                result: dict[str, Any]
                if name in tool_map:
                    try:
                        result = tool_map[name].invoke(args)
                        if name == "discover_scoped_catalog":
                            catalog_result = result.get("catalog", result)
                            catalog = catalog_result
                        elif name == "describe_entity":
                            entity_payload = result.get("entity")
                            if entity_payload is not None:
                                catalog = _merge_described_entity(
                                    DiscoveryCatalog.model_validate(catalog) if catalog else None,
                                    DiscoveryEntity.model_validate(entity_payload),
                                ).model_dump(mode="json")
                        if name == "submit_semantic_request":
                            proposed = SemanticRequest.model_validate(result["semantic_request"])
                            catalog_model = (
                                DiscoveryCatalog.model_validate(catalog) if catalog else None
                            )
                            if not proposed.entities and proposed.required_sources and catalog:
                                known_entities = {
                                    item["entity_id"]
                                    for item in catalog.get("entities", [])
                                    if isinstance(item, dict) and item.get("entity_id")
                                }
                                grounded_sources = [
                                    source
                                    for source in proposed.required_sources
                                    if source in known_entities
                                ]
                                if grounded_sources:
                                    proposed = proposed.model_copy(
                                        update={"entities": grounded_sources}
                                    )
                            proposed = _qualify_semantic_operational_conditions(
                                proposed, catalog_model
                            )
                            proposed = _infer_semantic_entities(proposed, catalog_model)
                            requires_discovery = (
                                proposed.requires_catalog or proposed.requires_structured_data
                            ) and not proposed.requires_policy and not proposed.needs_clarification
                            if requires_discovery and not catalog_available_before_round:
                                result = {
                                    "submitted": False,
                                    "reason": (
                                        "CATALOG_DISCOVERY_REQUIRED_BEFORE_SUBMISSION: use "
                                        "discover_scoped_catalog in an earlier model round"
                                    ),
                                }
                            elif (submission_errors := _semantic_submission_errors(
                                proposed,
                                catalog_model,
                            )):
                                result = {
                                    "submitted": False,
                                    "reason": "INCOMPLETE_SEMANTIC_REQUEST",
                                    "errors": submission_errors,
                                }
                            else:
                                semantic = proposed.model_dump(mode="json")
                                result = {"submitted": True, "semantic_request": semantic}
                    except Exception as exc:  # noqa: BLE001 - feedback belongs to the model
                        error_code = getattr(exc, "code", type(exc).__name__)
                        result = {
                            "status": "error",
                            "ok": False,
                            "retryable": _is_retryable_tool_error(exc),
                            "error": {
                                "code": error_code,
                                "message": str(exc),
                            },
                        }
                else:
                    result = {"ok": False, "error": f"UNKNOWN_TOOL: {name}"}
                if (
                    isinstance(result, dict)
                    and (result.get("ok") is False or result.get("submitted") is False)
                ):
                    failed_tool_results[call_key] = {
                        **dict(result),
                        "attempts": int(failed_tool_results.get(call_key, {}).get("attempts", 0)) + 1,
                    }
                round_results[call_key] = result
                events.append({"round": state["model_rounds"], "tool": name, "input": args, "output": result})
                responses.append(ToolMessage(content=_dump(result), tool_call_id=call["id"]))
            return {
                "messages": responses,
                "tool_calls": total_calls,
                "discovered_catalog": catalog,
                "semantic_request": semantic,
                "tool_events": events,
                "failed_tool_results": failed_tool_results,
                "termination_reason": termination_reason,
            }

        def route_after_tools(state: FunctionalAnalystState) -> str:
            return (
                "end"
                if state.get("semantic_request") is not None
                or state.get("termination_reason")
                or state.get("tool_calls", 0) >= max_tool_calls
                else "model"
            )

        builder = StateGraph(FunctionalAnalystState)
        builder.add_node("analyst_model", analyst_model)
        builder.add_node("tool_executor", execute_tools)
        builder.add_edge(START, "analyst_model")
        builder.add_conditional_edges("analyst_model", route_after_model, {"tools": "tool_executor", "end": END})
        builder.add_conditional_edges("tool_executor", route_after_tools, {"model": "analyst_model", "end": END})
        return builder.compile()

    def run(self, *, question: str) -> tuple[SemanticRequest, dict[str, Any]]:
        state: FunctionalAnalystState = {
            "messages": [
                SystemMessage(content=self._system_prompt()),
                HumanMessage(content=_dump({"question": question, "reference_context": self.reference_context})),
            ],
            "model_rounds": 0,
            "tool_calls": 0,
            "discovered_catalog": None,
            "model_events": [],
            "tool_events": [],
            "semantic_request": None,
            "termination_reason": None,
            "failed_tool_results": {},
        }
        result = self._build_subgraph().invoke(state)
        metadata = {
            "agent_id": "functional_analyst",
            "model": self.model_name,
            "model_rounds": result["model_rounds"],
            "tool_calls": result["tool_calls"],
            "termination_reason": result.get("termination_reason") or "ANALYST_DID_NOT_SUBMIT",
            "prompt_template": PROMPT,
            "rendered_system_prompt": self._system_prompt(),
            "model_events": result["model_events"],
            "tool_events": result["tool_events"],
            "catalog": result.get("discovered_catalog"),
        }
        if result.get("semantic_request") is None:
            if _authorization_blocked_discovery(result.get("tool_events", [])):
                metadata["termination_reason"] = "AUTHORIZATION_DENIED"
                raise FunctionalAnalystAgentError("AUTHORIZATION_DENIED", metadata)
            if clarification := _clarification_from_failed_submission(
                result.get("tool_events", []),
                question,
            ):
                metadata["termination_reason"] = "SUBMISSION_REJECTED_NEEDS_CLARIFICATION"
                return clarification, metadata
            raise FunctionalAnalystAgentError(metadata["termination_reason"], metadata)
        metadata["termination_reason"] = "SUBMISSION_ACCEPTED"
        return SemanticRequest.model_validate(result["semantic_request"]), metadata


def _message_json(message: BaseMessage) -> dict[str, Any]:
    return {
        "type": message.type,
        "content": message.content,
        "tool_calls": getattr(message, "tool_calls", []),
        "tool_call_id": getattr(message, "tool_call_id", None),
    }

"""Tool-calling Query Programmer for the production HR analysis workflow.

The model proposes provider-neutral ConceptualQuery objects.  The application
executes the validation tool through the real HRDataGateway, appends the
resulting ToolMessage, and lets the model repair or submit a plan.  This
module never executes a query and never exposes physical provider details.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
from importlib.resources import files as resource_files
from typing import Any, Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field

from peopleops_api.analysis_contracts import AnalysisPlan
from peopleops_api.hr_data_gateway import HRDataGateway
from peopleops_api.mcp_contracts import DiscoveryCatalog, SecurityContext, TemporalContext


MAX_TOOL_ROUNDS = 6
MAX_TOOL_CALLS_PER_ROUND = 2  # compatibility alias; runtime derives len(tools)
MAX_TOOL_CALLS = 24  # compatibility default for callers that set an explicit budget

PROMPT = resource_files("peopleops_api.resources.prompts").joinpath(
    "query-programmer-agent.md"
).read_text(encoding="utf-8")


class QueryProgrammerAgentError(RuntimeError):
    def __init__(self, message: str, metadata: dict[str, Any]) -> None:
        super().__init__(message)
        self.metadata = metadata


class ValidateConceptualQueryInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    query: dict[str, Any] | None = Field(
        default=None,
        description="One complete provider-neutral ConceptualQuery object.",
    )


class SubmitAnalysisPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: AnalysisPlan


class QueryProgrammerState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    validated_query_hashes: dict[str, int]
    model_rounds: int
    tool_calls: int
    validation_calls: int
    model_events: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]
    final_plan: dict[str, Any] | None
    termination_reason: str | None
    last_invalid_query_hash: str | None
    repeated_invalid_query_count: int


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _query_hash(query: dict[str, Any]) -> str:
    # The validation tool may receive a query with omitted optional fields,
    # while the same query embedded in AnalysisPlan is normalized by Pydantic.
    # Hash the canonical contract representation so a valid query can be
    # submitted in the following model round.
    from peopleops_api.query_contracts import ConceptualQuery

    query = ConceptualQuery.model_validate(query).model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(query, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def _unwrap_query(query: dict[str, Any]) -> dict[str, Any]:
    """Accept a plan-item wrapper without weakening the query contract."""
    if "entities" not in query and isinstance(query.get("query"), dict):
        return query["query"]
    return query


def _validate_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    """Accept either tool-schema args or a direct ConceptualQuery payload."""

    accepted_input_fields = conceptual_query_fields | {"grouping_requirements", "ordering_requirements"}
    if "query" in args:
        return {"query": args["query"]}
    if any(field in args for field in accepted_input_fields):
        return {"query": {field: args[field] for field in accepted_input_fields if field in args}}
    return args


conceptual_query_fields = {
    "contract_version",
    "goal",
    "entities",
    "select",
    "metrics",
    "filters",
    "where",
    "relationships",
    "time_scope",
    "comparisons",
    "order_by",
    "dimensions",
    "limit",
}


_AGGREGATE_FIELD_RE = re.compile(
    r"^\s*(?P<function>count|sum|avg|min|max)\s*\(\s*(?P<field>[^()]+?)\s*\)\s*$",
    re.IGNORECASE,
)
_GROUPING_REQUIREMENT_RE = re.compile(
    r"^\s*(?P<part>year|month|day|weekday)\s*\(\s*(?P<field>[^()]+?)\s*\)\s*$",
    re.IGNORECASE,
)


def _normalize_query_payload(query: dict[str, Any], catalog: DiscoveryCatalog) -> dict[str, Any]:
    """Normalize equivalent model payload shapes without weakening MCP validation."""

    accepted_input_fields = conceptual_query_fields | {"grouping_requirements", "ordering_requirements"}
    query = {field: query[field] for field in accepted_input_fields if field in query}
    selected_entities = [str(item) for item in query.get("entities", [])]
    field_refs = {
        field.field_id: f"{entity.entity_id}.{field.field_id}"
        for entity in catalog.entities
        if entity.entity_id in selected_entities
        for field in entity.fields
    }

    def qualify(reference: Any) -> Any:
        if not isinstance(reference, str) or "." in reference:
            return reference
        return field_refs.get(reference, reference)

    def normalize_reference(reference: Any) -> Any:
        if not isinstance(reference, str):
            return reference
        match = _GROUPING_REQUIREMENT_RE.match(reference)
        if match:
            return f"{match.group('part').lower()}({qualify(match.group('field'))})"
        return qualify(reference)

    def compact_same_field_equalities(node: Any) -> Any:
        if not isinstance(node, dict):
            return node
        if "conditions" not in node or node.get("operator") != "and":
            return node
        conditions = node.get("conditions")
        if not isinstance(conditions, list) or len(conditions) < 2:
            return node
        if not all(isinstance(item, dict) and "field" in item for item in conditions):
            return node
        fields = {item.get("field") for item in conditions}
        operators = {item.get("operator") for item in conditions}
        if len(fields) == 1 and operators == {"eq"}:
            values = [item.get("value") for item in conditions]
            if all(value is not None for value in values):
                return {"field": conditions[0]["field"], "operator": "in", "value": values}
        return node

    def normalize_filter_tree(node: Any) -> Any:
        if not isinstance(node, dict):
            return node
        if "field" in node:
            return {**node, "field": qualify(node.get("field"))}
        if "conditions" in node and isinstance(node["conditions"], list):
            return compact_same_field_equalities({
                **node,
                "conditions": [normalize_filter_tree(item) for item in node["conditions"]],
            })
        return node

    normalized = dict(query)
    normalized["select"] = [
        {**item, "field": qualify(item.get("field"))}
        for item in normalized.get("select", [])
        if isinstance(item, dict)
    ]
    normalized["filters"] = [
        {**item, "field": qualify(item.get("field"))}
        for item in normalized.get("filters", [])
        if isinstance(item, dict)
    ]
    if normalized.get("where") is not None:
        normalized["where"] = normalize_filter_tree(normalized["where"])
    if normalized.get("time_scope") and isinstance(normalized["time_scope"], dict):
        normalized["time_scope"] = {
            **normalized["time_scope"],
            "field": qualify(normalized["time_scope"].get("field")),
        }
    dimensions = [
        normalize_reference(item) for item in normalized.get("dimensions", []) if isinstance(item, str)
    ]
    selected_fields = {
        item.get("field")
        for item in normalized.get("select", [])
        if isinstance(item, dict) and isinstance(item.get("field"), str)
    }
    for item in normalized.pop("grouping_requirements", []) or []:
        if isinstance(item, str):
            reference = normalize_reference(item)
            if reference not in dimensions and reference not in selected_fields:
                dimensions.append(reference)
    normalized["dimensions"] = dimensions
    normalized["order_by"] = [
        {**item, "reference": normalize_reference(item.get("reference"))}
        for item in normalized.get("order_by", [])
        if isinstance(item, dict)
    ]
    for item in normalized.pop("ordering_requirements", []) or []:
        if isinstance(item, str):
            reference = normalize_reference(item)
            if reference in normalized["dimensions"] and not any(
                order.get("reference") == reference for order in normalized["order_by"]
            ):
                normalized["order_by"].append({"reference": reference, "direction": "asc"})
    dimension_by_base_field = {
        (_GROUPING_REQUIREMENT_RE.match(item).group("field")): item
        for item in normalized["dimensions"]
        if isinstance(item, str) and _GROUPING_REQUIREMENT_RE.match(item)
    }
    normalized["order_by"] = [
        {
            **item,
            "reference": dimension_by_base_field.get(item.get("reference"), item.get("reference")),
        }
        for item in normalized["order_by"]
    ]
    unique_order_by = []
    seen_order_by: set[tuple[Any, Any]] = set()
    for item in normalized["order_by"]:
        key = (item.get("reference"), item.get("direction", "asc"))
        if key in seen_order_by:
            continue
        seen_order_by.add(key)
        unique_order_by.append(item)
    normalized["order_by"] = unique_order_by

    metrics = []
    for item in normalized.get("metrics", []):
        if not isinstance(item, dict):
            continue
        metric = dict(item)
        field = metric.get("field")
        if isinstance(field, str):
            match = _AGGREGATE_FIELD_RE.match(field)
            if match:
                metric["function"] = match.group("function").lower()
                metric["field"] = match.group("field")
            metric["field"] = qualify(metric.get("field"))
        metrics.append(metric)
    normalized["metrics"] = metrics
    return normalized


def _normalize_plan_payload(payload: dict[str, Any], catalog: DiscoveryCatalog) -> dict[str, Any]:
    plan = dict(payload)
    queries = []
    for item in plan.get("queries", []):
        if not isinstance(item, dict):
            queries.append(item)
            continue
        query = item.get("query")
        if isinstance(query, dict):
            queries.append({**item, "query": _normalize_query_payload(query, catalog)})
        else:
            queries.append(item)
    plan["queries"] = queries
    return plan


class QueryProgrammerAgent:
    """Bounded LangChain tool-calling agent that validates ConceptualQuery through MCP."""

    def __init__(
        self,
        *,
        gateway: HRDataGateway,
        security: SecurityContext,
        request_id: str,
        catalog: DiscoveryCatalog,
        temporal_context: TemporalContext | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        max_retries: int = 2,
        max_rounds: int = MAX_TOOL_ROUNDS,
        max_tool_calls: int | None = None,
    ) -> None:
        from langchain_openai import ChatOpenAI

        self.gateway = gateway
        self.security = security
        self.request_id = request_id
        self.catalog = catalog
        self.temporal_context = temporal_context
        self.max_rounds = max(1, max_rounds)
        self.max_tool_calls = max_tool_calls
        self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.model = ChatOpenAI(
            model=self.model_name,
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            temperature=0,
            max_retries=max(0, min(max_retries, 6)),
        )

    def _validate_tool(self) -> StructuredTool:
        def validate(query: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
            from peopleops_api.query_contracts import ConceptualQuery

            try:
                payload = query if query is not None else extra
                candidate = ConceptualQuery.model_validate(
                    _normalize_query_payload(_unwrap_query(payload), self.catalog)
                )
            except Exception as exc:  # noqa: BLE001 - returned as tool feedback
                return {"valid": False, "errors": [f"INVALID_CONCEPTUAL_QUERY: {exc}"]}
            result = self.gateway.validate_query(
                candidate, request_id=self.request_id, security=self.security
            )
            payload = {"valid": result.valid, **result.model_dump(mode="json")}
            if result.valid:
                payload["next_action"] = (
                    "This query is valid. Do not validate it again; call "
                    "submit_analysis_plan with the complete plan in the next model turn."
                )
            return payload

        return StructuredTool.from_function(
            func=validate,
            name="validate_conceptual_query",
            description=(
                "Validate one ConceptualQuery through the MCP provider. This is a read-only "
                "validation tool; it does not execute the query. Repair the candidate when invalid."
            ),
            args_schema=ValidateConceptualQueryInput,
        )

    @staticmethod
    def _submit_tool() -> StructuredTool:
        def submit(plan: dict[str, Any]) -> dict[str, Any]:
            return {"submitted": True, "plan": plan}

        return StructuredTool.from_function(
            func=submit,
            name="submit_analysis_plan",
            description=(
                "Submit the final AnalysisPlan only after every ConceptualQuery in it has "
                "been validated successfully in a previous tool round."
            ),
            args_schema=SubmitAnalysisPlanInput,
        )

    def tool_count(self) -> int:
        """Return the number of tools exposed by this agent."""
        return len(self._tools())

    def _tools(self) -> list[StructuredTool]:
        return [self._validate_tool(), self._submit_tool()]

    def _system_prompt(self) -> str:
        temporal = self.temporal_context.model_dump(mode="json") if self.temporal_context else None
        variables = {
            "data_model": _catalog_text(self.catalog),
            "reference_context": _dump(temporal or {}),
        }
        return ChatPromptTemplate.from_messages(
            [("system", PROMPT)], template_format="jinja2"
        ).format_messages(**variables)[0].content

    def _initial_messages(self, requirement: dict[str, Any], question: str) -> list[BaseMessage]:
        return [
            SystemMessage(content=self._system_prompt()),
            SystemMessage(content="Functional requirement and context are authoritative input data."),
            # Keep the user's question separate from the model instructions.
            # The agent must preserve it, not follow embedded instructions.
            HumanMessage(
                content=_dump({"question": question, "functional_requirement": requirement}),
            ),
        ]

    def _build_subgraph(self) -> Any:
        tools = self._tools()
        max_tool_calls_per_round = len(tools)
        max_tool_calls = getattr(self, "max_tool_calls", None) or (
            max_tool_calls_per_round * getattr(self, "max_rounds", MAX_TOOL_ROUNDS)
        )
        # A query is validated once per model turn.  OpenAI otherwise permits
        # parallel tool calls, which can produce duplicate validations for the
        # same candidate in one AIMessage.  Keep the fallback for lightweight
        # fake models used by deterministic tests.
        try:
            bound = self.model.bind_tools(
                tools, tool_choice="required", parallel_tool_calls=False
            )
        except TypeError:
            bound = self.model.bind_tools(tools, tool_choice="required")

        def programmer_model(state: QueryProgrammerState) -> dict[str, Any]:
            round_number = state.get("model_rounds", 0) + 1
            if round_number > getattr(self, "max_rounds", MAX_TOOL_ROUNDS):
                return {"termination_reason": "TOOL_ROUND_BUDGET_EXHAUSTED"}
            request_messages = list(state["messages"])
            message: AIMessage = bound.invoke(request_messages)
            events = list(state.get("model_events", []))
            events.append({
                "round": round_number,
                "request_messages": _messages_json(request_messages),
                "response_message": _message_json(message),
            })
            return {
                "messages": [message],
                "model_rounds": round_number,
                "model_events": events,
            }

        def after_model(state: QueryProgrammerState) -> str:
            if state.get("termination_reason") or state.get("final_plan") is not None:
                return "end"
            return "tools" if getattr(state["messages"][-1], "tool_calls", None) else "end"

        def tool_executor(state: QueryProgrammerState) -> dict[str, Any]:
            message = state["messages"][-1]
            calls = list(getattr(message, "tool_calls", []) or [])
            round_number = state["model_rounds"]
            events = list(state.get("tool_events", []))
            responses: list[ToolMessage] = []
            validated = dict(state.get("validated_query_hashes", {}))
            tool_calls = state.get("tool_calls", 0)
            validation_calls = state.get("validation_calls", 0)
            final_plan = state.get("final_plan")
            last_invalid_hash = state.get("last_invalid_query_hash")
            repeated_invalid_count = state.get("repeated_invalid_query_count", 0)
            termination_reason = state.get("termination_reason")
            round_results: dict[str, dict[str, Any]] = {}

            if tool_calls >= max_tool_calls:
                result = {"accepted": False, "reason": "TOOL_CALL_BUDGET_EXHAUSTED"}
                for call in calls:
                    events.append({
                        "round": round_number,
                        "tool": call.get("name"),
                        "input": call.get("args") or {},
                        "output": result,
                    })
                    responses.append(ToolMessage(content=_dump(result), tool_call_id=call["id"]))
                return {
                    "messages": responses,
                    "tool_events": events,
                    "tool_calls": tool_calls + len(calls),
                    "validation_calls": validation_calls,
                    "termination_reason": "TOOL_CALL_BUDGET_EXHAUSTED",
                }

            if len(calls) > max_tool_calls_per_round:
                result = {"accepted": False, "reason": "TOOL_CALL_BATCH_LIMIT_EXCEEDED"}
                for call in calls:
                    events.append({
                        "round": round_number,
                        "tool": call.get("name"),
                        "input": call.get("args") or {},
                        "output": result,
                    })
                    responses.append(ToolMessage(content=_dump(result), tool_call_id=call["id"]))
                return {
                    "messages": responses,
                    "tool_events": events,
                    "tool_calls": tool_calls + len(calls),
                    "validation_calls": validation_calls,
                    "termination_reason": "TOOL_CALL_BATCH_LIMIT_EXCEEDED",
                }

            # Process every call in this AIMessage before routing. This is
            # required by the tool-calling protocol even when one call causes
            # a terminal condition.
            for call in calls:
                if tool_calls >= max_tool_calls:
                    result = {"accepted": False, "reason": "TOOL_CALL_BUDGET_EXHAUSTED"}
                    tool_calls += 1
                    termination_reason = "TOOL_CALL_BUDGET_EXHAUSTED"
                    events.append({
                        "round": round_number,
                        "tool": call.get("name"),
                        "input": call.get("args") or {},
                        "output": result,
                    })
                    responses.append(ToolMessage(content=_dump(result), tool_call_id=call["id"]))
                    continue
                name = call.get("name")
                args = call.get("args") or {}
                tool_calls += 1
                call_key = f"{name}:{_dump(args)}"
                if call_key in round_results:
                    result = {
                        **round_results[call_key],
                        "duplicate_call": True,
                        "executed": False,
                    }
                    if name == "validate_conceptual_query" and not result.get("valid"):
                        tool_args = _validate_tool_args(args)
                        query = _unwrap_query(tool_args.get("query", {}))
                        try:
                            candidate_hash = _query_hash(query)
                        except Exception:  # malformed candidates still need a stable loop key
                            candidate_hash = hashlib.sha256(_dump(query).encode()).hexdigest()
                        if candidate_hash == last_invalid_hash:
                            repeated_invalid_count += 1
                        else:
                            last_invalid_hash = candidate_hash
                            repeated_invalid_count = 1
                        if repeated_invalid_count >= 2:
                            termination_reason = "NO_PROGRESS_AFTER_REPEATED_INVALID_CANDIDATE"
                    events.append({
                        "round": round_number,
                        "tool": name,
                        "input": args,
                        "output": result,
                    })
                    responses.append(ToolMessage(content=_dump(result), tool_call_id=call["id"]))
                    continue
                if name == "validate_conceptual_query":
                    validation_calls += 1
                    tool_args = _validate_tool_args(args)
                    result = tools[0].invoke(tool_args)
                    query = _normalize_query_payload(
                        _unwrap_query(tool_args.get("query", {})), self.catalog
                    )
                    if result.get("valid"):
                        validated[_query_hash(query)] = round_number
                        last_invalid_hash = None
                        repeated_invalid_count = 0
                    else:
                        try:
                            candidate_hash = _query_hash(query)
                        except Exception:  # malformed candidates still need a stable loop key
                            candidate_hash = hashlib.sha256(_dump(query).encode()).hexdigest()
                        if candidate_hash == last_invalid_hash:
                            repeated_invalid_count += 1
                        else:
                            last_invalid_hash = candidate_hash
                            repeated_invalid_count = 1
                        if repeated_invalid_count >= 2:
                            termination_reason = "NO_PROGRESS_AFTER_REPEATED_INVALID_CANDIDATE"
                elif name == "submit_analysis_plan":
                    try:
                        submitted_payload = {
                            **args,
                            "plan": _normalize_plan_payload(args.get("plan", {}), self.catalog),
                        }
                        submitted = SubmitAnalysisPlanInput.model_validate(submitted_payload)
                        queries = [item.query.model_dump(mode="json") for item in submitted.plan.queries]
                        accepted = all(
                            validated.get(_query_hash(query), -1) < round_number
                            for query in queries
                        )
                        result = (
                            {"accepted": True, "plan": submitted.plan.model_dump(mode="json")}
                            if accepted
                            else {"accepted": False, "reason": "ALL_QUERIES_MUST_BE_VALIDATED_FIRST"}
                        )
                        if accepted:
                            final_plan = result["plan"]
                    except Exception as exc:  # noqa: BLE001 - returned as tool feedback
                        result = {"accepted": False, "reason": f"INVALID_SUBMISSION: {exc}"}
                else:
                    result = {"accepted": False, "reason": f"UNKNOWN_TOOL: {name}"}
                round_results[call_key] = result
                events.append({
                    "round": round_number,
                    "tool": name,
                    "input": args,
                    "output": result,
                })
                responses.append(ToolMessage(content=_dump(result), tool_call_id=call["id"]))
            return {
                "messages": responses,
                "validated_query_hashes": validated,
                "tool_calls": tool_calls,
                "validation_calls": validation_calls,
                "tool_events": events,
                "final_plan": final_plan,
                "last_invalid_query_hash": last_invalid_hash,
                "repeated_invalid_query_count": repeated_invalid_count,
                "termination_reason": termination_reason or (
                    "TOOL_CALL_BUDGET_EXHAUSTED"
                    if tool_calls >= max_tool_calls
                    else None
                ),
            }

        def after_tools(state: QueryProgrammerState) -> str:
            return (
                "end"
                if state.get("final_plan") is not None
                or state.get("termination_reason")
                or state.get("tool_calls", 0) >= max_tool_calls
                else "model"
            )

        builder = StateGraph(QueryProgrammerState)
        builder.add_node("programmer_model", programmer_model)
        builder.add_node("tool_executor", tool_executor)
        builder.add_edge(START, "programmer_model")
        builder.add_conditional_edges(
            "programmer_model", after_model, {"tools": "tool_executor", "end": END}
        )
        builder.add_conditional_edges(
            "tool_executor", after_tools, {"model": "programmer_model", "end": END}
        )
        return builder.compile()

    def run(self, *, requirement: dict[str, Any], question: str) -> tuple[AnalysisPlan, dict[str, Any]]:
        state: QueryProgrammerState = {
            "messages": self._initial_messages(requirement, question),
            "validated_query_hashes": {},
            "model_rounds": 0,
            "tool_calls": 0,
            "validation_calls": 0,
            "model_events": [],
            "tool_events": [],
            "final_plan": None,
            "termination_reason": None,
        }

        result_state = self._build_subgraph().invoke(state)

        metadata = {
            "agent_id": "query_programmer",
            "model": self.model_name,
            "model_rounds": result_state["model_rounds"],
            "tool_calls": result_state["tool_calls"],
            "validation_calls": result_state["validation_calls"],
            "termination_reason": result_state.get("termination_reason")
            or "QUERY_PROGRAMMER_DID_NOT_SUBMIT_A_PLAN",
            "prompt_template": PROMPT,
            "rendered_system_prompt": self._system_prompt(),
            "model_events": result_state["model_events"],
            "tool_events": result_state["tool_events"],
        }
        if result_state.get("final_plan") is None:
            fallback_plan = _fallback_plan_from_validated_queries(
                result_state["tool_events"], requirement, self.catalog
            )
            if fallback_plan is None:
                raise QueryProgrammerAgentError(metadata["termination_reason"], metadata)
            metadata["termination_reason"] = "AUTO_SUBMITTED_VALIDATED_QUERIES"
            return fallback_plan, metadata
        plan = AnalysisPlan.model_validate(result_state["final_plan"])
        metadata["termination_reason"] = "SUBMISSION_ACCEPTED"
        return plan, metadata


def _messages_json(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    return [_message_json(message) for message in messages]


def _fallback_plan_from_validated_queries(
    tool_events: list[dict[str, Any]],
    requirement: dict[str, Any],
    catalog: DiscoveryCatalog,
) -> AnalysisPlan | None:
    queries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in tool_events:
        if event.get("tool") != "validate_conceptual_query":
            continue
        output = event.get("output") if isinstance(event.get("output"), dict) else {}
        if not output.get("valid"):
            continue
        args = _validate_tool_args(event.get("input") or {})
        query = args.get("query")
        if not isinstance(query, dict):
            continue
        query = _normalize_query_payload(_unwrap_query(query), catalog)
        key = output.get("query_hash") or _dump(query)
        if key in seen:
            continue
        seen.add(key)
        queries.append(query)
    if not queries:
        return None
    semantic = requirement.get("semantic_request") if isinstance(requirement, dict) else {}
    if not isinstance(semantic, dict):
        semantic = {}
    goal = semantic.get("goal") or semantic.get("data_retrieval_request") or "Validated analysis plan"
    return AnalysisPlan.model_validate(
        {
            "goal": goal,
            "queries": [
                {
                    "purpose": semantic.get("data_retrieval_request")
                    or semantic.get("clarified_request_english")
                    or goal,
                    "query": query,
                }
                for query in queries
            ],
        }
    )


def _message_json(message: BaseMessage) -> dict[str, Any]:
    return {
        "type": message.type,
        "content": message.content,
        "tool_calls": getattr(message, "tool_calls", []),
        "tool_call_id": getattr(message, "tool_call_id", None),
    }


def _catalog_text(catalog: DiscoveryCatalog) -> str:
    return _dump({
        "capabilities": [item.model_dump(mode="json") for item in catalog.capabilities],
        "entities": [item.model_dump(mode="json") for item in catalog.entities],
        "relationships": [item.model_dump(mode="json") for item in catalog.relationships],
    })

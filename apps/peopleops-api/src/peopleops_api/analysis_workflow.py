"""Slice 06 structured HR analysis workflow.

The model proposes typed semantic artifacts; deterministic code validates,
executes, persists and merges evidence. No physical HRIS schema is used here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel
from sqlalchemy.orm import Session

from peopleops_api.analysis_contracts import (
    AnalysisPlan,
    SemanticRequest,
    StructuredAnswer,
)
from peopleops_api.audit import transition
from peopleops_api.hr_data_gateway import HRDataGateway
from peopleops_api.mcp_client import MCPClientError
from peopleops_api.mcp_contracts import DiscoveryCatalog, SecurityContext
from peopleops_api.models import AnalysisInteraction
from peopleops_api.query_contracts import QueryResult


class StructuredModel(Protocol):
    model_name: str

    def parse(
        self, *, purpose: str, instructions: str, output_model: type[BaseModel]
    ) -> BaseModel: ...


class OpenAIModelError(Exception):
    """Safe boundary error for unavailable or invalid model responses."""


class OpenAIStructuredModel:
    def __init__(self, *, api_key: str | None, model: str) -> None:
        self.model_name = model
        if not api_key:
            self._client = None
            return
        try:
            from openai import OpenAI

            self._client = OpenAI(api_key=api_key)
        except Exception as exc:  # provider initialization boundary
            raise OpenAIModelError("OpenAI could not be initialized") from exc

    def parse(self, *, purpose: str, instructions: str, output_model: type[BaseModel]) -> BaseModel:
        if self._client is None:
            raise OpenAIModelError("OpenAI is not configured")
        try:
            response = self._client.responses.parse(
                model=self.model_name,
                input=[
                    {"role": "system", "content": purpose},
                    {"role": "user", "content": instructions},
                ],
                text_format=output_model,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise OpenAIModelError("OpenAI returned no structured output")
            return parsed
        except OpenAIModelError:
            raise
        except Exception as exc:  # normalize provider details, never persist them
            raise OpenAIModelError("OpenAI structured output failed") from exc


class AnalysisState(TypedDict, total=False):
    interaction: AnalysisInteraction
    question: str
    semantic_request: SemanticRequest
    catalog: DiscoveryCatalog
    plan: AnalysisPlan
    results: list[QueryResult]
    evidence: list[dict[str, Any]]
    response: StructuredAnswer
    replan_count: int
    query_errors: list[str]


@dataclass
class AnalysisWorkflow:
    session: Session
    gateway: HRDataGateway
    model: StructuredModel
    security: SecurityContext
    max_replans: int = 1

    def run(self, interaction: AnalysisInteraction) -> AnalysisInteraction:
        graph = self._build_graph()
        started = monotonic()
        interaction.model_name = self.model.model_name
        transition(self.session, interaction, stage="workflow", status="running")
        self.session.commit()
        try:
            result = graph.invoke(
                {
                    "interaction": interaction,
                    "question": interaction.question,
                    "replan_count": 0,
                    "results": [],
                }
            )
            interaction.latency_ms = round((monotonic() - started) * 1000)
            interaction.completed_at = datetime.now(UTC)
            self.session.add(interaction)
            self.session.commit()
            return result["interaction"]
        except MCPClientError as exc:
            return self._fail(interaction, exc.code, self._safe_error(exc))
        except OpenAIModelError as exc:
            return self._fail(interaction, "MODEL_ERROR", str(exc))
        except Exception:  # noqa: BLE001 - normalize unexpected workflow boundary failures
            return self._fail(interaction, "SYSTEM_ERROR", "analysis workflow failed")

    def _build_graph(self):
        builder = StateGraph(AnalysisState)
        builder.add_node("understand_request", self._understand_request)
        builder.add_node("discover_catalog", self._discover_catalog)
        builder.add_node("plan_queries", self._plan_queries)
        builder.add_node("execute_queries", self._execute_queries)
        builder.add_node("merge_evidence", self._merge_evidence)
        builder.add_node("synthesize", self._synthesize)
        builder.add_edge(START, "understand_request")
        builder.add_edge("understand_request", "discover_catalog")
        builder.add_edge("discover_catalog", "plan_queries")
        builder.add_edge("plan_queries", "execute_queries")
        builder.add_conditional_edges(
            "execute_queries",
            self._after_execution,
            {"replan": "plan_queries", "merge": "merge_evidence"},
        )
        builder.add_edge("merge_evidence", "synthesize")
        builder.add_edge("synthesize", END)
        return builder.compile()

    def _understand_request(self, state: AnalysisState) -> dict[str, Any]:
        self._stage(state, "understanding", "running")
        semantic = self.model.parse(
            purpose=(
                "Interpret the HR question into the provided typed schema. Select only capabilities "
                "and entities present in the supplied catalog. Do not invent facts or SQL."
            ),
            instructions=f"Question: {state['question']}",
            output_model=SemanticRequest,
        )
        assert isinstance(semantic, SemanticRequest)
        interaction = state["interaction"]
        self._stage(
            state,
            "understanding",
            "completed",
            snapshots={
                "semantic_request": semantic.model_dump(mode="json"),
                "analysis_goal": semantic.goal,
            },
        )
        return {"semantic_request": semantic, "interaction": interaction}

    def _discover_catalog(self, state: AnalysisState) -> dict[str, Any]:
        self._stage(state, "discovery", "running")
        catalog = self.gateway.discover_catalog(
            request_id=str(state["interaction"].request_id), security=self.security
        )
        self._stage(
            state,
            "discovery",
            "completed",
            snapshots={
                "provider_type": catalog.provider_type,
                "provider_catalog_version": catalog.catalog_version,
            },
        )
        return {"catalog": catalog, "interaction": state["interaction"]}

    def _plan_queries(self, state: AnalysisState) -> dict[str, Any]:
        self._stage(state, "planning", "running")
        feedback = "; ".join(state.get("query_errors", []))
        plan = self.model.parse(
            purpose=(
                "Create a bounded plan of provider-neutral conceptual queries. Use semantic IDs from "
                "the catalog only; select capabilities dynamically; never output physical SQL."
            ),
            instructions=(
                f"Semantic request: {state['semantic_request'].model_dump_json()}\n"
                f"Catalog metadata: {state['catalog'].model_dump_json()}\n"
                f"Previous validation feedback (if any): {feedback or 'none'}"
            ),
            output_model=AnalysisPlan,
        )
        assert isinstance(plan, AnalysisPlan)
        self._stage(
            state, "planning", "completed", snapshots={"query_plan": plan.model_dump(mode="json")}
        )
        return {"plan": plan, "interaction": state["interaction"], "query_errors": []}

    def _execute_queries(self, state: AnalysisState) -> dict[str, Any]:
        self._stage(state, "query_execution", "running")
        results: list[tuple[Any, QueryResult]] = []
        errors: list[str] = []
        for planned in state["plan"].queries:
            validation = self.gateway.validate_query(
                planned.query,
                request_id=str(state["interaction"].request_id),
                security=self.security,
            )
            if not validation.valid:
                errors.extend(validation.errors)
                continue
            results.append(
                (
                    planned,
                    self.gateway.execute_query(
                        planned.query,
                        request_id=str(state["interaction"].request_id),
                        security=self.security,
                    ),
                )
            )
        if errors:
            self._stage(
                state,
                "query_execution",
                "validation_failed",
                snapshots={"validation": {"errors": errors}},
            )
        else:
            self._stage(state, "query_execution", "completed")
        return {
            "results": results,
            "query_errors": errors,
            "replan_count": state.get("replan_count", 0),
            "interaction": state["interaction"],
        }

    def _after_execution(self, state: AnalysisState) -> str:
        if state.get("query_errors") and state.get("replan_count", 0) < self.max_replans:
            state["replan_count"] = state.get("replan_count", 0) + 1
            return "replan"
        return "merge"

    def _merge_evidence(self, state: AnalysisState) -> dict[str, Any]:
        self._stage(state, "evidence_merge", "running")
        evidence = [
            {
                "type": "structured_data",
                "purpose": planned.purpose,
                "query": planned.query.model_dump(mode="json"),
                "result": result.model_dump(mode="json"),
            }
            for planned, result in state.get("results", [])
        ]
        self._stage(state, "evidence_merge", "completed", snapshots={"evidence": evidence})
        return {"evidence": evidence, "interaction": state["interaction"]}

    def _synthesize(self, state: AnalysisState) -> dict[str, Any]:
        evidence = state.get("evidence", [])
        if not any(item["result"].get("rows") for item in evidence):
            response = StructuredAnswer(
                answer="No sufficient structured HR data was returned for this question.",
                warnings=["The requested analysis has insufficient data."],
            )
            self._stage(
                state,
                "synthesis",
                "insufficient_data",
                snapshots={
                    "response": response.model_dump(mode="json"),
                    "warnings": response.warnings,
                },
            )
            return {"response": response, "interaction": state["interaction"]}
        self._stage(state, "synthesis", "running")
        response = self.model.parse(
            purpose=(
                "Synthesize only a concise answer grounded in the structured evidence. Preserve numeric "
                "values exactly. Facts must be attributable to evidence; do not mention hidden reasoning."
            ),
            instructions=f"Question: {state['question']}\nEvidence: {evidence}",
            output_model=StructuredAnswer,
        )
        assert isinstance(response, StructuredAnswer)
        _assert_supported_numbers(response, evidence)
        self._stage(
            state,
            "synthesis",
            "completed",
            snapshots={"response": response.model_dump(mode="json")},
        )
        return {"response": response, "interaction": state["interaction"]}

    def _stage(
        self,
        state: AnalysisState,
        stage: str,
        status: str,
        *,
        snapshots: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        transition(
            self.session, state["interaction"], stage=stage, status=status, snapshots=snapshots
        )
        self.session.commit()

    def _fail(
        self, interaction: AnalysisInteraction, error_type: str, detail: str
    ) -> AnalysisInteraction:
        transition(
            self.session,
            interaction,
            stage=interaction.current_stage,
            status="failed",
            error_type=error_type,
            error_detail=detail,
        )
        interaction.completed_at = datetime.now(UTC)
        self.session.commit()
        return interaction

    @staticmethod
    def _safe_error(exc: MCPClientError) -> str:
        return (
            str(exc)
            if str(exc)
            in {
                "MCP provider timed out",
                "MCP provider is unavailable",
                "MCP provider rejected the request",
            }
            else "MCP provider request failed"
        )


def _assert_supported_numbers(response: StructuredAnswer, evidence: list[dict[str, Any]]) -> None:
    serialized = str(evidence)
    for text in [response.answer, *response.key_findings]:
        for number in re.findall(r"(?<![A-Za-z])[+-]?\d+(?:[.,]\d+)?", text):
            if number not in serialized and number.replace(",", ".") not in serialized:
                raise OpenAIModelError("structured response contained an unsupported numeric claim")

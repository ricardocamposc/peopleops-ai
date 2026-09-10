"""Phase 4.2 Query Programmer runtime with skill-specific prompts.

This keeps the Phase 4.2 graph, validator, state, repair budgets, Functional Analyst,
and Senior Reviewer unchanged. Only Query Programmer prompt selection changes:

- GENERATE for a fresh query;
- TECHNICAL_REPAIR for deterministic/internal technical failures;
- SEMANTIC_REPAIR for Senior-requested semantic revision.

The goal is to isolate whether skill-specific instructions improve reliability
without introducing a new phase or changing the surrounding workflow.
"""
from __future__ import annotations

import time
from contextvars import ContextVar
from importlib.resources import files as resource_files
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

import direct_sqlalchemy_phase42 as phase42


PHASE42_PROMPTS = resource_files("peopleops_api.resources.prompts.phase42")
QUERY_GENERATE_PROMPT = PHASE42_PROMPTS.joinpath(
    "sqlalchemy-query-programmer-generate.md"
).read_text(encoding="utf-8")
QUERY_TECHNICAL_REPAIR_PROMPT = PHASE42_PROMPTS.joinpath(
    "sqlalchemy-query-programmer-technical-repair.md"
).read_text(encoding="utf-8")
QUERY_SEMANTIC_REPAIR_PROMPT = PHASE42_PROMPTS.joinpath(
    "sqlalchemy-query-programmer-semantic-repair.md"
).read_text(encoding="utf-8")

QUERY_PROGRAMMER_SKILLS = {
    "GENERATE": {
        "prompt": QUERY_GENERATE_PROMPT,
        "prompt_id": "peopleops.sqlalchemy_query_developer.generate",
        "prompt_version": "v1-skill-generate",
    },
    "TECHNICAL_REPAIR": {
        "prompt": QUERY_TECHNICAL_REPAIR_PROMPT,
        "prompt_id": "peopleops.sqlalchemy_query_developer.technical_repair",
        "prompt_version": "v1-skill-technical-repair",
    },
    "SEMANTIC_REPAIR": {
        "prompt": QUERY_SEMANTIC_REPAIR_PROMPT,
        "prompt_id": "peopleops.sqlalchemy_query_developer.semantic_repair",
        "prompt_version": "v1-skill-semantic-repair",
    },
}

_QUERY_PROGRAMMER_INVOCATION_TRACE: ContextVar[list[dict[str, Any]] | None] = (
    ContextVar("phase42_query_programmer_invocation_trace", default=None)
)


def select_query_programmer_skill(repair_type: str | None) -> str:
    """Map a known workflow repair type to one focused Query Programmer skill."""
    if repair_type is None:
        return "GENERATE"
    if repair_type in {"TECHNICAL", "INTERNAL_SELF_REPAIR"}:
        return "TECHNICAL_REPAIR"
    if repair_type == "SEMANTIC":
        return "SEMANTIC_REPAIR"
    raise ValueError(f"Unsupported Query Programmer repair_type: {repair_type!r}")


def _skill_templates() -> dict[str, ChatPromptTemplate]:
    return {
        skill: ChatPromptTemplate.from_messages(
            [("system", spec["prompt"]), ("human", "{{user_input}}")],
            template_format="jinja2",
        )
        for skill, spec in QUERY_PROGRAMMER_SKILLS.items()
    }


def _relevant_input_artifacts(human_payload: dict[str, Any]) -> dict[str, Any]:
    """Keep the artifacts needed to explain/reproduce one programmer invocation."""
    keys = (
        "functional_requirement",
        "previous_query",
        "deterministic_validation_result",
        "senior_review",
        "internal_tool_results",
    )
    artifacts: dict[str, Any] = {}
    for key in keys:
        value = human_payload.get(key)
        if value not in (None, [], {}):
            artifacts[key] = value
    return artifacts


class SkillPromptRuntime(phase42.LangChainAgentRuntime):
    """Phase 4.2 runtime that treats Query Programmer tasks as separate skills."""

    model_name = "langchain-phase42-skill-prompts"

    def __init__(self, model_config: dict[str, str] | None = None) -> None:
        super().__init__(model_config)
        self.query_skill_templates = _skill_templates()

    def invoke(
        self, *, role: str, input_payload: dict[str, Any], output_model: type[BaseModel]
    ) -> tuple[BaseModel, dict[str, Any]]:
        if role != "sqlalchemy_query_developer":
            return super().invoke(
                role=role, input_payload=input_payload, output_model=output_model
            )

        skill = select_query_programmer_skill(input_payload.get("repair_type"))
        skill_spec = QUERY_PROGRAMMER_SKILLS[skill]
        template = self.query_skill_templates[skill]

        variables = phase42._chain_variables(input_payload)
        human_payload = phase42._human_payload(role, input_payload)
        variables["user_input"] = phase42._json(human_payload)
        rendered = template.format_messages(**variables)

        started = time.perf_counter()
        chain = template | self.models[role].with_structured_output(output_model)
        result = chain.invoke(variables)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        metadata = {
            "agent_id": role,
            "prompt": skill_spec["prompt"],
            "prompt_id": skill_spec["prompt_id"],
            "prompt_version": skill_spec["prompt_version"],
            "prompt_skill": skill,
            "model": self.model_config[role],
            "schema_version": output_model.__name__,
            "rendered_messages": [
                {"role": message.type, "content": message.content}
                for message in rendered
            ],
            "latency_ms": latency_ms,
            "rendered_system_prompt": rendered[0].content,
        }

        trace = _QUERY_PROGRAMMER_INVOCATION_TRACE.get()
        if trace is not None:
            trace.append(
                {
                    "sequence": len(trace) + 1,
                    "agent_id": role,
                    "skill": skill,
                    "prompt_id": skill_spec["prompt_id"],
                    "prompt_version": skill_spec["prompt_version"],
                    "model": self.model_config[role],
                    "schema_version": output_model.__name__,
                    "repair_type": input_payload.get("repair_type"),
                    "repair_attempt": input_payload.get("repair_attempt", 0),
                    "latency_ms": latency_ms,
                    "input_artifacts": _relevant_input_artifacts(human_payload),
                    "output_status": getattr(result, "status", None),
                }
            )

        # `prompt` intentionally overrides the legacy prompt argument recorded by
        # phase42._record so the audit artifact contains the actual skill prompt.
        return result, metadata

    def invoke_query_programmer(
        self, *, input_payload: dict[str, Any], output_model: type[BaseModel]
    ) -> tuple[BaseModel, dict[str, Any]]:
        """Run the inherited Phase 4.2 loop and retain metadata for every LLM call."""
        token = _QUERY_PROGRAMMER_INVOCATION_TRACE.set([])
        try:
            result, metadata = super().invoke_query_programmer(
                input_payload=input_payload,
                output_model=output_model,
            )
            invocation_trace = list(_QUERY_PROGRAMMER_INVOCATION_TRACE.get() or [])
        finally:
            _QUERY_PROGRAMMER_INVOCATION_TRACE.reset(token)

        enriched_iterations: list[dict[str, Any]] = []
        for index, iteration in enumerate(metadata.get("internal_iterations", [])):
            enriched = dict(iteration)
            if index < len(invocation_trace):
                invocation = invocation_trace[index]
                enriched.update(
                    {
                        "prompt_skill": invocation["skill"],
                        "prompt_id": invocation["prompt_id"],
                        "prompt_version": invocation["prompt_version"],
                        "model": invocation["model"],
                        "llm_latency_ms": invocation["latency_ms"],
                    }
                )
            enriched_iterations.append(enriched)

        return result, {
            **metadata,
            "query_programmer_invocation_count": len(invocation_trace),
            "query_programmer_invocations": invocation_trace,
            "internal_iterations": enriched_iterations,
        }


# Re-export the existing Phase 4.2 graph/state helpers. The graph calls the
# runtime polymorphically, so inherited workflow logic uses
# GENERATE / TECHNICAL_REPAIR / SEMANTIC_REPAIR at the proper stages.
build_graph = phase42.build_graph
initial_state = phase42.initial_state
assert_phase42_contract = phase42.assert_phase42_contract

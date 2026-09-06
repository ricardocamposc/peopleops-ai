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


def select_query_programmer_skill(repair_type: str | None) -> str:
    """Map workflow state to one focused Query Programmer skill."""
    if repair_type == "SEMANTIC":
        return "SEMANTIC_REPAIR"
    if repair_type in {"TECHNICAL", "INTERNAL_SELF_REPAIR"}:
        return "TECHNICAL_REPAIR"
    return "GENERATE"


def _skill_templates() -> dict[str, ChatPromptTemplate]:
    return {
        skill: ChatPromptTemplate.from_messages(
            [("system", spec["prompt"]), ("human", "{{user_input}}")],
            template_format="jinja2",
        )
        for skill, spec in QUERY_PROGRAMMER_SKILLS.items()
    }


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

        # `prompt` intentionally overrides the legacy prompt argument recorded by
        # phase42._record so the audit artifact contains the actual skill prompt.
        return result, {
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
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "rendered_system_prompt": rendered[0].content,
        }


# Re-export the existing Phase 4.2 graph/state helpers. The graph calls the
# runtime polymorphically, so inherited invoke_query_programmer() automatically
# uses GENERATE / TECHNICAL_REPAIR / SEMANTIC_REPAIR at the proper stages.
build_graph = phase42.build_graph
initial_state = phase42.initial_state
assert_phase42_contract = phase42.assert_phase42_contract

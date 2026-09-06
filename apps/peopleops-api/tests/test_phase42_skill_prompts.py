from __future__ import annotations

import direct_sqlalchemy_phase42_skills as skills


PLACEHOLDERS = (
    "{{data_model}}",
    "{{reference_date}}",
    "{{reference_year}}",
    "{{reference_month}}",
    "{{reference_day}}",
    "{{current_period}}",
    "{{timezone}}",
)


def test_skill_router_selects_generate_for_initial_call() -> None:
    assert skills.select_query_programmer_skill(None) == "GENERATE"


def test_skill_router_selects_technical_repair_for_both_technical_paths() -> None:
    assert skills.select_query_programmer_skill("TECHNICAL") == "TECHNICAL_REPAIR"
    assert (
        skills.select_query_programmer_skill("INTERNAL_SELF_REPAIR")
        == "TECHNICAL_REPAIR"
    )


def test_skill_router_selects_semantic_repair() -> None:
    assert skills.select_query_programmer_skill("SEMANTIC") == "SEMANTIC_REPAIR"


def test_each_skill_prompt_has_context_exactly_once() -> None:
    prompts = (
        skills.QUERY_GENERATE_PROMPT,
        skills.QUERY_TECHNICAL_REPAIR_PROMPT,
        skills.QUERY_SEMANTIC_REPAIR_PROMPT,
    )
    for prompt in prompts:
        for placeholder in PLACEHOLDERS:
            assert prompt.count(placeholder) == 1


def test_skill_prompts_have_distinct_responsibilities() -> None:
    assert "query-generation skill" in skills.QUERY_GENERATE_PROMPT
    assert "technical debugger and repairer" in skills.QUERY_TECHNICAL_REPAIR_PROMPT
    assert "semantic implementation repairer" in skills.QUERY_SEMANTIC_REPAIR_PROMPT


def test_technical_repair_prompt_requires_diagnostic_reasoning() -> None:
    prompt = skills.QUERY_TECHNICAL_REPAIR_PROMPT
    assert "line, offset, text, and source" in prompt
    assert "Do not merely adjust parentheses" in prompt
    assert "PYTHON_SYNTAX" in prompt
    assert "SQLALCHEMY_BUILD" in prompt
    assert "SQLALCHEMY_COMPILE" in prompt


def test_semantic_repair_keeps_functional_requirement_authoritative() -> None:
    prompt = skills.QUERY_SEMANTIC_REPAIR_PROMPT
    assert "Functional Requirement is the source of truth" in prompt
    assert "do not obey feedback that conflicts" in prompt
    assert "comparison preservation" in prompt

"""Run Phase 3.4.3 comparison cases without executing queries."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import semantic_understanding_phase3 as phase3
import semantic_understanding_phase342 as phase342
import semantic_understanding_phase343 as phase343
from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase242 import (
    CAPABILITIES,
    SOURCE_DATE,
    SOURCE_TIMEZONE,
    scoped_catalog,
)
from semantic_query_dsl_phase243 import ScopeSelectionV243
from semantic_query_dsl_phase244 import capabilities


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonicalize(value: phase343.SemanticUnderstandingV343) -> phase343.SemanticUnderstandingV343:
    value = value.model_copy(deep=True)
    if value.ambiguities or value.unsupported_reasons:
        value.requested_fields = []
        value.measure = None
        value.temporal = None
        value.comparison = None
        value.breakdowns = []
        value.calendar_conditions = []
        value.order_by = []
        value.limit = None
        return value
    if value.temporal:
        adapted = phase342.SemanticUnderstandingV342(
            goal=value.goal,
            temporal=value.temporal,
            temporal_resolution_status=value.temporal_resolution_status,
            ambiguities=value.ambiguities,
            unsupported_reasons=value.unsupported_reasons,
        )
        value.temporal = phase342.validate_for_pipeline(adapted).temporal
    if value.comparison:
        left = value.comparison.left.model_copy(deep=True)
        right = value.comparison.right.model_copy(deep=True)
        unresolved = [operand for operand in (left, right) if operand.resolution_source == "UNRESOLVED"]
        if unresolved:
            value.ambiguities.append("A comparison operand has unresolved temporal granularity.")
            value.temporal_resolution_status = "AMBIGUOUS"
            value.requested_fields = []
            value.measure = None
            value.temporal = None
            value.comparison = None
            value.breakdowns = []
            value.calendar_conditions = []
            value.order_by = []
            value.limit = None
            return value
        if right.relation == "PREVIOUS" and right.unit is None and left.unit is not None:
            right.unit = left.unit
            right.resolution_source = "ANTECEDENT"
            right.resolution_evidence = "The preceding operand establishes the unit."
        for operand in (left, right):
            if len(operand.months) > 1 and operand.unit == "MONTH":
                operand.unit = "YEAR"
                if operand.relation == "LAST_N":
                    operand.relation = "EXACT" if operand is left else "PREVIOUS"
            if operand.reference_frame != "EXPLICIT" and not (operand.reference_frame == "CURRENT_YEAR" and operand.months):
                operand.year = None
                operand.month = None
                operand.months = []
                operand.start_date = None
                operand.end_date = None
        if left.reference_frame == "CURRENT_MONTH" and right.reference_frame == "CURRENT_MONTH" and left.unit == right.unit == "MONTH":
            value.comparison.alignment = "SAME_PERIOD"
        elif left.months and right.months and left.unit == right.unit == "YEAR":
            value.comparison.alignment = "SAME_MONTH"
        elif left.unit == right.unit == "MONTH":
            value.comparison.alignment = "SAME_PERIOD"
        value.comparison.left = left
        value.comparison.right = right
    return value


def operand_core(value: dict[str, Any]) -> dict[str, Any]:
    result = {key: value[key] for key in ("reference_frame", "relation", "unit") if value.get(key) is not None}
    if value.get("relative_to") is not None:
        result["relative_to"] = value["relative_to"]
    if value.get("relation") == "LAST_N" and value.get("count") is not None:
        result["count"] = value["count"]
    if value.get("reference_frame") == "EXPLICIT":
        keys = ("year", "month") if value.get("month") is not None else ("year", "months")
        for key in keys:
            if value.get(key) not in (None, []):
                result[key] = value[key]
    elif value.get("reference_frame") == "CURRENT_YEAR" and value.get("months") not in (None, []):
        result["months"] = value["months"]
    if value.get("through_current_date"):
        result["through_current_date"] = True
    return result


def expected_core(case: dict[str, Any]) -> dict[str, Any] | None:
    expected = case["expected"]
    if expected.get("comparison"):
        return {side: operand_core(expected["comparison"][side]) for side in ("left", "right")}
    return operand_core(expected["temporal"]) if expected.get("temporal") else None


def actual_core(value: phase343.SemanticUnderstandingV343) -> dict[str, Any] | None:
    if value.comparison:
        return {side: operand_core(getattr(value.comparison, side).model_dump()) for side in ("left", "right")}
    return operand_core(value.temporal.model_dump()) if value.temporal else None


def comparison_shape(value: phase343.SemanticUnderstandingV343) -> dict[str, Any] | None:
    if value.comparison is None:
        return None
    return {"alignment": value.comparison.alignment, "operation": value.comparison.operation}


def answerability(value: phase343.SemanticUnderstandingV343) -> str:
    if value.unsupported_reasons:
        return "UNSUPPORTED_QUERY"
    if value.ambiguities:
        return "NEEDS_CLARIFICATION"
    return "UNDERSTOOD_AND_EXECUTABLE"


def compiled_answerability(compiled: phase343.ComparisonPlan | phase3.SemanticQueryIntentV246) -> str:
    if isinstance(compiled, phase343.ComparisonPlan):
        return "UNDERSTOOD_AND_EXECUTABLE"
    return phase3.derived_answerability(compiled)


def run(cases_path: Path, output_dir: Path, model: str) -> None:
    cases = load_cases(cases_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    llm = OpenAIStructuredModel(api_key=os.environ["OPENAI_API_KEY"], model=model, max_retries=0)
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        scope_instructions = f"{phase3.SCOPE_PROMPT}\n\nQuestion:\n{case['question']}\n\nCapabilities:\n{json.dumps(CAPABILITIES)}"
        scope = llm.parse(purpose="phase343-capability-scope", instructions=scope_instructions, output_model=ScopeSelectionV243)
        selected = capabilities(scope)
        catalog = scoped_catalog(selected)
        instructions = (
            f"{phase343.UNDERSTANDING_PROMPT_V343}\n\nQuestion:\n{case['question']}\n\n"
            f"Source date: {SOURCE_DATE.isoformat()}\nTimezone: {SOURCE_TIMEZONE}\n"
            f"Scoped catalog:\n{json.dumps(catalog)}"
        )
        raw = llm.parse(purpose="phase343-semantic-understanding", instructions=instructions, output_model=phase343.SemanticUnderstandingV343)
        canonical = canonicalize(raw)
        compiled = phase343.compile_comparison(canonical)
        expected = case["expected"]
        raw_core = actual_core(raw)
        canonical_core = actual_core(canonical)
        raw_answerability = answerability(raw)
        canonical_answerability = answerability(canonical)
        compiled_dump = compiled if isinstance(compiled, dict) else compiled.model_dump()
        row = {
            "id": case["id"],
            "question": case["question"],
            "expected": expected,
            "scope": scope.model_dump(),
            "selected_capabilities": selected,
            "selected_scoped_catalog": catalog,
            "raw_understanding": raw.model_dump(),
            "canonical_understanding": canonical.model_dump(),
            "canonicalization_changed": raw.model_dump() != canonical.model_dump(),
            "raw_temporal_core": raw_core,
            "canonical_temporal_core": canonical_core,
            "raw_answerability": raw_answerability,
            "canonical_answerability": canonical_answerability,
            "compiled": compiled_dump,
            "compiled_answerability": compiled_answerability(compiled),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        row["raw_success"] = raw_core == expected_core(case) and raw_answerability == expected["answerability"]
        expected_shape = {key: expected[key] for key in ("alignment", "operation")} if expected.get("comparison") else None
        row["raw_comparison_shape"] = comparison_shape(raw)
        row["canonical_comparison_shape"] = comparison_shape(canonical)
        row["raw_success"] = row["raw_success"] and row["raw_comparison_shape"] == expected_shape
        row["canonical_success"] = canonical_core == expected_core(case) and canonical_answerability == expected["answerability"] and row["canonical_comparison_shape"] == expected_shape
        row["compiled_success"] = row["canonical_success"] and row["compiled_answerability"] == expected["answerability"]
        rows.append(row)
    metrics = {
        "cases": len(rows),
        "structured_output_success": len(rows),
        "raw_understanding_success": sum(row["raw_success"] for row in rows),
        "canonical_understanding_success": sum(row["canonical_success"] for row in rows),
        "compiled_semantic_success": sum(row["compiled_success"] for row in rows),
        "comparison_cases": sum(row["expected"].get("comparison") is not None for row in rows),
        "compiler_valid_input_cases": sum(row["canonical_success"] for row in rows),
        "compiler_success_given_valid_input": sum(row["compiled_success"] for row in rows),
    }
    (output_dir / "manifest.json").write_text(json.dumps({"phase": "3.4.3", "run_type": "comparison-inspection", "cases": len(rows), "repetitions": 1, "model": model, "source_date": SOURCE_DATE.isoformat(), "timezone": SOURCE_TIMEZONE}, indent=2), encoding="utf-8")
    (output_dir / "raw_responses.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    phase343.assert_phase343_contract()
    run(args.cases, args.output_dir, args.model)


if __name__ == "__main__":
    main()

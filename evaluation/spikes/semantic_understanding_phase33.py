"""Phase 3.3 focused inspection: semantic composition hard cases.

This experiment adds only a focused dataset/evaluator around the frozen Phase 3.2
canonicalizer, capability closure, compiler, normalizer, and renderer. It does not
execute MCP, SQL, or Eloquent.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import semantic_understanding_phase3 as phase3
import semantic_understanding_phase31 as phase31
import semantic_understanding_phase32 as phase32
from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase242 import CAPABILITIES, SOURCE_DATE, SOURCE_TIMEZONE, scoped_catalog
from semantic_query_dsl_phase243 import ScopeSelectionV243
from semantic_query_dsl_phase244 import capabilities

ROOT = Path(__file__).resolve().parents[2]
GROUPS_PATH = ROOT / "evaluation/spikes/semantic_understanding_phase33_groups.json"

PROMPT_V33 = phase32.UNDERSTANDING_PROMPT_V32 + """

PHASE 3.3 HARD CASES
- A calendar condition filters records inside the containing temporal scope; it is never a breakdown.
- Create a breakdown only when the user explicitly asks to group, split, compare, or report by that dimension.
- Explicit 'no grouping' means breakdowns must be empty.
- 'First day of the week' and 'first day of each month' are not supported conceptual predicates in this catalog;
  report unsupported_reasons rather than inventing a weekday number or enumerating dates.
- 'Previous period/prior period' without an explicit or established unit is ambiguous; do not guess month, year,
  payroll period, or day. Explicit previous month/year remains semantically distinct.
- A date used for a calendar filter or measure is not a requested display field unless the user explicitly asks to
  show it. Ordering a date is not grouping it.
- For monthly analytical groupings spanning time, use YEAR_MONTH rather than MONTH alone.
"""


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize_model_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: normalize_model_value(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [normalize_model_value(v) for v in value]
    return value


def temporal_semantic_fingerprint(value: Any) -> Any:
    """Compare only temporal meaning, not Pydantic defaults or structural fields."""
    if value is None:
        return None
    value = value if isinstance(value, dict) else value.model_dump()
    keep = {"reference_frame", "relation", "unit"}
    if value.get("relation") == "LAST_N":
        keep.add("count")
    if value.get("reference_frame") == "EXPLICIT":
        if value.get("unit") == "YEAR":
            keep.add("year")
        elif value.get("unit") == "MONTH":
            keep.update({"year", "month", "months"})
    if value.get("through_current_date") is True:
        keep.add("through_current_date")
    return {key: value[key] for key in sorted(keep) if value.get(key) is not None and value.get(key) != []}


def calendar_semantic_fingerprint(value: Any) -> Any:
    """Remove only renderer/model metadata, retaining the calendar predicate meaning."""
    value = value if isinstance(value, dict) else value.model_dump()
    return {
        key: normalize_model_value(value[key])
        for key in ("field", "derivation", "operator", "value", "predicate")
        if key in value and value[key] is not None
    }


def self_tests() -> None:
    assert temporal_semantic_fingerprint({"reference_frame": "CURRENT_MONTH", "relation": "PREVIOUS", "unit": "MONTH"}) == temporal_semantic_fingerprint({"reference_frame": "CURRENT_MONTH", "relation": "PREVIOUS", "unit": "MONTH", "months": [], "through_current_date": False})
    assert temporal_semantic_fingerprint({"reference_frame": "CURRENT_MONTH", "relation": "LAST_N", "unit": "MONTH", "count": 3}) != temporal_semantic_fingerprint({"reference_frame": "CURRENT_MONTH", "relation": "LAST_N", "unit": "MONTH", "count": 2})
    assert calendar_semantic_fingerprint({"field": "overtime.work_date", "derivation": "WEEKDAY", "operator": "EQ", "value": "MONDAY", "type": "DERIVED_VALUE", "values": []}) == calendar_semantic_fingerprint({"field": "overtime.work_date", "derivation": "WEEKDAY", "operator": "EQ", "value": "MONDAY"})
    assert calendar_semantic_fingerprint({"field": "overtime.work_date", "derivation": "WEEKDAY", "operator": "EQ", "value": "MONDAY"}) != calendar_semantic_fingerprint({"field": "overtime.work_date", "derivation": "WEEKDAY", "operator": "EQ", "value": "FRIDAY"})
    assert calendar_semantic_fingerprint({"field": "overtime.work_date", "predicate": "IS_LAST_DAY_OF_MONTH"}) != calendar_semantic_fingerprint({"field": "overtime.work_date", "derivation": "DAY_OF_MONTH", "operator": "EQ", "value": 31})
    assert [] != [{"field": "overtime.work_date", "derivation": "YEAR_MONTH"}]
    assert "NEEDS_CLARIFICATION" != "UNDERSTOOD_AND_EXECUTABLE"


def expected_understanding_differences(
    case: dict[str, Any], understanding: phase3.SemanticUnderstanding
) -> list[str]:
    expected = case["understanding"]
    actual = understanding.model_dump(exclude_none=True)
    differences: list[str] = []
    expected_unsupported = bool(expected.get("unsupported", False))
    if expected_unsupported:
        return [] if actual.get("unsupported_reasons") else ["UNSUPPORTED_CLASSIFICATION_ERROR"]
    if sorted(actual.get("requested_fields", [])) != sorted(expected.get("requested_fields", [])):
        differences.append("RESULT_FIELD_ERROR")
    actual_measure = actual.get("measure")
    if actual_measure != expected.get("measure"):
        differences.append("MEASURE_ERROR")
    actual_temporal = temporal_semantic_fingerprint(actual.get("temporal"))
    if actual_temporal != expected.get("temporal"):
        differences.append("TEMPORAL_SCOPE_ERROR")
    if actual.get("breakdowns", []) != expected.get("breakdowns", []):
        differences.append("GROUPING_ERROR")
    if actual.get("calendar_conditions", []) != expected.get("calendar_conditions", []):
        differences.append("CALENDAR_CONDITION_ERROR")
    expected_ambiguous = bool(expected.get("ambiguous", False))
    if bool(actual.get("ambiguities")) != expected_ambiguous:
        differences.append("AMBIGUITY_ERROR")
    if bool(actual.get("unsupported_reasons")) != expected_unsupported:
        differences.append("UNSUPPORTED_CLASSIFICATION_ERROR")
    actual_order = [normalize_model_value(x) for x in actual.get("order_by", [])]
    if actual_order != expected.get("order_by", []):
        differences.append("ORDER_ERROR")
    if actual.get("limit") != expected.get("limit"):
        differences.append("LIMIT_ERROR")
    if expected_ambiguous and any(
        [actual.get("requested_fields"), actual.get("measure"), actual.get("temporal"),
         actual.get("breakdowns"), actual.get("calendar_conditions"), actual.get("order_by"),
         actual.get("limit")]
    ):
        differences.append("UNSUPPORTED_OR_AMBIGUOUS_CONTENT")
    return differences


def expected_compiled_differences(
    case: dict[str, Any], intent: phase3.SemanticQueryIntentV246, normalized: Any
) -> list[str]:
    expected = case["expected"]
    differences: list[str] = []
    expected_answerability = expected.get("answerability", "UNDERSTOOD_AND_EXECUTABLE")
    actual_answerability = phase3.derived_answerability(intent)
    if actual_answerability != expected_answerability:
        differences.append("ANSWERABILITY_ERROR")
    if expected_answerability != "UNDERSTOOD_AND_EXECUTABLE":
        if intent.measures or intent.time_scope or intent.group_by or intent.order_by or intent.result_fields:
            differences.append("EXECUTABLE_CONTENT_ERROR")
        return differences
    if normalize_model_value([m.model_dump() for m in intent.measures]) != expected.get("measures", []):
        differences.append("MEASURE_ERROR")
    if sorted(intent.result_fields) != sorted(expected.get("result_fields", [])):
        differences.append("RESULT_FIELD_ERROR")
    actual_groups = [normalize_model_value(g.model_dump()) for g in intent.group_by]
    if actual_groups != expected.get("group_by", []):
        differences.append("GROUPING_ERROR")
    actual_order = [normalize_model_value(o.model_dump()) for o in intent.order_by]
    if actual_order != expected.get("order_by", []):
        differences.append("ORDER_ERROR")
    expected_ranges = expected.get("normalized_ranges")
    expected_range = expected_ranges[0] if isinstance(expected_ranges, list) and len(expected_ranges) == 1 else expected_ranges
    if normalized != expected_range and expected_ranges is not None:
        differences.append("TEMPORAL_SCOPE_ERROR")
    actual_derived = [calendar_semantic_fingerprint(x) for x in intent.derived_calendar_filters]
    if actual_derived != expected.get("derived_conditions", []):
        differences.append("CALENDAR_CONDITION_ERROR")
    actual_predicates = [calendar_semantic_fingerprint(x) for x in intent.calendar_predicate_filters]
    if actual_predicates != expected.get("calendar_conditions", []):
        differences.append("CALENDAR_CONDITION_ERROR")
    if expected.get("relative_required") and (
        not intent.time_scope or intent.time_scope.kind != "RELATIVE_RANGE"
    ):
        differences.append("RELATIVE_INTENT_ERROR")
    return differences


def scope_diff(case: dict[str, Any], actual: list[str]) -> list[str]:
    return [] if sorted(actual) == sorted(case["expected"]["capabilities"]) else ["SCOPE_ERROR"]


def run(case_path: Path, output_dir: Path, model: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = load_cases(case_path)
    self_tests()
    assert len(cases) == 32 and len({case["id"] for case in cases}) == 32
    llm = OpenAIStructuredModel(api_key=os.environ["OPENAI_API_KEY"], model=model, max_retries=0)
    rows: list[dict[str, Any]] = []
    for case in cases:
        row: dict[str, Any] = {"id": case["id"], "question": case["question"]}
        started = time.perf_counter()
        try:
            scope_prompt = f"{phase3.SCOPE_PROMPT}\n\nQuestion:\n{case['question']}\n\nCapabilities:\n{json.dumps(CAPABILITIES)}"
            scope = llm.parse(purpose="phase33-capability-scope", instructions=scope_prompt, output_model=ScopeSelectionV243)
            selected = capabilities(scope)
            selected_catalog = scoped_catalog(selected)
            row.update({"scope": scope.model_dump(), "selected_capabilities": selected,
                        "selected_scope_differences": scope_diff(case, selected),
                        "selected_catalog": selected_catalog})
            row["selected_scope_success"] = not row["selected_scope_differences"]
            understanding_prompt = (
                f"{PROMPT_V33}\n\nQuestion:\n{case['question']}\n\n"
                f"Source date: {SOURCE_DATE.isoformat()}\nTimezone: {SOURCE_TIMEZONE}\n"
                f"Scoped catalog:\n{json.dumps(selected_catalog)}"
            )
            raw = llm.parse(purpose="phase33-semantic-understanding", instructions=understanding_prompt,
                            output_model=phase3.SemanticUnderstanding)
            row["raw_understanding"] = raw.model_dump()
            row["raw_differences"] = expected_understanding_differences(case, raw)
            row["raw_understanding_success"] = not row["raw_differences"]
            canonical = phase31.canonicalize_understanding(raw)
            row["canonical_understanding"] = canonical.model_dump()
            row["canonicalization_changed"] = canonical.model_dump() != raw.model_dump()
            row["canonical_differences"] = expected_understanding_differences(case, canonical)
            row["canonical_understanding_success"] = not row["canonical_differences"]
            row["referenced_fields"] = sorted(phase32.referenced_fields(canonical))
            row["derived_required_capabilities"] = phase32.derive_required_capabilities(canonical)
            effective = phase32.effective_capabilities(selected, canonical)
            row["effective_capabilities"] = effective
            row["effective_scope_differences"] = scope_diff(case, effective)
            row["effective_scope_success"] = not row["effective_scope_differences"]
            row["effective_catalog"] = scoped_catalog(effective)
            intent = phase3.compile_understanding(canonical)
            row["compiled_intent"] = intent.model_dump()
            row["derived_answerability"] = phase3.derived_answerability(intent)
            row["derived_entities"] = phase3.derived_entities(intent)
            row["derived_result_mode"] = phase3.result_mode(intent)
            normalized = phase3.normalize_time_scope(intent.time_scope)
            row["normalized_time_scope"] = normalized
            row["compiled_differences"] = expected_compiled_differences(case, intent, normalized)
            row["compiled_semantic_success"] = not row["compiled_differences"]
            row["eloquent_like"] = phase3.eloquent_like(intent, normalized)
            if row["canonical_differences"]:
                row["first_failing_component"] = row["canonical_differences"][0]
            elif row["effective_scope_differences"]:
                row["first_failing_component"] = "SCOPE_ERROR"
            elif row["compiled_differences"]:
                row["first_failing_component"] = row["compiled_differences"][0]
            elif row["selected_scope_differences"]:
                row["first_failing_component"] = "SELECTED_SCOPE_RECOVERED"
            else:
                row["first_failing_component"] = "FULL_SUCCESS"
        except Exception as exc:
            row.update({"error": f"{type(exc).__name__}: {exc}", "raw_understanding_success": False,
                        "canonical_understanding_success": False, "compiled_semantic_success": False,
                        "selected_scope_success": False, "effective_scope_success": False,
                        "first_failing_component": "RUNNER_OR_MODEL_FAILURE"})
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        rows.append(row)

    groups = json.loads(GROUPS_PATH.read_text(encoding="utf-8"))
    contrastive = {}
    for name, ids in groups.items():
        members = [r for r in rows if r["id"] in ids]
        contrastive[name] = {"cases": ids, "all_correct": all(r.get("compiled_semantic_success") for r in members),
                             "compiled_success": sum(bool(r.get("compiled_semantic_success")) for r in members),
                             "total": len(members)}
    metrics = {
        "phase": "3.3-semantic-composition-hard-cases", "cases": len(rows), "repetitions": 1,
        "structured_output_success": sum("raw_understanding" in r for r in rows),
        "raw_understanding_success": sum(bool(r.get("raw_understanding_success")) for r in rows),
        "canonical_understanding_success": sum(bool(r.get("canonical_understanding_success")) for r in rows),
        "compiled_semantic_success": sum(bool(r.get("compiled_semantic_success")) for r in rows),
        "selected_scope_success": sum(bool(r.get("selected_scope_success")) for r in rows),
        "effective_scope_success": sum(bool(r.get("effective_scope_success")) for r in rows),
        "selected_scope_recovered": sum(r.get("first_failing_component") == "SELECTED_SCOPE_RECOVERED" for r in rows),
        "canonicalization_changed": sum(bool(r.get("canonicalization_changed")) for r in rows),
        "normalization_errors": sum(bool(r.get("normalization_error")) for r in rows),
        "failure_distribution": dict(Counter(r.get("first_failing_component") for r in rows if r.get("first_failing_component") != "FULL_SUCCESS")),
        "contrastive_groups": contrastive,
        "mcp_execution": 0, "sql_execution": 0, "eloquent_execution": 0,
    }
    manifest = {"phase": metrics["phase"], "run_id": str(uuid.uuid4()), "timestamp": time.time(), "model": model,
                "source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE,
                "retries": 0, "dataset": str(case_path), "group_metadata": str(GROUPS_PATH),
                "frozen_layers": ["canonicalizer", "effective_scope", "compiler", "normalizer", "entity_derivation", "eloquent_like"],
                "mcp_execution": False, "sql_execution": False, "eloquent_execution": False}
    (output_dir / "raw_responses.jsonl").write_text("\n".join(json.dumps(r, default=str, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(ROOT / "evaluation/spikes/semantic_understanding_phase33_cases.jsonl"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    run(Path(args.cases), Path(args.output_dir), args.model)


if __name__ == "__main__":
    main()

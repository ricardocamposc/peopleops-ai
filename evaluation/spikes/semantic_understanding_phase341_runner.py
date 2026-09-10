"""Dedicated Phase 3.4.1 runner for the temporal-focused oracle.

The dataset intentionally has no Phase 3.2 ``understanding`` or capability
oracle. This runner evaluates only the temporal/answerability fields present in
that dataset while reusing the frozen deterministic pipeline.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import semantic_understanding_phase3 as phase3
import semantic_understanding_phase31 as phase31
import semantic_understanding_phase32 as phase32
import semantic_understanding_phase341 as phase341
from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase243 import ScopeSelectionV243

SOURCE_DATE = "2026-08-30"
SOURCE_TIMEZONE = "UTC"


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def temporal_fingerprint(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)
    if not isinstance(value, dict):
        return value
    result = {key: value[key] for key in ("reference_frame", "relation", "unit", "count", "through_current_date") if key in value and value[key] not in (None, [], False)}
    if result.get("relation") == "PREVIOUS" and result.get("count") == 1:
        result.pop("count")
    if result.get("reference_frame") == "EXPLICIT":
        for key in ("year", "month"):
            if key in value and value[key] is not None:
                result[key] = value[key]
    return result


def answerability_from_understanding(value: dict[str, Any]) -> str:
    if value.get("ambiguities"):
        return "NEEDS_CLARIFICATION"
    if value.get("unsupported_reasons"):
        return "UNSUPPORTED_QUERY"
    return "UNDERSTOOD_AND_EXECUTABLE"


def understanding_executable(value: dict[str, Any]) -> bool:
    return any(value.get(key) for key in ("requested_fields", "measure", "temporal", "breakdowns", "calendar_conditions", "order_by", "limit"))


def intent_executable(value: dict[str, Any]) -> bool:
    return any(value.get(key) for key in ("result_fields", "measures", "time_scope", "derived_calendar_filters", "calendar_predicate_filters", "scalar_conditions", "group_by", "order_by", "limit"))


def materialization_leak(value: dict[str, Any], case: dict[str, Any]) -> bool:
    if not case["expected"].get("materialization_forbidden"):
        return False
    temporal = value.get("temporal") or {}
    return any(temporal.get(key) not in (None, [], False) for key in ("year", "month", "months", "start_date", "end_date"))


def canonical_differences(case: dict[str, Any], value: dict[str, Any]) -> list[str]:
    expected = case["expected"]
    differences: list[str] = []
    if temporal_fingerprint(value.get("temporal")) != temporal_fingerprint(expected.get("temporal")):
        differences.append("TEMPORAL_CORE")
    if answerability_from_understanding(value) != expected["answerability"]:
        differences.append("ANSWERABILITY")
    if expected["answerability"] in ("NEEDS_CLARIFICATION", "UNSUPPORTED_QUERY") and understanding_executable(value):
        differences.append("NON_EXECUTABLE_STATE")
    return differences


def self_tests(cases: list[dict[str, Any]]) -> None:
    by_id = {case["id"]: case for case in cases}
    assert by_id["tsd-exp-previous-month"]["expected"]["temporal"] != by_id["tsd-amb-period"]["expected"]["temporal"]
    assert by_id["tsd-exp-january"]["expected"]["temporal"] != by_id["tsd-exp-previous-month"]["expected"]["temporal"]
    assert by_id["tsd-amb-period"]["expected"]["answerability"] == "NEEDS_CLARIFICATION"
    assert by_id["tsd-amb-period"]["expected"]["ambiguous"] is True
    assert by_id["tsd-domain-exercise"]["expected"]["answerability"] == "UNSUPPORTED_QUERY"
    assert by_id["tsd-domain-exercise"]["expected"]["unsupported"] is True
    assert by_id["tsd-ant-inherited"]["expected"]["granularity_source"] == "inherited"
    assert by_id["tsd-ant-january-period"]["expected"]["granularity_source"] == "missing"
    materialized = {"temporal": {"reference_frame": "CURRENT_MONTH", "relation": "PREVIOUS", "unit": "MONTH", "year": 2026, "month": 7}}
    assert temporal_fingerprint(materialized["temporal"]) == temporal_fingerprint(by_id["tsd-exp-previous-month"]["expected"]["temporal"])
    assert materialization_leak(materialized, by_id["tsd-exp-previous-month"])
    assert answerability_from_understanding({"ambiguities": ["missing"], "unsupported_reasons": [], "temporal": None}) == "NEEDS_CLARIFICATION"
    assert answerability_from_understanding({"ambiguities": [], "unsupported_reasons": ["unsupported"], "temporal": None}) == "UNSUPPORTED_QUERY"
    phase341.assert_non_executable_canonicalization()
    print("ABSTENTION_SELF_TEST_OK")


def scope_instructions(case: dict[str, Any]) -> str:
    return f"{phase3.SCOPE_PROMPT}\n\nQuestion:\n{case['question']}\n\nCapabilities:\n{json.dumps(phase32.CAPABILITIES)}"


def understanding_instructions(case: dict[str, Any], catalog: dict[str, Any]) -> str:
    context = f"\nStructured context:\n{case['context']}" if case.get("context") else ""
    return (
        f"{phase341.UNDERSTANDING_PROMPT_V341}\n\nQuestion:\n{case['question']}"
        f"\nSource date: {SOURCE_DATE}\nTimezone: {SOURCE_TIMEZONE}{context}"
        f"\nScoped conceptual catalog:\n{json.dumps(catalog)}"
    )


def run(cases_path: Path, output_dir: Path, model: str) -> None:
    cases = load_cases(cases_path)
    self_tests(cases)
    output_dir.mkdir(parents=True, exist_ok=True)
    llm = OpenAIStructuredModel(api_key=os.environ["OPENAI_API_KEY"], model=model, max_retries=0)
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        row: dict[str, Any] = {"id": case["id"], "question": case["question"], "language": case.get("language"), "category": case.get("category"), "context": case.get("context"), "expected": case["expected"]}
        selected: list[str] = []
        try:
            scope = llm.parse(purpose="phase341-capability-scope", instructions=scope_instructions(case), output_model=ScopeSelectionV243)
            selected = phase32.capabilities(scope)
            row["scope"] = scope.model_dump()
        except Exception as exc:  # noqa: BLE001 - preserve diagnostics and continue each case
            row["scope_error"] = f"{type(exc).__name__}: {exc}"
        row["selected_capabilities"] = selected
        catalog = phase32.scoped_catalog(selected)
        row["selected_scoped_catalog"] = catalog
        try:
            raw_model = llm.parse(purpose="phase341-semantic-understanding", instructions=understanding_instructions(case, catalog), output_model=phase3.SemanticUnderstanding)
            raw = raw_model.model_dump()
            row["raw_understanding"] = raw
            row["raw_temporal_fingerprint"] = temporal_fingerprint(raw.get("temporal"))
            row["raw_answerability"] = answerability_from_understanding(raw)
            row["raw_executable_content"] = understanding_executable(raw)
            row["raw_ambiguity_recognition"] = bool(raw.get("ambiguities"))
            row["raw_ambiguity_safety"] = bool(raw.get("ambiguities")) and not understanding_executable(raw)
            row["raw_unsupported_recognition"] = bool(raw.get("unsupported_reasons"))
            row["raw_materialization_leakage"] = materialization_leak(raw, case)
            row["raw_differences"] = canonical_differences(case, raw)
            canonical_model = phase31.canonicalize_understanding(raw_model)
            canonical = canonical_model.model_dump()
            row["canonical_understanding"] = canonical
            row["canonical_temporal_fingerprint"] = temporal_fingerprint(canonical.get("temporal"))
            row["canonical_answerability"] = answerability_from_understanding(canonical)
            row["canonical_executable_content"] = understanding_executable(canonical)
            row["canonical_ambiguity_safety"] = bool(canonical.get("ambiguities")) and not understanding_executable(canonical)
            row["canonical_unsupported_safety"] = bool(canonical.get("unsupported_reasons")) and not understanding_executable(canonical)
            row["canonical_materialization_leakage"] = materialization_leak(canonical, case)
            row["canonical_differences"] = canonical_differences(case, canonical)
            row["canonicalization_changed"] = raw != canonical
            row["referenced_fields"] = sorted(phase32.referenced_fields(canonical_model))
            row["derived_required_capabilities"] = phase32.derive_required_capabilities(canonical_model)
            row["effective_capabilities"] = phase32.effective_capabilities(selected, canonical_model)
            intent = phase3.compile_understanding(canonical_model)
            compiled = intent.model_dump()
            row["compiled_intent"] = compiled
            row["compiled_answerability"] = phase3.derived_answerability(intent)
            row["compiled_executable_content"] = intent_executable(compiled)
            row["compiled_ambiguity_safety"] = bool(compiled.get("ambiguities")) and not intent_executable(compiled)
            row["compiled_unsupported_safety"] = bool(compiled.get("unsupported_reasons")) and not intent_executable(compiled)
            try:
                row["normalized_time_scope"] = phase3.normalize_time_scope(intent.time_scope)
                row["normalization_error"] = None
            except Exception as exc:  # noqa: BLE001 - preserve normalization diagnostics
                row["normalized_time_scope"] = None
                row["normalization_error"] = f"{type(exc).__name__}: {exc}"
            row["derived_entities"] = phase3.derived_entities(intent)
        except Exception as exc:  # noqa: BLE001 - preserve layer diagnostics and continue the batch
            row["understanding_error"] = f"{type(exc).__name__}: {exc}"
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        rows.append(row)
    metric = {"phase": "semantic-understanding-phase341", "run_type": "focused-temporal-validation", "cases": len(rows), "repetitions": 1, "model": model, "source_current_date": SOURCE_DATE, "source_timezone": SOURCE_TIMEZONE, "retries": 0, "mcp_execution": 0, "sql_execution": 0, "eloquent_execution": 0, "structured_output_success": sum("raw_understanding" in row for row in rows), "raw_ambiguity_recognition": sum(row.get("raw_ambiguity_recognition", False) for row in rows), "raw_ambiguity_safety": sum(row.get("raw_ambiguity_safety", False) for row in rows), "canonical_ambiguity_safety": sum(row.get("canonical_ambiguity_safety", False) for row in rows), "compiled_ambiguity_safety": sum(row.get("compiled_ambiguity_safety", False) for row in rows), "raw_unsupported_recognition": sum(row.get("raw_unsupported_recognition", False) for row in rows), "canonical_unsupported_safety": sum(row.get("canonical_unsupported_safety", False) for row in rows), "compiled_unsupported_safety": sum(row.get("compiled_unsupported_safety", False) for row in rows), "normalization_errors": sum(bool(row.get("normalization_error")) for row in rows)}
    manifest = {**metric, "dataset": str(cases_path), "pipeline": "scope -> raw understanding -> canonicalization -> effective closure -> compiler -> normalization -> inspection", "compiler_invoked": True, "normalizer_invoked": True}
    (output_dir / "raw_responses.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metric, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metric, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    arguments = parser.parse_args()
    run(Path(arguments.cases), Path(arguments.output_dir), arguments.model)

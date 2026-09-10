"""Dedicated Phase 3.4.2 runner for structured temporal resolution."""
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
import semantic_understanding_phase342 as phase342
from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase243 import ScopeSelectionV243


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def executable(value: dict[str, Any]) -> bool:
    return any(value.get(key) for key in ("requested_fields", "measure", "temporal", "breakdowns", "calendar_conditions", "order_by", "limit"))


def answerability(value: dict[str, Any]) -> str:
    if value.get("ambiguities"):
        return "NEEDS_CLARIFICATION"
    if value.get("unsupported_reasons"):
        return "UNSUPPORTED_QUERY"
    return "UNDERSTOOD_AND_EXECUTABLE"


def temporal_core(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    keys = ("reference_frame", "relation", "unit", "count", "year", "month", "through_current_date")
    result = {key: value[key] for key in keys if key in value and value[key] not in (None, [], False)}
    if result.get("reference_frame") != "EXPLICIT":
        result.pop("year", None)
        result.pop("month", None)
    if result.get("relation") == "PREVIOUS" and result.get("count") == 1:
        result.pop("count")
    return result or None


def run(cases_path: Path, output_dir: Path, model: str, condition: str) -> None:
    cases = load_cases(cases_path)
    phase342.assert_phase342_contract()
    llm = OpenAIStructuredModel(api_key=os.environ["OPENAI_API_KEY"], model=model, max_retries=0)
    output_dir.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        row: dict[str, Any] = {"id": case["id"], "question": case["question"], "language": case.get("language"), "category": case.get("category"), "context": case.get("context"), "expected": case["expected"]}
        scope_prompt = f"{phase3.SCOPE_PROMPT}\n\nQuestion:\n{case['question']}\n\nCapabilities:\n{json.dumps(phase32.CAPABILITIES)}"
        scope = llm.parse(purpose="phase342-capability-scope", instructions=scope_prompt, output_model=ScopeSelectionV243)
        selected = phase32.capabilities(scope)
        catalog = phase32.scoped_catalog(selected)
        row.update({"selected_capabilities": selected, "selected_scoped_catalog": catalog, "scope": scope.model_dump()})
        instructions = phase342.prompt_for_case(case, disciplined=condition == "disciplined") + f"\nScoped conceptual catalog:\n{json.dumps(catalog)}"
        raw_model = llm.parse(purpose="phase342-semantic-understanding", instructions=instructions, output_model=phase342.SemanticUnderstandingV342)
        raw = raw_model.model_dump()
        validated_model = phase342.validate_for_pipeline(raw_model)
        validated = validated_model.model_dump()
        compiler_model = phase342.to_phase3_understanding(validated_model)
        canonical_model = phase31.canonicalize_understanding(compiler_model)
        canonical = canonical_model.model_dump()
        intent = phase3.compile_understanding(canonical_model)
        compiled = intent.model_dump()
        row.update({
            "raw_understanding": raw,
            "raw_temporal_core": temporal_core(raw.get("temporal")),
            "raw_answerability": answerability(raw),
            "raw_executable_content": executable(raw),
            "raw_ambiguity_recognition": bool(raw.get("ambiguities")),
            "raw_ambiguity_safety": bool(raw.get("ambiguities")) and not executable(raw),
            "raw_materialization_leakage": any((raw.get("temporal") or {}).get(key) not in (None, [], False) for key in ("year", "month", "months", "start_date", "end_date")) if case["expected"].get("symbolic_required") else False,
            "validated_understanding": validated,
            "validated_ambiguity_safety": bool(validated.get("ambiguities")) and not executable(validated),
            "validated_unsupported_safety": bool(validated.get("unsupported_reasons")) and not executable(validated),
            "validated_materialization_leakage": any((validated.get("temporal") or {}).get(key) not in (None, [], False) for key in ("year", "month", "months", "start_date", "end_date")) if case["expected"].get("symbolic_required") else False,
            "canonical_understanding": canonical,
            "canonical_temporal_core": temporal_core(canonical.get("temporal")),
            "canonical_answerability": answerability(canonical),
            "canonical_executable_content": executable(canonical),
            "canonical_ambiguity_safety": bool(canonical.get("ambiguities")) and not executable(canonical),
            "effective_capabilities": phase32.effective_capabilities(selected, canonical_model),
            "compiled_intent": compiled,
            "compiled_answerability": phase3.derived_answerability(intent),
            "compiled_executable_content": any(compiled.get(key) for key in ("result_fields", "measures", "time_scope", "derived_calendar_filters", "calendar_predicate_filters", "scalar_conditions", "group_by", "order_by", "limit")),
            "normalized_time_scope": phase3.normalize_time_scope(intent.time_scope),
            "derived_entities": phase3.derived_entities(intent),
        })
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        rows.append(row)
    metric = {"phase": "semantic-understanding-phase342", "run_type": "structured-temporal-resolution", "condition": condition, "cases": len(rows), "repetitions": 1, "model": model, "source_current_date": "2026-08-30", "source_timezone": "UTC", "retries": 0, "structured_output_success": len(rows)}
    (output_dir / "raw_responses.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metric, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps({**metric, "dataset": str(cases_path), "pipeline": "scope -> understanding -> canonicalization -> closure -> compiler -> normalization"}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metric, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--condition", choices=("baseline", "disciplined"), default="disciplined")
    args = parser.parse_args()
    run(Path(args.cases), Path(args.output_dir), args.model, args.condition)

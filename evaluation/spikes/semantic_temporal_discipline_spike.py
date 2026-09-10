"""Focused A/B spike for temporal lexical grounding and abstention discipline.

This is an understanding-only experiment. It reuses the frozen Phase 3.4
schema and prompt, adds one experimental prompt section in condition B, and
does not invoke the compiler, normalizer, MCP, SQL, or Eloquent execution.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import semantic_understanding_phase34 as phase34
from peopleops_api.analysis_workflow import OpenAIStructuredModel

SOURCE_DATE = "2026-08-30"
SOURCE_TIMEZONE = "UTC"

TEMPORAL_SEMANTIC_DISCIPLINE = """
TEMPORAL SEMANTIC DISCIPLINE
Interpret temporal language semantically. Do not calculate dates that can be represented symbolically.
A temporal expression is executable only when its granularity and reference are determined by the expression
itself or by an unambiguous antecedent in the same request/context. A glossary may explain terminology but
must not supply missing semantic information.

Explicit examples:
- current month means CURRENT_MONTH / EXACT / MONTH.
- previous month means CURRENT_MONTH / PREVIOUS / MONTH.
- current calendar year means CURRENT_YEAR / EXACT / YEAR.
- previous calendar year means CURRENT_YEAR / PREVIOUS / YEAR when supported by the contract.
- January 2026 is EXPLICIT / EXACT / MONTH / year=2026 / month=1.

The generic words period, prior period, previous period, período anterior, período previo, accounting period,
payroll period, fiscal period, ejercicio, and equivalent terms do not silently provide MONTH, YEAR, WEEK,
payroll, or accounting granularity. If materially different interpretations remain plausible, use ambiguities
and NEEDS_CLARIFICATION. If meaning is clear but the contract cannot represent it, use unsupported_reasons
and UNSUPPORTED_QUERY. Do not guess the most common business interpretation.

Contextual antecedents:
- "Compare the current month with the previous one" inherits MONTH from the explicit antecedent.
- "Compare January 2026 with the previous period" remains ambiguous because January does not establish that
  the generic word period has the same unit.

ABSTENTION SAFETY: when ambiguities or unsupported_reasons are present, clear all executable temporal,
measure, breakdown, calendar, ordering, requested-field, and limit content.

SYMBOLIC RELATIVE REPRESENTATION: preserve relative meanings such as PREVIOUS + MONTH. Do not add absolute
year/month/start/end values when they are derivable later. The source date anchors deterministic normalization;
it does not transfer date arithmetic into this understanding step.
"""


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def temporal_core(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)
    if not isinstance(value, dict):
        return value
    keys = ("reference_frame", "relation", "unit", "count", "year", "month", "months", "through_current_date")
    return {key: value[key] for key in keys if key in value and value[key] not in (None, [], False)}


def actual_answerability(output: dict[str, Any]) -> str:
    if output.get("ambiguities"):
        return "NEEDS_CLARIFICATION"
    if output.get("unsupported_reasons"):
        return "UNSUPPORTED_QUERY"
    return "UNDERSTOOD_AND_EXECUTABLE"


def has_executable_content(output: dict[str, Any]) -> bool:
    return any(output.get(key) for key in ("requested_fields", "measure", "temporal", "breakdowns", "calendar_conditions", "order_by", "limit"))


def materialization_leak(output: dict[str, Any], case: dict[str, Any]) -> bool:
    expected = case["expected"]
    if not expected["materialization_forbidden"]:
        return False
    temporal = output.get("temporal") or {}
    return any(temporal.get(key) not in (None, [], False) for key in ("year", "month", "months", "start_date", "end_date"))


def speculative_granularity(output: dict[str, Any], case: dict[str, Any]) -> bool:
    expected = case["expected"]
    if expected["granularity_source"] != "missing":
        return False
    temporal = output.get("temporal") or {}
    return bool(temporal.get("unit")) or bool(output.get("measure"))


def compare(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    actual_answer = actual_answerability(output)
    answer_ok = actual_answer == expected["answerability"]
    temporal_ok = temporal_core(output.get("temporal")) == temporal_core(expected.get("temporal"))
    safety_ok = True
    if expected["answerability"] in ("NEEDS_CLARIFICATION", "UNSUPPORTED_QUERY"):
        safety_ok = not has_executable_content(output)
    unsupported_ok = expected["answerability"] != "UNSUPPORTED_QUERY" or bool(output.get("unsupported_reasons"))
    leakage = materialization_leak(output, case)
    speculative = speculative_granularity(output, case)
    differences = []
    if not temporal_ok:
        differences.append("TEMPORAL_MEANING_ERROR")
    if not answer_ok:
        differences.append("AMBIGUITY_OR_ANSWERABILITY_ERROR")
    if not unsupported_ok:
        differences.append("UNSUPPORTED_CLASSIFICATION_ERROR")
    if not safety_ok:
        differences.append("EXECUTABLE_CONTENT_WHILE_NON_EXECUTABLE")
    if leakage:
        differences.append("MATERIALIZATION_LEAKAGE")
    if speculative:
        differences.append("SPECULATIVE_GRANULARITY_ERROR")
    strict_success = not differences
    return {
        "actual_answerability": actual_answer,
        "temporal_core_correct": temporal_ok,
        "answerability_correct": answer_ok,
        "abstention_safety_correct": safety_ok,
        "unsupported_recognition_correct": unsupported_ok,
        "materialization_leakage": leakage,
        "speculative_granularity": speculative,
        "differences": differences,
        "strict_success": strict_success,
    }


def run_self_tests() -> None:
    previous_month = {"reference_frame": "CURRENT_MONTH", "relation": "PREVIOUS", "unit": "MONTH"}
    previous_period = None
    assert previous_month != previous_period
    assert actual_answerability({"ambiguities": [], "unsupported_reasons": [], "temporal": previous_month}) == "UNDERSTOOD_AND_EXECUTABLE"
    assert actual_answerability({"ambiguities": ["unit missing"], "unsupported_reasons": [], "temporal": None}) == "NEEDS_CLARIFICATION"
    assert actual_answerability({"ambiguities": [], "unsupported_reasons": ["unsupported"], "temporal": None}) == "UNSUPPORTED_QUERY"
    explicit_antecedent = {"reference_frame": "CURRENT_MONTH", "relation": "PREVIOUS", "unit": "MONTH"}
    missing_antecedent = None
    assert explicit_antecedent != missing_antecedent
    symbolic = {"reference_frame": "CURRENT_MONTH", "relation": "PREVIOUS", "unit": "MONTH"}
    materialized = {**symbolic, "year": 2026, "month": 7}
    assert temporal_core(symbolic) != temporal_core(materialized)
    jan = {"reference_frame": "EXPLICIT", "relation": "EXACT", "unit": "MONTH", "year": 2026, "month": 1}
    assert not materialization_leak({"temporal": jan}, {"expected": {"materialization_forbidden": False}})


def instructions(case: dict[str, Any], with_discipline: bool) -> str:
    context = f"\nStructured context: {case['context']}" if case.get("context") else ""
    extra = f"\n{TEMPORAL_SEMANTIC_DISCIPLINE}\n" if with_discipline else ""
    return (
        f"{phase34.UNDERSTANDING_PROMPT_V34}\n{extra}"
        f"Source date: {SOURCE_DATE}\nSource timezone: {SOURCE_TIMEZONE}{context}\n"
        f"Question:\n{case['question']}"
    )


def run(cases_path: Path, output_dir: Path, model: str) -> None:
    run_self_tests()
    cases = load_cases(cases_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    llm = OpenAIStructuredModel(api_key=os.environ["OPENAI_API_KEY"], model=model, max_retries=0)
    rows: list[dict[str, Any]] = []
    for case in cases:
        row = {"id": case["id"], "question": case["question"], "language": case["language"], "category": case["category"], "context": case.get("context"), "expected": case["expected"]}
        for condition, discipline in (("A_CURRENT_PHASE34", False), ("B_TEMPORAL_DISCIPLINE", True)):
            started = time.perf_counter()
            try:
                parsed = llm.parse(
                    purpose=f"temporal-discipline-{condition.lower()}",
                    instructions=instructions(case, discipline),
                    output_model=phase34.phase32.phase3.SemanticUnderstanding,
                )
                output = parsed.model_dump()
                row[condition] = {"output": output, "analysis": compare(case, output), "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
            except Exception as exc:  # noqa: BLE001 - preserve per-condition diagnostics and continue the batch
                row[condition] = {"error": f"{type(exc).__name__}: {exc}", "analysis": {"strict_success": False}}
        rows.append(row)
    metrics = {
        "phase": "temporal-semantic-discipline",
        "run_type": "ab-inspection",
        "cases": len(rows),
        "repetitions": 1,
        "model": model,
        "source_current_date": SOURCE_DATE,
        "source_timezone": SOURCE_TIMEZONE,
        "retries": 0,
        "condition_a_success": sum(r["A_CURRENT_PHASE34"]["analysis"].get("strict_success", False) for r in rows),
        "condition_b_success": sum(r["B_TEMPORAL_DISCIPLINE"]["analysis"].get("strict_success", False) for r in rows),
        "structured_output_a": sum("output" in r["A_CURRENT_PHASE34"] for r in rows),
        "structured_output_b": sum("output" in r["B_TEMPORAL_DISCIPLINE"] for r in rows),
        "mcp_execution": 0,
        "sql_execution": 0,
        "eloquent_execution": 0,
    }
    manifest = {**metrics, "condition_a": "Phase 3.4 current prompt", "condition_b": "Phase 3.4 prompt plus temporal semantic discipline", "dataset": str(cases_path), "deterministic_compiler_invoked": False, "normalizer_invoked": False}
    (output_dir / "raw_responses.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    run(Path(args.cases), Path(args.output_dir), args.model)

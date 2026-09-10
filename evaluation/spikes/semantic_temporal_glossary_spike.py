"""A/B inspection spike for temporal domain vocabulary and ambiguity.

This file evaluates Semantic Understanding only. It does not modify or invoke
the Phase 3.4 deterministic compiler, canonicalizer, production code, MCP,
SQL, or executable Eloquent.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import semantic_understanding_phase34 as phase34
from peopleops_api.analysis_workflow import OpenAIStructuredModel

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATE = "2026-08-30"
SOURCE_TIMEZONE = "UTC"

DOMAIN_TEMPORAL_GLOSSARY = """
DOMAIN TEMPORAL GLOSSARY
- A calendar month is the complete calendar month.
- The current month is the calendar month containing source_current_date.
- The previous month is the complete calendar month immediately before the current month.
- A calendar year is the complete calendar year.
- The current year is the calendar year containing source_current_date.
- The previous year is the complete calendar year immediately before the current year.
- An accounting period is a period whose unit depends on explicit context or catalog definition.
- A payroll period is a period defined by the HR/payroll provider.
- The generic word period is potentially ambiguous. Never assume month, year, payroll period,
  or accounting period without explicit or contextual evidence.
- A fiscal year is not necessarily a calendar year. If the fiscal calendar is not defined,
  do not invent its boundaries; report the concept as unsupported when the meaning is clear.
- If a context statement explicitly defines period as a calendar month or monthly payroll period,
  that context resolves the unit for the current request.
"""


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def temporal_fingerprint(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)
    if not isinstance(value, dict):
        return value
    keys = ("reference_frame", "relation", "unit", "count", "year", "month", "months", "through_current_date")
    result = {key: value[key] for key in keys if key in value}
    if not result.get("months"):
        result.pop("months", None)
    if result.get("through_current_date") is False:
        result.pop("through_current_date", None)
    return result


def expected_answerability(case: dict[str, Any]) -> str:
    return case["expected"]["answerability"]


def compare(case: dict[str, Any], actual: Any) -> list[str]:
    expected = case["expected"]
    differences: list[str] = []
    actual_temporal = temporal_fingerprint(actual.temporal)
    if actual_temporal != temporal_fingerprint(expected.get("temporal")):
        differences.append("TEMPORAL_MEANING")
    expected_answer = expected_answerability(case)
    actual_answer = "NEEDS_CLARIFICATION" if actual.ambiguities else (
        "UNSUPPORTED_QUERY" if actual.unsupported_reasons else "UNDERSTOOD_AND_EXECUTABLE"
    )
    if actual_answer != expected_answer:
        differences.append("ANSWERABILITY")
    if expected_answer == "NEEDS_CLARIFICATION" and (actual.measure or actual.temporal):
        differences.append("EXECUTABLE_CONTENT")
    if expected_answer == "UNSUPPORTED_QUERY" and not actual.unsupported_reasons:
        differences.append("UNSUPPORTED_RECOGNITION")
    return differences


def instructions(prompt: str, case: dict[str, Any], glossary: bool) -> str:
    context = f"\nStructured context for this request: {case['context']}\n" if case.get("context") else ""
    glossary_text = f"\n{DOMAIN_TEMPORAL_GLOSSARY}\n" if glossary else ""
    return (
        f"{prompt}\n{glossary_text}\n"
        f"Source date: {SOURCE_DATE}\nSource timezone: {SOURCE_TIMEZONE}\n"
        f"Question context:{context}\nQuestion:\n{case['question']}"
    )


def run(cases_path: Path, output_dir: Path, model: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = load_cases(cases_path)
    llm = OpenAIStructuredModel(api_key=os.environ["OPENAI_API_KEY"], model=model, max_retries=0)
    rows: list[dict[str, Any]] = []
    for case in cases:
        row = {"id": case["id"], "question": case["question"], "context": case.get("context")}
        for condition, glossary in (("A_CURRENT_PHASE34", False), ("B_WITH_DOMAIN_GLOSSARY", True)):
            started = time.perf_counter()
            try:
                actual = llm.parse(
                    purpose=f"temporal-glossary-{condition.lower()}",
                    instructions=instructions(phase34.UNDERSTANDING_PROMPT_V34, case, glossary),
                    output_model=phase34.phase32.phase3.SemanticUnderstanding,
                )
                row[condition] = {
                    "output": actual.model_dump(),
                    "differences": compare(case, actual),
                    "success": not compare(case, actual),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            except Exception as exc:
                row[condition] = {"error": f"{type(exc).__name__}: {exc}", "success": False}
        rows.append(row)
    metrics = {"phase": "temporal-domain-vocabulary-ambiguity", "cases": len(rows), "repetitions": 1,
               "model": model, "source_current_date": SOURCE_DATE, "source_timezone": SOURCE_TIMEZONE,
               "condition_a_success": sum(r["A_CURRENT_PHASE34"]["success"] for r in rows),
               "condition_b_success": sum(r["B_WITH_DOMAIN_GLOSSARY"]["success"] for r in rows),
               "structured_output_a": sum("output" in r["A_CURRENT_PHASE34"] for r in rows),
               "structured_output_b": sum("output" in r["B_WITH_DOMAIN_GLOSSARY"] for r in rows),
               "mcp_execution": 0, "sql_execution": 0, "eloquent_execution": 0}
    manifest = {"phase": metrics["phase"], "run_id": str(uuid.uuid4()), "cases": len(rows),
                "repetitions": 1, "model": model, "source_current_date": SOURCE_DATE,
                "source_timezone": SOURCE_TIMEZONE, "retries": 0,
                "condition_a": "current Phase 3.4 semantic context",
                "condition_b": "condition A plus domain temporal glossary",
                "dataset": str(cases_path), "mcp_execution": False, "sql_execution": False,
                "eloquent_execution": False}
    (output_dir / "raw_responses.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(ROOT / "evaluation/spikes/semantic_temporal_glossary_cases.jsonl"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    run(Path(args.cases), Path(args.output_dir), args.model)

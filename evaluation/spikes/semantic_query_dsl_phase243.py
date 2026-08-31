"""Phase 2.4.3 focused extension of Phase 2.4.2.

Only three hypotheses change:
1) minimal justified capability scope;
2) strict TemporalCondition fields by kind;
3) result_fields only for attributes explicitly requested by the user.
Production code, MCP, SQL, normalization semantics, entity derivation and renderer remain untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase242 import (
    CAPABILITIES,
    INTENT_PROMPT,
    SOURCE_DATE,
    SOURCE_TIMEZONE,
    TYPE_CAPABILITIES,
    SemanticQueryIntentV242,
    derived_answerability,
    derived_entities,
    derived_result_mode,
    normalize_temporal,
    render_eloquent_like,
    scoped_catalog,
    semantic_check,
    validate as validate_v242,
)

ROOT = Path(__file__).resolve().parents[2]


class CapabilityUse(BaseModel):
    capability: Literal["overtime", "workforce", "payroll"]
    usage: Literal["SUBJECT", "RESULT", "GROUP", "FILTER", "ORDER"]
    reason: str


class ScopeSelectionV243(BaseModel):
    selected: list[CapabilityUse] = Field(default_factory=list)


SCOPE_PROMPT_V243 = """Select the MINIMUM conceptual capabilities required by what the user explicitly asks to analyze, return, group, filter, or order. Every selected capability needs a concrete usage and reason tied to the user's request. Do not include a capability merely because its entities are commonly related in the source system. Overtime amount/date only requires overtime. Overtime by department requires overtime + workforce because department is explicitly requested. Listing/latest employees requires workforce. The word period/month/year never implies payroll. Do not decide fields, joins, entities, answerability, SQL, or provider syntax."""

INTENT_PROMPT_V243 = INTENT_PROMPT + """

PHASE 2.4.3 STRICTNESS:
- result_fields contains ONLY attributes the user explicitly names. If the user asks to list records but names no output attributes, result_fields MUST be empty; platform default fields are applied later.
- Do not add helpful/conventional fields just because they are visible in the scoped catalog.
- Each temporal condition MUST use fields belonging only to its kind:
  EXPLICIT_DATE_RANGE -> start_inclusive,end_exclusive
  EXPLICIT_YEAR -> year
  EXPLICIT_MONTH -> year,month
  EXPLICIT_MONTH_LIST -> year,months
  RELATIVE_RANGE -> relative_start,relative_end
  DERIVED_VALUE -> derivation,operator,value or values
  CALENDAR_PREDICATE -> predicate
- Never populate properties from another temporal kind.
- Never duplicate equivalent temporal conditions.
"""


def capabilities(scope: ScopeSelectionV243) -> list[str]:
    return sorted({item.capability for item in scope.selected})


def temporal_kind_errors(item) -> list[str]:
    fields = {
        "start_inclusive": item.start_inclusive,
        "end_exclusive": item.end_exclusive,
        "year": item.year,
        "month": item.month,
        "months": item.months,
        "relative_start": item.relative_start,
        "relative_end": item.relative_end,
        "derivation": item.derivation,
        "operator": item.operator,
        "value": item.value,
        "values": item.values,
        "predicate": item.predicate,
    }
    present = {k for k, v in fields.items() if v not in (None, [], "")}
    allowed = {
        "EXPLICIT_DATE_RANGE": {"start_inclusive", "end_exclusive"},
        "EXPLICIT_YEAR": {"year"},
        "EXPLICIT_MONTH": {"year", "month"},
        "EXPLICIT_MONTH_LIST": {"year", "months"},
        "RELATIVE_RANGE": {"relative_start", "relative_end"},
        "DERIVED_VALUE": {"derivation", "operator", "value", "values"},
        "CALENDAR_PREDICATE": {"predicate"},
    }[item.kind]
    required = {
        "EXPLICIT_DATE_RANGE": {"start_inclusive", "end_exclusive"},
        "EXPLICIT_YEAR": {"year"},
        "EXPLICIT_MONTH": {"year", "month"},
        "EXPLICIT_MONTH_LIST": {"year", "months"},
        "RELATIVE_RANGE": {"relative_start", "relative_end"},
        "DERIVED_VALUE": {"derivation", "operator"},
        "CALENDAR_PREDICATE": {"predicate"},
    }[item.kind]
    errors = [f"TEMPORAL_KIND_EXTRA_FIELD:{item.kind}:{name}" for name in sorted(present - allowed)]
    errors += [f"TEMPORAL_KIND_MISSING_FIELD:{item.kind}:{name}" for name in sorted(required - present)]
    if item.kind == "DERIVED_VALUE":
        if item.operator == "EQ" and item.value is None:
            errors.append("TEMPORAL_KIND_MISSING_FIELD:DERIVED_VALUE:value")
        if item.operator == "IN" and not item.values:
            errors.append("TEMPORAL_KIND_MISSING_FIELD:DERIVED_VALUE:values")
        if item.operator == "EQ" and item.values:
            errors.append("TEMPORAL_KIND_EXTRA_FIELD:DERIVED_VALUE:values")
        if item.operator == "IN" and item.value is not None:
            errors.append("TEMPORAL_KIND_EXTRA_FIELD:DERIVED_VALUE:value")
    return errors


def validate(scope: ScopeSelectionV243, intent: SemanticQueryIntentV242):
    fake_scope = type("Scope", (), {"capabilities": capabilities(scope)})()
    result = validate_v242(fake_scope, intent)
    extra = []
    for item in intent.temporal_conditions:
        extra.extend(temporal_kind_errors(item))
    result["errors"] = sorted(set(result.get("errors", []) + extra))
    result["scope_uses"] = [item.model_dump(mode="json") for item in scope.selected]
    return result


def check(case, scope, intent, validation):
    fake_scope = type("Scope", (), {"capabilities": capabilities(scope)})()
    ok, differences = semantic_check(case, fake_scope, intent, validation)
    return ok and not validation["errors"], sorted(set(differences + validation["errors"]))


def load_cases(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(cases, repetitions: int, output: Path, model_name: str):
    model = OpenAIStructuredModel(api_key=os.environ.get("OPENAI_API_KEY"), model=model_name, timeout_seconds=60, max_retries=0, max_output_tokens=4096)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    descriptions = {name: data["description"] for name, data in CAPABILITIES.items()}
    for case in cases:
        for repetition in range(1, repetitions + 1):
            started = time.monotonic()
            row = {"attempt_id": str(uuid.uuid4()), "question_id": case["id"], "question": case["question"], "repetition": repetition}
            try:
                scope = model.parse(purpose=SCOPE_PROMPT_V243, instructions="Capability catalog: " + json.dumps(descriptions, ensure_ascii=False) + "\nQuestion: " + case["question"], output_model=ScopeSelectionV243)
                cats = capabilities(scope)
                catalog = scoped_catalog(cats)
                intent = model.parse(purpose=INTENT_PROMPT_V243, instructions="Provider temporal context: " + json.dumps({"source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE}) + "\nType capabilities: " + json.dumps(TYPE_CAPABILITIES) + "\nScoped conceptual fields: " + json.dumps(catalog["fields"], ensure_ascii=False) + "\nDefault result fields are platform metadata; do NOT copy them into result_fields unless the user explicitly names those attributes: " + json.dumps(catalog["default_result_fields"], ensure_ascii=False) + "\nQuestion: " + case["question"], output_model=SemanticQueryIntentV242)
                validation = validate(scope, intent)
                ok, differences = check(case, scope, intent, validation)
                row.update({"structured_output_success": True, "scope": scope.model_dump(mode="json"), "capabilities": cats, "scoped_fields": sorted(catalog["fields"]), "raw_intent": intent.model_dump(mode="json"), "validation": validation, "derived_result_mode": derived_result_mode(intent), "derived_answerability": derived_answerability(intent), "derived_entities": derived_entities(intent), "normalized_temporal": normalize_temporal(intent), "eloquent_like": render_eloquent_like(intent, validation), "semantic_success": ok, "semantic_differences": differences})
            except Exception as exc:
                row.update({"structured_output_success": False, "semantic_success": False, "semantic_differences": [model.last_failure_class or "MODEL_FAILURE"], "exception_class": type(exc).__name__, "error": str(exc)[:300]})
            row["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("question_id", "repetition", "semantic_success", "semantic_differences", "latency_ms")}, ensure_ascii=False), flush=True)
    (output / "raw_responses.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    failures = Counter(error for row in rows for error in row.get("semantic_differences", []))
    metrics = {"total": len(rows), "structured_output_success_rate": sum(bool(x.get("structured_output_success")) for x in rows) / len(rows), "semantic_success_rate": sum(bool(x.get("semantic_success")) for x in rows) / len(rows), "failure_distribution": dict(failures)}
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"created_at": datetime.utcnow().isoformat() + "Z", "phase": "2.4.3", "model": model_name, "source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE, "cases": len(cases), "repetitions": repetitions}, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=ROOT / "evaluation/spikes/semantic_query_dsl_phase243_cases.jsonl")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    run(load_cases(args.cases), args.repetitions, args.output, args.model)


if __name__ == "__main__":
    main()

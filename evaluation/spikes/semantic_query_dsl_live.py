"""Live OpenAI reliability probe for the isolated Semantic Query DSL spike.

This file is evaluation-only. It deliberately stops after OpenAI structured
output and deterministic DSL validation; it does not call MCP or SQL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_spike import (
    CATALOG,
    SemanticQueryDSL,
    TemporalExpression,
    equivalent_key,
)


ROOT = Path(__file__).resolve().parents[2]
CASES = Path(__file__).with_name("semantic_query_dsl_cases.jsonl")
PROMPT = """You translate the user question into the provided Semantic Query DSL.
Return only the DSL object. Do not output entities or relationships: entities are
derived deterministically from qualified conceptual references.

Use only conceptual field references and only fields present in the catalog.
Never invent fields, entities, relationships, SQL, tables, columns, or provider
syntax. A calendar period is a YEAR_MONTH value with integer year and month.
Do not use payroll_period.code for an overtime question; use the temporal field
declared for the analytical subject. Keep temporal meaning in the temporal
expression, not in an extra temporal filter. The catalog metadata describes
which dimensions/operators/windows/calendar positions each field supports.
"""


class LiveFilter(BaseModel):
    field: str
    operator: str
    value: str | int | None = None


class LiveDSL(BaseModel):
    goal: str
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[LiveFilter] = Field(default_factory=list)
    temporal: TemporalExpression | None = None


def enriched_catalog() -> dict[str, Any]:
    return {
        "overtime": {
            "fields": {
                "overtime.approved_minutes": {
                    "data_type": "integer", "semantic_type": "duration_minutes", "unit": "minutes"
                },
                "overtime.work_date": {
                    "data_type": "date", "semantic_type": "calendar_date", "granularity": "day",
                    "supported_dimensions": ["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEKDAY"],
                    "supported_operators": ["EQ", "IN", "BETWEEN", "GT", "GTE", "LT", "LTE"],
                    "supported_windows": ["CURRENT_MONTH", "PREVIOUS_MONTH", "CURRENT_YEAR", "YEAR_TO_DATE", "LAST_N_MONTHS"],
                    "supported_calendar_positions": ["FIRST_DAY_OF_MONTH", "LAST_DAY_OF_MONTH"],
                },
            }
        },
        "employee": {"fields": {"employee.employee_code": {"data_type": "string", "semantic_type": "identifier"}}},
        "department": {"fields": {"department.name": {"data_type": "string", "semantic_type": "label"}}},
        "payroll": {"fields": {"payroll.net_amount": {"data_type": "numeric", "semantic_type": "currency"}}},
        "payroll_period": {"fields": {"payroll_period.code": {
            "data_type": "string", "semantic_type": "period_identifier", "granularity": "month",
            "supported_dimensions": ["YEAR_MONTH"], "supported_operators": ["EQ", "IN"]
        }}},
    }


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def expected_key(case: dict[str, Any]) -> tuple[Any, ...]:
    return equivalent_key(SemanticQueryDSL.model_validate(case["expected_dsl"]))


def validate(raw: dict[str, Any]) -> dict[str, Any]:
    dsl = LiveDSL.model_validate(raw)
    temporal = dsl.temporal
    fields = [*dsl.metrics, *dsl.dimensions, *(f.field for f in dsl.filters)]
    temporal_data = temporal.model_dump(mode="json") if isinstance(temporal, BaseModel) else temporal
    if isinstance(temporal_data, dict) and temporal_data.get("field"):
        fields.append(temporal_data["field"])
    field_valid = all(field in CATALOG for field in fields)
    temporal_valid = False
    value_shape_valid = True
    if temporal is None:
        temporal_valid = True
    elif isinstance(temporal_data, dict):
        field = temporal_data.get("field")
        dimension = temporal_data.get("dimension")
        metadata = CATALOG.get(field, {})
        temporal_valid = bool(metadata and dimension in metadata.get("dimensions", []))
        if dimension == "YEAR_MONTH":
            for value in temporal_data.get("values", []):
                if not isinstance(value, dict) or set(value) != {"year", "month"}:
                    value_shape_valid = False
    entities = sorted({field.split(".", 1)[0] for field in fields if "." in field})
    payroll = any(field.startswith("payroll") for field in fields)
    return {
        "field_catalog_valid": field_valid,
        "temporal_valid": temporal_valid,
        "value_shape_valid": value_shape_valid,
        "derived_entities": entities,
        "payroll_contamination": "overtime" in entities and payroll,
    }


def semantic_result(case: dict[str, Any], raw: dict[str, Any], checks: dict[str, Any]) -> tuple[bool, str | None]:
    expected = expected_key(case)
    actual = equivalent_key(SemanticQueryDSL.model_validate(raw))
    if not checks["field_catalog_valid"]:
        return False, "UNKNOWN_FIELD"
    if not checks["temporal_valid"]:
        return False, "UNSUPPORTED_DIMENSION"
    if not checks["value_shape_valid"]:
        return False, "WRONG_VALUE"
    if checks["payroll_contamination"] and case["expected_dsl"].get("goal", "").startswith("overtime"):
        return False, "TEMPORAL_SEMANTIC_CONTAMINATION"
    if actual != expected:
        return False, "SEMANTIC_EQUIVALENCE_FAILURE"
    return True, None


def run(cases: list[dict[str, Any]], repetitions: int, output: Path, model_name: str) -> None:
    model = OpenAIStructuredModel(
        api_key=os.environ.get("OPENAI_API_KEY"), model=model_name,
        timeout_seconds=float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "60")),
        max_retries=0, max_output_tokens=int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "2048")),
    )
    output.mkdir(parents=True, exist_ok=False)
    attempts: list[dict[str, Any]] = []
    catalog = enriched_catalog()
    for case in cases:
        for repetition in range(1, repetitions + 1):
            started = time.monotonic()
            record: dict[str, Any] = {
                "attempt_id": str(uuid.uuid4()), "question_id": case["id"],
                "question": case["question"], "repetition": repetition,
                "model": model.model_name, "category": case.get("category", "unspecified"),
            }
            try:
                result = model.parse(
                    purpose=PROMPT,
                    instructions=("Experimental conceptual catalog:\n" + json.dumps(catalog, ensure_ascii=False)
                                  + "\nQuestion: " + case["question"]),
                    output_model=LiveDSL,
                )
                raw = result.model_dump(mode="json")
                checks = validate(raw)
                ok, failure = semantic_result(case, raw, checks)
                record.update({"structured_output_success": True, "raw_structured_output": raw,
                               "validation": checks, "semantic_success": ok, "failure_class": failure,
                               "response_diagnostics": model.last_response_diagnostics})
            except Exception as exc:
                record.update({"structured_output_success": False, "semantic_success": False,
                               "failure_class": model.last_failure_class or "UNKNOWN_MODEL_FAILURE",
                               "exception_class": type(exc).__name__,
                               "validation_error_summary": str(exc)[:240],
                               "response_diagnostics": model.last_response_diagnostics})
            record["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            attempts.append(record)
            print(json.dumps({k: record.get(k) for k in ("question_id", "repetition", "structured_output_success", "semantic_success", "failure_class", "latency_ms")}), flush=True)
    raw_path = output / "raw_responses.jsonl"
    raw_path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in attempts) + "\n", encoding="utf-8")
    counts = Counter(x.get("failure_class") for x in attempts if x.get("failure_class"))
    metrics = {
        "total": len(attempts), "structured_output_success_rate": sum(x["structured_output_success"] for x in attempts) / len(attempts),
        "semantic_success_rate": sum(x["semantic_success"] for x in attempts) / len(attempts),
        "failure_counts": dict(counts),
        "field_catalog_validity_rate": sum(bool(x.get("validation", {}).get("field_catalog_valid")) for x in attempts) / len(attempts),
        "temporal_dimension_validity_rate": sum(bool(x.get("validation", {}).get("temporal_valid")) for x in attempts) / len(attempts),
        "field_derived_entity_accuracy": sum(x.get("validation", {}).get("derived_entities") == sorted({f.split(".", 1)[0] for f in case["expected_dsl"].get("metrics", []) + case["expected_dsl"].get("dimensions", []) if "." in f}) for x, case in zip(attempts, [c for c in cases for _ in range(repetitions)])) / len(attempts),
        "overtime_payroll_contamination_rate": sum(bool(x.get("validation", {}).get("payroll_contamination")) for x in attempts) / len(attempts),
        "per_question": {},
    }
    for case in cases:
        rows = [x for x in attempts if x["question_id"] == case["id"]]
        fingerprints = Counter(str(equivalent_key(SemanticQueryDSL.model_validate(x["raw_structured_output"]))) for x in rows if x.get("raw_structured_output"))
        metrics["per_question"][case["id"]] = {
            "attempts": len(rows), "structured_success": sum(x["structured_output_success"] for x in rows),
            "semantic_success": sum(x["semantic_success"] for x in rows), "fingerprints": fingerprints,
            "fingerprint_consistency": (fingerprints.most_common(1)[0][1] / len(rows)) if fingerprints else 0,
        }
    manifest = {"run_type": "semantic_query_dsl_live", "created_at": datetime.now(UTC).isoformat(),
                "attempts": len(attempts), "repetitions": repetitions, "model": model.model_name,
                "mcp_execution": False, "retries": 0, "cases": [c["id"] for c in cases],
                "catalog_type": "experimental_enriched_conceptual", "secrets_stored": False,
                "raw_responses_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest()}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False, default=list) + "\n", encoding="utf-8")
    (output / "normalized_results.jsonl").write_text("\n".join(json.dumps({"attempt_id": x["attempt_id"], "question_id": x["question_id"], "semantic_success": x["semantic_success"], "validation": x.get("validation"), "failure_class": x.get("failure_class")}, ensure_ascii=False) for x in attempts) + "\n", encoding="utf-8")
    (output / "failures.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in attempts if not x["semantic_success"]) + "\n", encoding="utf-8")
    (output / "report.md").write_text("# Live Semantic Query DSL reliability\n\nOpenAI structured-output calls only; no MCP or SQL execution.\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "metrics": metrics}, indent=2, ensure_ascii=False, default=list))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    run(load_cases(args.cases), args.repetitions, args.output, args.model)


if __name__ == "__main__":
    main()

"""Phase 2.1 live probe: contextual, mode-separated Semantic Query DSL.

Evaluation-only. It calls the existing OpenAIStructuredModel and stops before
MCP/SQL. Relative windows are normalized deterministically after parsing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_spike import CATALOG


ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATE = date(2026, 8, 30)
SOURCE_TIMEZONE = "UTC"
WINDOW_TYPES = Literal[
    "CURRENT_MONTH", "PREVIOUS_MONTH", "CURRENT_YEAR", "YEAR_TO_DATE",
    "LAST_N_MONTHS", "SAME_MONTH_PREVIOUS_YEARS"
]
DIMENSIONS = Literal[
    "YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY", "TIME_OF_DAY"
]
OPERATORS = Literal["EQ", "IN", "BETWEEN", "GT", "GTE", "LT", "LTE"]


class PeriodValue(BaseModel):
    year: int = Field(ge=1)
    month: int = Field(ge=1, le=12)


class RelativeWindow(BaseModel):
    type: WINDOW_TYPES
    count: int | None = Field(default=None, ge=1)


class TemporalExpression(BaseModel):
    mode: Literal["EXPLICIT", "RELATIVE"]
    field: str
    dimension: DIMENSIONS
    operator: OPERATORS | None = None
    values: list[PeriodValue | int | str] = Field(default_factory=list)
    window: RelativeWindow | None = None
    calendar_position: Literal["FIRST_DAY_OF_MONTH", "LAST_DAY_OF_MONTH"] | None = None


class TemporalGrouping(BaseModel):
    field: str
    dimension: DIMENSIONS


class TemporalComparison(BaseModel):
    field: str
    dimension: DIMENSIONS
    left: RelativeWindow
    right: RelativeWindow


class Filter(BaseModel):
    field: str
    operator: str
    value: str | int | None = None


class Phase21DSL(BaseModel):
    goal: str
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    temporal: TemporalExpression | None = None
    temporal_grouping: TemporalGrouping | None = None
    comparison: TemporalComparison | None = None


PROMPT = """Translate the user's analytical question into this provider-neutral Semantic Query DSL.
Return only the typed DSL object. Do not output entities or relationships; they are derived
from qualified references. Use only conceptual fields present in the catalog. Never output
SQL, tables, physical columns, provider syntax, or invented identifiers.

Analytical dimensions are grouping/breakdown references such as employee.employee_code or
department.name. Do not put a temporal field in dimensions merely because it is used to
filter time. Use temporal_grouping only when the user asks 'by month/year/etc.'.

Temporal filtering is discriminated: mode EXPLICIT has values and no window; mode RELATIVE
has a window and no values. Never mix them. Relative windows must remain symbolic; do not
materialize dates from the provider context. Explicit periods must use PeriodValue objects.
CURRENT_MONTH and PREVIOUS_MONTH are windows, not explicit values. A comparison uses the
comparison object with left/right windows. Calendar position is separate from dimension.

Provider temporal context is supplied as authoritative context for interpreting words such
as current and previous, but relative windows must remain symbolic in your output.
"""


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def enriched_catalog() -> dict[str, Any]:
    return {
        "provider_temporal_context": {"source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE},
        "fields": {
            "overtime.work_date": {
                "data_type": "date", "semantic_type": "calendar_date", "granularity": "day",
                "supported_dimensions": ["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY"],
                "supported_operators": ["EQ", "IN", "BETWEEN", "GT", "GTE", "LT", "LTE"],
                "supported_windows": ["CURRENT_MONTH", "PREVIOUS_MONTH", "CURRENT_YEAR", "YEAR_TO_DATE", "LAST_N_MONTHS", "SAME_MONTH_PREVIOUS_YEARS"],
                "supported_calendar_positions": ["FIRST_DAY_OF_MONTH", "LAST_DAY_OF_MONTH"],
            },
            "overtime.approved_minutes": {"data_type": "integer", "semantic_type": "duration_minutes", "unit": "minutes"},
            "employee.employee_code": {"data_type": "string", "semantic_type": "identifier"},
            "department.name": {"data_type": "string", "semantic_type": "label"},
            "payroll.net_amount": {"data_type": "numeric", "semantic_type": "currency"},
            "payroll_period.code": {"data_type": "string", "semantic_type": "period_identifier", "granularity": "month", "supported_dimensions": ["YEAR_MONTH"], "supported_operators": ["EQ", "IN"]},
        },
    }


def refs(dsl: Phase21DSL) -> list[str]:
    result = [*dsl.metrics, *dsl.dimensions, *(item.field for item in dsl.filters)]
    if dsl.temporal:
        result.append(dsl.temporal.field)
    if dsl.temporal_grouping:
        result.append(dsl.temporal_grouping.field)
    if dsl.comparison:
        result.append(dsl.comparison.field)
    return result


def derived_entities(dsl: Phase21DSL) -> list[str]:
    return sorted({ref.split(".", 1)[0] for ref in refs(dsl) if "." in ref})


def temporal_data(dsl: Phase21DSL) -> dict[str, Any] | None:
    return dsl.temporal.model_dump(mode="json") if dsl.temporal else None


def normalize_relative(dsl: Phase21DSL, source: date = SOURCE_DATE) -> dict[str, Any]:
    value = dsl.model_dump(mode="json")
    temporal = temporal_data(dsl)
    if temporal and temporal["mode"] == "RELATIVE":
        window = temporal["window"]["type"]
        if window == "CURRENT_MONTH":
            value["canonical_temporal"] = {"kind": "YEAR_MONTH", "values": [{"year": source.year, "month": source.month}]}
        elif window == "PREVIOUS_MONTH":
            month = source.month - 1 or 12
            year = source.year - (1 if source.month == 1 else 0)
            value["canonical_temporal"] = {"kind": "YEAR_MONTH", "values": [{"year": year, "month": month}]}
        elif window == "CURRENT_YEAR":
            value["canonical_temporal"] = {"kind": "YEAR", "values": [source.year]}
        elif window == "YEAR_TO_DATE":
            value["canonical_temporal"] = {"kind": "DATE_RANGE", "start": f"{source.year:04d}-01-01", "end": source.isoformat()}
        else:
            value["canonical_temporal"] = {"kind": "RELATIVE_WINDOW", "type": window, "source_date": source.isoformat()}
    if dsl.comparison:
        current = {"year": source.year, "month": source.month}
        month = source.month - 1 or 12
        previous = {"year": source.year - (1 if source.month == 1 else 0), "month": month}
        value["canonical_comparison"] = {"left": current, "right": previous}
    return value


def validate(dsl: Phase21DSL) -> dict[str, Any]:
    field_refs = refs(dsl)
    field_valid = all(ref in CATALOG for ref in field_refs)
    temporal = temporal_data(dsl)
    temporal_valid = True
    mode_valid = True
    window_valid = True
    explicit_values_valid = True
    if temporal:
        metadata = enriched_catalog()["fields"].get(temporal["field"], {})
        temporal_valid = temporal["dimension"] in metadata.get("supported_dimensions", [])
        if temporal["mode"] == "EXPLICIT":
            explicit_values_valid = temporal.get("window") is None
            if temporal["dimension"] == "YEAR_MONTH":
                explicit_values_valid = all(isinstance(item, dict) and set(item) == {"year", "month"} for item in temporal["values"])
        else:
            mode_valid = not temporal.get("values") and temporal.get("operator") is None
            window_valid = temporal["window"]["type"] in metadata.get("supported_windows", [])
    extra_temporal_dimension = bool(dsl.temporal and dsl.temporal.field in dsl.dimensions)
    payroll_contamination = any(ref.startswith("payroll") for ref in field_refs) and "overtime" in derived_entities(dsl)
    return {"field_valid": field_valid, "temporal_valid": temporal_valid, "mode_valid": mode_valid,
            "window_valid": window_valid, "explicit_values_valid": explicit_values_valid,
            "extra_temporal_dimension": extra_temporal_dimension, "derived_entities": derived_entities(dsl),
            "payroll_contamination": payroll_contamination}


def expected_shape(case: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected_dsl"]
    temporal = expected.get("temporal")
    if temporal and temporal.get("mode") == "RELATIVE":
        return {"relative": {"field": temporal["field"], "dimension": temporal["dimension"], "window": temporal["window"]["type"]}}
    if temporal and temporal.get("mode") == "EXPLICIT":
        return {"explicit": {"field": temporal["field"], "dimension": temporal["dimension"], "operator": temporal.get("operator"), "values": temporal.get("values", [])}}
    if temporal and temporal.get("window"):
        raw_window = temporal["window"]
        if raw_window == "CURRENT_MONTH,PREVIOUS_MONTH":
            return {"comparison": {"field": temporal["field"], "dimension": temporal["dimension"], "left": "CURRENT_MONTH", "right": "PREVIOUS_MONTH"}}
        return {"relative": {"field": temporal["field"], "dimension": temporal["dimension"], "window": raw_window}}
    if temporal:
        return {"explicit": {"field": temporal["field"], "dimension": temporal["dimension"], "operator": temporal["operator"], "values": temporal.get("values", [])}}
    return {"non_temporal": True}


def semantic_success(case: dict[str, Any], dsl: Phase21DSL, checks: dict[str, Any]) -> tuple[bool, str | None]:
    if not checks["field_valid"]:
        return False, "UNKNOWN_FIELD"
    if not checks["temporal_valid"]:
        return False, "UNSUPPORTED_DIMENSION"
    if not checks["mode_valid"] or not checks["window_valid"]:
        return False, "WRONG_MODE"
    if not checks["explicit_values_valid"]:
        return False, "WRONG_VALUE"
    if checks["extra_temporal_dimension"]:
        return False, "UNNECESSARY_REFERENCE"
    expected = expected_shape(case)
    actual = dsl.model_dump(mode="json")
    expected_dsl = case["expected_dsl"]
    if sorted(actual.get("metrics", [])) != sorted(expected_dsl.get("metrics", [])):
        return False, "MISSING_REQUIRED_REFERENCE" if not actual.get("metrics") else "SEMANTIC_EQUIVALENCE_FAILURE"
    if sorted(actual.get("dimensions", [])) != sorted(expected_dsl.get("dimensions", [])):
        return False, "UNNECESSARY_REFERENCE" if len(actual.get("dimensions", [])) > len(expected_dsl.get("dimensions", [])) else "MISSING_REQUIRED_REFERENCE"
    expected_filters = expected_dsl.get("filters", [])
    if actual.get("filters", []) != expected_filters:
        return False, "SEMANTIC_EQUIVALENCE_FAILURE"
    expected_grouping = expected_dsl.get("temporal_grouping")
    if (actual.get("temporal_grouping") or None) != (expected_grouping or None):
        return False, "UNNECESSARY_REFERENCE" if actual.get("temporal_grouping") else "MISSING_REQUIRED_REFERENCE"
    temporal = actual.get("temporal")
    if "comparison" in expected:
        comparison = actual.get("comparison") or {}
        ok = comparison.get("field") == expected["comparison"]["field"] and comparison.get("dimension") == expected["comparison"]["dimension"] and comparison.get("left", {}).get("type") == expected["comparison"]["left"] and comparison.get("right", {}).get("type") == expected["comparison"]["right"]
    elif "relative" in expected:
        ok = bool(temporal and temporal.get("mode") == "RELATIVE" and temporal.get("field") == expected["relative"]["field"] and temporal.get("dimension") == expected["relative"]["dimension"] and temporal.get("window", {}).get("type") == expected["relative"]["window"])
    elif "explicit" in expected:
        ok = bool(temporal and temporal.get("mode") == "EXPLICIT" and temporal.get("field") == expected["explicit"]["field"] and temporal.get("dimension") == expected["explicit"]["dimension"] and temporal.get("operator") == expected["explicit"]["operator"] and temporal.get("values") == expected["explicit"]["values"])
    else:
        ok = temporal is None
    return (True, None) if ok else (False, "SEMANTIC_EQUIVALENCE_FAILURE")


def run(cases: list[dict[str, Any]], repetitions: int, output: Path, model_name: str) -> None:
    model = OpenAIStructuredModel(api_key=os.environ.get("OPENAI_API_KEY"), model=model_name,
                                  timeout_seconds=60, max_retries=0, max_output_tokens=4096)
    output.mkdir(parents=True, exist_ok=False)
    catalog = enriched_catalog()
    attempts: list[dict[str, Any]] = []
    for case in cases:
        for repetition in range(1, repetitions + 1):
            started = time.monotonic()
            row: dict[str, Any] = {"attempt_id": str(uuid.uuid4()), "question_id": case["id"], "question": case["question"], "repetition": repetition, "model": model.model_name}
            try:
                parsed = model.parse(purpose=PROMPT, instructions="Provider temporal context: " + json.dumps(catalog["provider_temporal_context"]) + "\nCatalog: " + json.dumps(catalog["fields"], ensure_ascii=False) + "\nQuestion: " + case["question"], output_model=Phase21DSL)
                checks = validate(parsed)
                raw_ok, failure = semantic_success(case, parsed, checks)
                row.update({"structured_output_success": True, "raw_dsl": parsed.model_dump(mode="json"), "raw_validation": checks, "raw_semantic_success": raw_ok, "raw_failure": failure, "normalized_dsl": normalize_relative(parsed, SOURCE_DATE), "response_diagnostics": model.last_response_diagnostics})
            except Exception as exc:
                row.update({"structured_output_success": False, "raw_semantic_success": False, "raw_failure": model.last_failure_class or "UNKNOWN_MODEL_FAILURE", "exception_class": type(exc).__name__, "validation_error_summary": str(exc)[:240], "response_diagnostics": model.last_response_diagnostics})
            row["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            attempts.append(row)
            print(json.dumps({k: row.get(k) for k in ("question_id", "repetition", "structured_output_success", "raw_semantic_success", "raw_failure", "latency_ms")}), flush=True)
    raw_path = output / "raw_responses.jsonl"
    raw_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in attempts) + "\n", encoding="utf-8")
    metrics = {"total": len(attempts), "structured_output_success_rate": sum(row["structured_output_success"] for row in attempts) / len(attempts), "raw_semantic_success_rate": sum(row["raw_semantic_success"] for row in attempts) / len(attempts), "failure_counts": dict(Counter(row.get("raw_failure") for row in attempts if row.get("raw_failure"))), "source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE, "per_question": {}}
    for case in cases:
        rows = [row for row in attempts if row["question_id"] == case["id"]]
        fps = Counter(json.dumps(row.get("raw_dsl"), sort_keys=True, ensure_ascii=False) for row in rows if row.get("raw_dsl"))
        metrics["per_question"][case["id"]] = {"attempts": len(rows), "structured_success": sum(row["structured_output_success"] for row in rows), "raw_semantic_success": sum(row["raw_semantic_success"] for row in rows), "fingerprint_consistency": fps.most_common(1)[0][1] / len(rows) if fps else 0, "fingerprints": fps}
    manifest = {"run_type": "semantic_query_dsl_phase21", "created_at": datetime.now(UTC).isoformat(), "model": model.model_name, "retries": 0, "mcp_execution": False, "source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE, "attempts": len(attempts), "catalog": "experimental_enriched_conceptual", "raw_responses_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(), "secrets_stored": False}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False, default=list) + "\n", encoding="utf-8")
    (output / "normalized_results.jsonl").write_text("\n".join(json.dumps({"attempt_id": row["attempt_id"], "question_id": row["question_id"], "raw_semantic_success": row["raw_semantic_success"], "normalized_dsl": row.get("normalized_dsl"), "raw_failure": row.get("raw_failure")}, ensure_ascii=False) for row in attempts) + "\n", encoding="utf-8")
    (output / "failures.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in attempts if not row["raw_semantic_success"]) + "\n", encoding="utf-8")
    (output / "dataset.jsonl").write_text("\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n", encoding="utf-8")
    (output / "report.md").write_text("# Semantic Query DSL Phase 2.1\n\nLive OpenAI structured output, deterministic relative-window normalization, no MCP/SQL.\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "metrics": metrics}, indent=2, ensure_ascii=False, default=list))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("semantic_query_dsl_cases.jsonl"))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--source-date", default="2026-08-30")
    args = parser.parse_args()
    global SOURCE_DATE
    SOURCE_DATE = date.fromisoformat(args.source_date)
    run(load_cases(args.cases), args.repetitions, args.output, args.model)


if __name__ == "__main__":
    main()

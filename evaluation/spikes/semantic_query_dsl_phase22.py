"""Phase 2.2 isolated live spike for a smaller Semantic Query DSL.

This file is evaluation-only. It deliberately does not import or modify the
production AnalysisPlan, ConceptualQuery, temporal resolver, or MCP layers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from peopleops_api.analysis_workflow import OpenAIStructuredModel

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATE = date(2026, 8, 30)
SOURCE_TIMEZONE = "UTC"
CATALOG_FIELDS = {
    "overtime.work_date": {"type": "DATE", "semantic_type": "calendar_date"},
    "overtime.approved_minutes": {"type": "INTEGER", "semantic_type": "duration_minutes"},
    "employee.employee_code": {"type": "STRING", "semantic_type": "identifier"},
    "employee.id": {"type": "STRING", "semantic_type": "identifier"},
    "employee.status": {"type": "STRING", "semantic_type": "status"},
    "department.name": {"type": "STRING", "semantic_type": "label"},
    "payroll.net_amount": {"type": "DECIMAL", "semantic_type": "currency"},
    "payroll_period.code": {"type": "STRING", "semantic_type": "period_identifier"},
    "sale.date": {"type": "DATE", "semantic_type": "calendar_date"},
    "sales.amount": {"type": "DECIMAL", "semantic_type": "currency"},
    "operation.timestamp": {"type": "DATETIME", "semantic_type": "event_timestamp"},
    "operation.amount": {"type": "DECIMAL", "semantic_type": "currency"},
}
TYPE_CAPABILITIES = {
    "DATE": {
        "derivations": ["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY"],
        "operators": ["EQ", "IN", "BETWEEN", "GT", "GTE", "LT", "LTE"],
    },
    "DATETIME": {
        "derivations": ["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY", "TIME_OF_DAY"],
        "operators": ["EQ", "IN", "BETWEEN", "GT", "GTE", "LT", "LTE"],
    },
}
WINDOWS = ["CURRENT_MONTH", "PREVIOUS_MONTH", "CURRENT_YEAR", "YEAR_TO_DATE", "LAST_N_MONTHS", "LAST_N_YEARS", "SAME_MONTH_PREVIOUS_YEARS"]


class Metric(BaseModel):
    field: str
    aggregation: Literal["SUM", "COUNT", "AVG", "MIN", "MAX"] = "SUM"


class Predicate(BaseModel):
    field: str
    operator: Literal["EQ", "IN", "BETWEEN", "GT", "GTE", "LT", "LTE"]
    value: str | int | None = None
    values: list[str] = Field(default_factory=list)
    start: str | None = None
    end_exclusive: str | None = None
    relative_window: Literal["CURRENT_MONTH", "PREVIOUS_MONTH", "CURRENT_YEAR", "YEAR_TO_DATE", "LAST_N_MONTHS", "LAST_N_YEARS", "SAME_MONTH_PREVIOUS_YEARS"] | None = None
    relative_count: int | None = Field(default=None, ge=1)
    relative_end: Literal["TODAY", "PREVIOUS_MONTH_END"] | None = None
    derivation: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY", "TIME_OF_DAY"] | None = None
    calendar_position: Literal["FIRST_DAY_OF_MONTH", "LAST_DAY_OF_MONTH"] | None = None


class Grouping(BaseModel):
    field: str
    derivation: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY", "TIME_OF_DAY"] | None = None


class Ordering(BaseModel):
    field: str
    direction: Literal["ASC", "DESC"] = "ASC"


class Answerability(BaseModel):
    status: Literal["UNDERSTOOD_AND_EXECUTABLE", "NEEDS_CLARIFICATION", "UNSUPPORTED_QUERY"]
    reason: str | None = None


class SemanticQueryDSLv22(BaseModel):
    goal: str
    projections: list[str] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    filters: list[Predicate] = Field(default_factory=list)
    groupings: list[Grouping] = Field(default_factory=list)
    ordering: list[Ordering] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    answerability: Answerability


PROMPT = """Translate the question into the small provider-neutral Semantic Query DSL.
Return only the typed DSL object. Do not emit entities, relationships, SQL, tables, physical
columns, or provider syntax. Entities are derived from qualified references such as
overtime.approved_minutes; the model must not output an entities field.

The DSL mirrors logical query operations: projections, metrics, filters, groupings, ordering,
and limit. A filter selects rows; a grouping is only for breakdown/segmentation. Do not put a
date field in groupings unless the user explicitly asks 'by month', 'per month', or equivalent.

For DATE and DATETIME fields, use the general type capabilities in the catalog. For a concrete
calendar period, prefer a filter with start and end_exclusive. For relative periods, use only
relative_window and relative_count; never materialize dates from provider context. Do not mix
relative_window with start/end/values. calendar_position is separate from DAY_OF_MONTH.

Use payroll_period.code only when the user explicitly asks for a payroll-period identifier or
payroll-period analytics; it is a STRING period identifier, not a DATE. Keep the output minimal:
do not add employee or department dimensions unless requested. If the question is ambiguous or
unsupported by the declared catalog capabilities, use answerability instead of inventing a query.
"""


def catalog_payload() -> dict[str, Any]:
    return {"provider_temporal_context": {"source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE}, "type_capabilities": TYPE_CAPABILITIES, "fields": CATALOG_FIELDS}


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_dataset(path: Path, extra: Path | None) -> list[dict[str, Any]]:
    cases = load_cases(path)
    if extra:
        cases.extend(load_cases(extra))
    return cases


def refs(dsl: SemanticQueryDSLv22) -> list[str]:
    return [*dsl.projections, *(m.field for m in dsl.metrics), *(p.field for p in dsl.filters), *(g.field for g in dsl.groupings), *(o.field for o in dsl.ordering)]


def derived_entities(dsl: SemanticQueryDSLv22) -> list[str]:
    return sorted({ref.split(".", 1)[0] for ref in refs(dsl) if "." in ref})


def month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def add_months(value: date, amount: int) -> date:
    index = value.year * 12 + value.month - 1 + amount
    return date(index // 12, index % 12 + 1, 1)


def normalize_relative(dsl: SemanticQueryDSLv22, source: date = SOURCE_DATE) -> dict[str, Any]:
    result = dsl.model_dump(mode="json")
    canonical_filters = []
    for predicate in dsl.filters:
        item = predicate.model_dump(mode="json")
        window = predicate.relative_window
        if window:
            if window == "CURRENT_MONTH":
                start, end = month_start(source.year, source.month), add_months(month_start(source.year, source.month), 1)
            elif window == "PREVIOUS_MONTH":
                end = month_start(source.year, source.month)
                start = add_months(end, -1)
            elif window == "CURRENT_YEAR":
                start, end = date(source.year, 1, 1), date(source.year + 1, 1, 1)
            elif window == "YEAR_TO_DATE":
                start, end = date(source.year, 1, 1), source + timedelta(days=1)
            elif window == "LAST_N_MONTHS":
                count = predicate.relative_count or 1
                end = source + timedelta(days=1)
                start = add_months(month_start(source.year, source.month), -(count - 1))
            elif window == "LAST_N_YEARS":
                count = predicate.relative_count or 1
                start = date(source.year - count + 1, 1, 1)
                if predicate.relative_end == "PREVIOUS_MONTH_END":
                    end = month_start(source.year, source.month)
                else:
                    end = source + timedelta(days=1)
            else:
                count = predicate.relative_count or 1
                start, end = date(source.year - count, source.month, 1), date(source.year + 1, source.month, 1)
            item["canonical_range"] = {"start": start.isoformat(), "end_exclusive": end.isoformat()}
        canonical_filters.append(item)
    result["filters"] = canonical_filters
    result["derived_entities"] = derived_entities(dsl)
    return result


def validate(dsl: SemanticQueryDSLv22) -> dict[str, Any]:
    references = refs(dsl)
    field_valid = all(ref in CATALOG_FIELDS for ref in references)
    mixed_relative = any(p.relative_window and (p.start or p.end_exclusive or p.values) for p in dsl.filters)
    date_caps_valid = True
    for predicate in dsl.filters:
        metadata = CATALOG_FIELDS.get(predicate.field, {})
        caps = TYPE_CAPABILITIES.get(metadata.get("type"), {})
        if predicate.derivation and predicate.derivation not in caps.get("derivations", []):
            date_caps_valid = False
        if predicate.operator not in caps.get("operators", [predicate.operator]) and metadata.get("type") in TYPE_CAPABILITIES:
            date_caps_valid = False
        if predicate.relative_window and predicate.relative_window not in WINDOWS:
            date_caps_valid = False
    payroll_contamination = any(ref.startswith("payroll") for ref in references) and any(ref.startswith("overtime") for ref in references)
    return {"field_catalog_valid": field_valid, "date_capabilities_valid": date_caps_valid, "mixed_relative_explicit": mixed_relative, "derived_entities": derived_entities(dsl), "payroll_contamination": payroll_contamination}


def expected_case(case: dict[str, Any]) -> dict[str, Any]:
    if "expected_v22" in case:
        return case["expected_v22"]
    old = case.get("expected_dsl", {})
    expected = {"metrics": old.get("metrics", []), "groupings": [{"field": f} for f in old.get("dimensions", [])], "filters": old.get("filters", [])}
    temporal = old.get("temporal")
    if temporal:
        expected["temporal_field"] = temporal.get("field")
        expected["temporal_dimension"] = temporal.get("dimension")
        expected["temporal_operator"] = temporal.get("operator")
        expected["temporal_values"] = temporal.get("values", [])
        expected["relative_window"] = temporal.get("window")
    if old.get("temporal_grouping"):
        expected["temporal_grouping"] = old["temporal_grouping"]
    return expected


def semantic_check(case: dict[str, Any], dsl: SemanticQueryDSLv22, checks: dict[str, Any]) -> tuple[bool, str | None]:
    if dsl.answerability.status != "UNDERSTOOD_AND_EXECUTABLE":
        expected_status = expected_case(case).get("answerability", "UNDERSTOOD_AND_EXECUTABLE")
        return (True, None) if dsl.answerability.status == expected_status else (False, "ANSWERABILITY_MISMATCH")
    if not checks["field_catalog_valid"]:
        return False, "UNKNOWN_FIELD"
    if not checks["date_capabilities_valid"]:
        return False, "UNSUPPORTED_DATE_CAPABILITY"
    if checks["mixed_relative_explicit"]:
        return False, "MIXED_RELATIVE_EXPLICIT"
    expected = expected_case(case)
    actual_metrics = sorted(m.field for m in dsl.metrics)
    if actual_metrics != sorted(expected.get("metrics", [])):
        return False, "METRIC_MISMATCH"
    if "expected_v22" in case:
        predicates = dsl.filters
        expected_groupings = sorted((g["field"], g.get("derivation")) for g in expected.get("groupings", []))
        actual_groupings = sorted((g.field, g.derivation) for g in dsl.groupings)
        if actual_groupings != expected_groupings:
            return False, "FILTER_GROUPING_CONFUSION" if actual_groupings else "MISSING_GROUPING"
        if expected.get("relative_window"):
            relative = next((p for p in predicates if p.relative_window), None)
            if not relative or relative.relative_window != expected["relative_window"] or relative.relative_count != expected.get("relative_count") or relative.relative_end != expected.get("relative_end"):
                return False, "WRONG_RELATIVE_RANGE"
        if expected.get("date_range"):
            if not any(p.start == expected["date_range"][0] and p.end_exclusive == expected["date_range"][1] for p in predicates):
                return False, "WRONG_DATE_RANGE"
        if expected.get("month_filter"):
            if not any(p.start == "2026-01-01" and p.end_exclusive == "2026-02-01" for p in predicates):
                return False, "WRONG_DATE_RANGE"
        if expected.get("year_filter") and not any(p.start == f"{expected['year_filter']}-01-01" and p.end_exclusive == f"{expected['year_filter'] + 1}-01-01" for p in predicates):
            return False, "WRONG_DATE_RANGE"
        if expected.get("weekday") is not None and not any(p.derivation == "WEEKDAY" and p.value == expected["weekday"] for p in predicates):
            return False, "WRONG_DATE_DERIVATION"
        if expected.get("day_of_month") is not None and not any(p.derivation == "DAY_OF_MONTH" and p.value == expected["day_of_month"] for p in predicates):
            return False, "WRONG_DATE_DERIVATION"
        if expected.get("calendar_position") and not any(p.calendar_position == expected["calendar_position"] for p in predicates):
            return False, "WRONG_CALENDAR_POSITION"
        return True, None
    expected_groupings = sorted((g["field"], g.get("derivation")) for g in expected.get("groupings", []))
    actual_groupings = sorted((g.field, g.derivation) for g in dsl.groupings)
    if expected_groupings and actual_groupings != expected_groupings:
        return False, "FILTER_GROUPING_CONFUSION"
    if not expected_groupings and dsl.groupings:
        return False, "UNNECESSARY_REFERENCE"
    temporal = next((p for p in dsl.filters if p.field == expected.get("temporal_field")), None)
    if expected.get("temporal_field") and not temporal:
        return False, "MISSING_TEMPORAL_FILTER"
    if temporal:
        expected_window = expected.get("relative_window")
        if expected_window and isinstance(expected_window, str) and temporal.relative_window is None:
            return False, "WRONG_RELATIVE_RANGE"
        if expected_window and temporal.relative_window and isinstance(expected_window, str) and expected_window not in {expected_window, temporal.relative_window}:
            return False, "WRONG_RELATIVE_RANGE"
        expected_dim = expected.get("temporal_dimension")
        if expected_dim and temporal.derivation and temporal.derivation not in {expected_dim, "YEAR_MONTH" if expected_dim == "MONTH" else expected_dim}:
            return False, "WRONG_DATE_DERIVATION"
    if any(ref.startswith("payroll") for ref in refs(dsl)) and "overtime" in checks["derived_entities"]:
        return False, "PAYROLL_CONTAMINATION"
    return True, None


def run(cases: list[dict[str, Any]], repetitions: int, output: Path, model_name: str) -> None:
    model = OpenAIStructuredModel(api_key=os.environ.get("OPENAI_API_KEY"), model=model_name, timeout_seconds=60, max_retries=0, max_output_tokens=4096)
    output.mkdir(parents=True, exist_ok=False)
    catalog = catalog_payload()
    attempts = []
    for case in cases:
        for repetition in range(1, repetitions + 1):
            started = time.monotonic()
            row: dict[str, Any] = {"attempt_id": str(uuid.uuid4()), "question_id": case["id"], "question": case["question"], "repetition": repetition, "model": model.model_name}
            try:
                instructions = "ProviderTemporalContext: " + json.dumps(catalog["provider_temporal_context"]) + "\nCatalog: " + json.dumps(catalog, ensure_ascii=False) + "\nQuestion: " + case["question"]
                parsed = model.parse(purpose=PROMPT, instructions=instructions, output_model=SemanticQueryDSLv22)
                checks = validate(parsed)
                semantic_ok, failure = semantic_check(case, parsed, checks)
                row.update({"structured_output_success": True, "raw_dsl": parsed.model_dump(mode="json"), "validation": checks, "raw_semantic_success": semantic_ok, "failure": failure, "normalized_dsl": normalize_relative(parsed), "response_diagnostics": model.last_response_diagnostics})
            except Exception as exc:
                row.update({"structured_output_success": False, "raw_semantic_success": False, "failure": model.last_failure_class or "UNKNOWN_MODEL_FAILURE", "exception_class": type(exc).__name__, "validation_error_summary": str(exc)[:240], "response_diagnostics": model.last_response_diagnostics})
            row["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            attempts.append(row)
            print(json.dumps({k: row.get(k) for k in ("question_id", "repetition", "structured_output_success", "raw_semantic_success", "failure", "latency_ms")}), flush=True)
    raw_path = output / "raw_responses.jsonl"
    raw_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in attempts) + "\n", encoding="utf-8")
    by_question = {}
    for case in cases:
        rows = [r for r in attempts if r["question_id"] == case["id"]]
        fps = Counter(json.dumps({k: r["raw_dsl"].get(k) for k in ("metrics", "projections", "filters", "groupings", "ordering", "answerability")}, sort_keys=True, ensure_ascii=False) for r in rows if r.get("raw_dsl"))
        by_question[case["id"]] = {"attempts": len(rows), "structured": sum(r["structured_output_success"] for r in rows), "raw_semantic": sum(r["raw_semantic_success"] for r in rows), "fingerprint_consistency": fps.most_common(1)[0][1] / len(rows) if fps else 0, "failures": dict(Counter(r.get("failure") for r in rows if r.get("failure")))}
    metrics = {"total": len(attempts), "structured_output_success": sum(r["structured_output_success"] for r in attempts), "raw_semantic_success": sum(r["raw_semantic_success"] for r in attempts), "failure_counts": dict(Counter(r.get("failure") for r in attempts if r.get("failure"))), "average_latency_ms": round(sum(r["latency_ms"] for r in attempts) / len(attempts), 1), "source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE, "per_question": by_question}
    manifest = {"run_type": "semantic_query_dsl_phase22", "created_at": datetime.now(UTC).isoformat(), "model": model.model_name, "retries": 0, "mcp_execution": False, "provider_temporal_context": catalog["provider_temporal_context"], "attempts": len(attempts), "secrets_stored": False, "raw_responses_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest()}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "dataset.jsonl").write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")
    (output / "normalized_results.jsonl").write_text("\n".join(json.dumps({"attempt_id": r["attempt_id"], "question_id": r["question_id"], "normalized_dsl": r.get("normalized_dsl"), "raw_semantic_success": r["raw_semantic_success"], "failure": r.get("failure")}, ensure_ascii=False) for r in attempts) + "\n", encoding="utf-8")
    (output / "failures.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in attempts if not r["raw_semantic_success"]) + "\n", encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "report.md").write_text("# Semantic Query DSL Phase 2.2\n\nEvaluation-only live OpenAI spike; no MCP or SQL execution.\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "metrics": metrics}, indent=2, ensure_ascii=False))


def self_test() -> None:
    assert derived_entities(SemanticQueryDSLv22(goal="x", metrics=[Metric(field="overtime.approved_minutes")], filters=[Predicate(field="overtime.work_date", operator="BETWEEN", start="2026-01-01", end_exclusive="2026-02-01")], answerability=Answerability(status="UNDERSTOOD_AND_EXECUTABLE"))) == ["overtime"]
    dsl = SemanticQueryDSLv22(goal="x", metrics=[Metric(field="overtime.approved_minutes")], filters=[Predicate(field="overtime.work_date", operator="EQ", relative_window="CURRENT_MONTH")], answerability=Answerability(status="UNDERSTOOD_AND_EXECUTABLE"))
    assert normalize_relative(dsl, date(2026, 8, 30))["filters"][0]["canonical_range"] == {"start": "2026-08-01", "end_exclusive": "2026-09-01"}
    assert validate(SemanticQueryDSLv22(goal="x", metrics=[Metric(field="payroll.net_amount")], filters=[Predicate(field="payroll_period.code", operator="EQ", value="2026-01")], answerability=Answerability(status="UNDERSTOOD_AND_EXECUTABLE")))["payroll_contamination"] is False
    print("phase22 self-tests: PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("semantic_query_dsl_cases.jsonl"))
    parser.add_argument("--extra-cases", type=Path, default=Path(__file__).with_name("semantic_query_dsl_phase22_cases.jsonl"))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--source-date", default="2026-08-30")
    parser.add_argument("--no-extra", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    global SOURCE_DATE
    SOURCE_DATE = date.fromisoformat(args.source_date)
    if args.self_test:
        self_test()
    elif args.output:
        run(load_dataset(args.cases, None if args.no_extra else args.extra_cases), args.repetitions, args.output, args.model)


if __name__ == "__main__":
    main()

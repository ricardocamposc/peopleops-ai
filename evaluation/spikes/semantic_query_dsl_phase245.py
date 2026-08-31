"""Phase 2.4.5 — focused Semantic Query Intent reliability candidate.

Changes vs 2.4.4:
1. semantic_success is the primary gate;
2. deterministic canonicalization enforces non-semantic invariants;
3. ambiguous/unsupported intents cannot also carry executable query content;
4. relative time scopes keep only symbolic bounds;
5. monthly groupings canonicalize to YEAR_MONTH.

Capability scoping, payroll isolation, entity derivation, field operations,
time-scope/calendar separation, and Eloquent-like rendering remain inherited.
No MCP, SQL, or executable Eloquent is used.
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
from typing import Any

from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase242 import (
    CAPABILITIES,
    SOURCE_DATE,
    SOURCE_TIMEZONE,
    TYPE_CAPABILITIES,
    GroupBy,
    scoped_catalog,
)
from semantic_query_dsl_phase243 import ScopeSelectionV243
from semantic_query_dsl_phase244 import (
    CalendarPredicateFilter,
    DerivedCalendarFilter,
    SemanticQueryIntentV244,
    TimeScope,
    capabilities,
    derived_answerability,
    derived_entities,
    eloquent_like,
    normalize_time_scope,
    result_mode,
    scope_shape_errors,
    validate_operations,
)

ROOT = Path(__file__).resolve().parents[2]


SCOPE_PROMPT_V245 = """Select ONLY capabilities required by an explicit subject, result, grouping, filter, or ordering in the user's question.
Every selected capability must have one PRESENT use. Never select a capability speculatively, defensively, because it is related, because it may be useful, or because employee attributes could be needed later.
Overtime-only questions require only overtime. Overtime grouped/filtered by department requires overtime + workforce. Listing employees requires workforce. Period/month/year never imply payroll.
Do not select workforce merely because overtime belongs to employees. Do not decide fields, joins, SQL, entities, or answerability."""


INTENT_PROMPT_V245 = """Translate the question into the MINIMAL provider-neutral Semantic Query Intent using ONLY the scoped conceptual fields.

RESULTS:
- result_fields means ONLY attributes explicitly requested by the user to appear in the result.
- Never add useful/default/helpful fields. If the user asks to list records but names no output attributes, result_fields MUST be []. Platform metadata decides default fields later.
- measures contains analytical quantities only.
- A field used for measure, filter, grouping, ordering, or temporal scope does NOT automatically belong in result_fields.

GROUPING:
- group_by exists only when the user explicitly requests a breakdown/grouping.
- A temporal grouping requested as 'by month' MUST use YEAR_MONTH so month identity remains stable across years. Do not use MONTH merely because the current example happens to fit one year.
- Calendar filters such as WEEKDAY=MONDAY or DAY_OF_MONTH=15 are conditions, never groupings unless the user explicitly asks to group by them.

TIME:
- time_scope is the ONE interval/set limiting when data is considered.
- calendar filters express properties of dates inside that scope.
- Relative requests MUST use RELATIVE_RANGE with relative_start and relative_end. Never materialize relative dates into start_inclusive/end_exclusive.
- Current month: START_OF_CURRENT_MONTH +0 MONTH to START_OF_CURRENT_MONTH +1 MONTH.
- Previous month: START_OF_CURRENT_MONTH -1 MONTH to START_OF_CURRENT_MONTH +0 MONTH.
- Last N months including current: START_OF_CURRENT_MONTH -(N-1) MONTH to START_OF_CURRENT_MONTH +1 MONTH.
- Year through today: START_OF_CURRENT_YEAR to SOURCE_DATE with include_anchor_day=true.
- Last N years through today: SOURCE_DATE -N YEAR to SOURCE_DATE with include_anchor_day=true.
- January 2026 / 2026-01 / 202601 => EXPLICIT_MONTH(year=2026, month=1).
- During 2026 => EXPLICIT_YEAR(year=2026).

CALENDAR FILTERS:
- Every Monday => WEEKDAY EQ MONDAY.
- Day 15 of each month => DAY_OF_MONTH EQ 15.
- Last day of each month => IS_LAST_DAY_OF_MONTH.
Never enumerate dates when one calendar predicate/derived filter expresses the intent.

AMBIGUITY / UNSUPPORTED:
- If the request is materially ambiguous, record ambiguity and DO NOT build an executable query: result_fields=[], measures=[], time_scope=null, calendar filters=[], scalar_conditions=[], group_by=[], order_by=[], limit=null.
- 'previous period' without an established period unit is ambiguous. Do not assume month/year/payroll period.
- Apply the same empty-query rule when unsupported_reasons is non-empty.

Do not emit SQL, Eloquent/PHP, entities, relationships, physical schema, raw expressions, or fields outside scope."""


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _canonical_scope(scope: TimeScope | None) -> TimeScope | None:
    """Strip fields that are mechanically incompatible with the selected kind.

    This does not infer missing semantic information. Incomplete RELATIVE_RANGE
    scopes remain incomplete and fail preflight rather than being reconstructed
    from strings or absolute dates.
    """
    if scope is None:
        return None

    common = {"field": scope.field, "kind": scope.kind}
    if scope.kind == "EXPLICIT_DATE_RANGE":
        return TimeScope(
            **common,
            start_inclusive=scope.start_inclusive,
            end_exclusive=scope.end_exclusive,
        )
    if scope.kind == "EXPLICIT_YEAR":
        return TimeScope(**common, year=scope.year)
    if scope.kind == "EXPLICIT_MONTH":
        return TimeScope(**common, year=scope.year, month=scope.month)
    if scope.kind == "EXPLICIT_MONTH_LIST":
        return TimeScope(**common, year=scope.year, months=scope.months)
    return TimeScope(
        **common,
        relative_start=scope.relative_start,
        relative_end=scope.relative_end,
    )


def _canonical_grouping(group_by: list[GroupBy]) -> list[GroupBy]:
    """Use stable year-month identity for any model-proposed monthly grouping."""
    result: list[GroupBy] = []
    for item in group_by:
        if item.derivation == "MONTH":
            result.append(
                GroupBy(field=item.field, derivation="YEAR_MONTH")
            )
        else:
            result.append(item)
    return result


def canonicalize_intent(intent: SemanticQueryIntentV244) -> SemanticQueryIntentV244:
    data = intent.model_dump()

    if intent.ambiguities or intent.unsupported_reasons:
        data.update(
            {
                "result_fields": [],
                "measures": [],
                "time_scope": None,
                "derived_calendar_filters": [],
                "calendar_predicate_filters": [],
                "scalar_conditions": [],
                "group_by": [],
                "order_by": [],
                "limit": None,
            }
        )
        return SemanticQueryIntentV244.model_validate(data)

    data["time_scope"] = (
        _canonical_scope(intent.time_scope).model_dump()
        if intent.time_scope is not None
        else None
    )
    data["group_by"] = [item.model_dump() for item in _canonical_grouping(intent.group_by)]
    return SemanticQueryIntentV244.model_validate(data)


def _normalization_preflight(intent: SemanticQueryIntentV244) -> list[str]:
    errors = scope_shape_errors(intent.time_scope)
    scope = intent.time_scope
    if scope is None:
        return errors
    if scope.kind == "RELATIVE_RANGE":
        if scope.relative_start is None:
            errors.append("TIME_SCOPE_MISSING_FIELD:RELATIVE_RANGE:relative_start")
        if scope.relative_end is None:
            errors.append("TIME_SCOPE_MISSING_FIELD:RELATIVE_RANGE:relative_end")
    return sorted(set(errors))


def _safe_normalize(intent: SemanticQueryIntentV244) -> tuple[dict[str, Any] | None, str | None]:
    errors = _normalization_preflight(intent)
    missing = [x for x in errors if "TIME_SCOPE_MISSING_FIELD" in x]
    if missing:
        return None, ";".join(missing)
    try:
        return normalize_time_scope(intent.time_scope), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:240]}"


def _semantic_differences(
    case: dict[str, Any],
    cats: list[str],
    intent: SemanticQueryIntentV244,
    normalized: dict[str, Any] | None,
    normalization_error: str | None,
) -> list[str]:
    expected = case["expected"]
    diff: list[str] = []

    if sorted(cats) != sorted(expected.get("capabilities", [])):
        diff.append("CAPABILITY_SCOPE_MISMATCH")
    if result_mode(intent) != expected.get("result_mode", result_mode(intent)):
        diff.append("RESULT_MODE_MISMATCH")
    if sorted(intent.result_fields) != sorted(expected.get("result_fields", [])):
        diff.append("RESULT_FIELDS_MISMATCH")
    if sorted((x.field, x.aggregation) for x in intent.measures) != sorted(
        (x["field"], x["aggregation"]) for x in expected.get("measures", [])
    ):
        diff.append("MEASURE_MISMATCH")
    if sorted((x.field, x.derivation) for x in intent.group_by) != sorted(
        (x["field"], x.get("derivation")) for x in expected.get("group_by", [])
    ):
        diff.append("GROUP_BY_MISMATCH")
    if sorted((x.field, x.derivation, x.direction) for x in intent.order_by) != sorted(
        (x["field"], x.get("derivation"), x["direction"])
        for x in expected.get("order_by", [])
    ):
        diff.append("ORDER_BY_MISMATCH")
    if intent.limit != expected.get("limit"):
        diff.append("LIMIT_MISMATCH")
    if derived_answerability(intent) != expected.get(
        "answerability", "UNDERSTOOD_AND_EXECUTABLE"
    ):
        diff.append("ANSWERABILITY_MISMATCH")

    if expected.get("relative_required") and (
        not intent.time_scope or intent.time_scope.kind != "RELATIVE_RANGE"
    ):
        diff.append("RELATIVE_INTENT_NOT_SYMBOLIC")

    expected_ranges = expected.get("normalized_ranges", [])
    actual_ranges = []
    if normalized is not None and "periods" not in normalized:
        actual_ranges = [normalized]
    if normalization_error:
        diff.append("NORMALIZATION_ERROR")
    if sorted(
        (x["field"], x["start_inclusive"], x["end_exclusive"])
        for x in actual_ranges
    ) != sorted(
        (x["field"], x["start_inclusive"], x["end_exclusive"])
        for x in expected_ranges
    ):
        diff.append("RANGE_MISMATCH")

    actual_derived = sorted(
        (x.field, x.derivation, x.operator, str(x.value), tuple(map(str, x.values)))
        for x in intent.derived_calendar_filters
    )
    expected_derived = sorted(
        (
            x["field"],
            x["derivation"],
            x["operator"],
            str(x.get("value")),
            tuple(map(str, x.get("values", []))),
        )
        for x in expected.get("derived_conditions", [])
    )
    if actual_derived != expected_derived:
        diff.append("DERIVED_CONDITION_MISMATCH")

    actual_calendar = sorted(
        (x.field, x.predicate) for x in intent.calendar_predicate_filters
    )
    expected_calendar = sorted(
        (x["field"], x["predicate"])
        for x in expected.get("calendar_conditions", [])
    )
    if actual_calendar != expected_calendar:
        diff.append("CALENDAR_CONDITION_MISMATCH")

    diff.extend(scope_shape_errors(intent.time_scope))
    diff.extend(validate_operations(cats, intent))
    return sorted(set(diff))


def run(cases: list[dict[str, Any]], repetitions: int, output: Path, model_name: str) -> None:
    model = OpenAIStructuredModel(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model=model_name,
        timeout_seconds=60,
        max_retries=0,
        max_output_tokens=4096,
    )
    output.mkdir(parents=True, exist_ok=False)
    descriptions = {k: v["description"] for k, v in CAPABILITIES.items()}
    rows: list[dict[str, Any]] = []

    for case in cases:
        for repetition in range(1, repetitions + 1):
            started = time.monotonic()
            row: dict[str, Any] = {
                "attempt_id": str(uuid.uuid4()),
                "question_id": case["id"],
                "question": case["question"],
                "repetition": repetition,
            }
            try:
                scope = model.parse(
                    purpose=SCOPE_PROMPT_V245,
                    instructions=(
                        "Capability catalog: "
                        + json.dumps(descriptions, ensure_ascii=False)
                        + "\nQuestion: "
                        + case["question"]
                    ),
                    output_model=ScopeSelectionV243,
                )
                cats = capabilities(scope)
                catalog = scoped_catalog(cats)
                row.update(
                    {
                        "scope": scope.model_dump(mode="json"),
                        "capabilities": cats,
                        "scoped_fields": sorted(catalog["fields"]),
                    }
                )

                raw_intent = model.parse(
                    purpose=INTENT_PROMPT_V245,
                    instructions=(
                        "Provider temporal context: "
                        + json.dumps(
                            {
                                "source_current_date": SOURCE_DATE.isoformat(),
                                "source_timezone": SOURCE_TIMEZONE,
                            }
                        )
                        + "\nType capabilities: "
                        + json.dumps(TYPE_CAPABILITIES)
                        + "\nScoped conceptual fields: "
                        + json.dumps(catalog["fields"], ensure_ascii=False)
                        + "\nDefault result fields are platform metadata and MUST NOT be copied unless explicitly named: "
                        + json.dumps(catalog["default_result_fields"], ensure_ascii=False)
                        + "\nQuestion: "
                        + case["question"]
                    ),
                    output_model=SemanticQueryIntentV244,
                )
                intent = canonicalize_intent(raw_intent)
                row.update(
                    {
                        "structured_output_success": True,
                        "raw_intent": raw_intent.model_dump(mode="json"),
                        "canonical_intent": intent.model_dump(mode="json"),
                        "derived_result_mode": result_mode(intent),
                        "derived_answerability": derived_answerability(intent),
                        "derived_entities": derived_entities(intent),
                        "raw_scope_shape_errors": scope_shape_errors(raw_intent.time_scope),
                        "canonical_scope_shape_errors": scope_shape_errors(intent.time_scope),
                        "field_operation_errors": validate_operations(cats, intent),
                    }
                )

                normalized, normalization_error = _safe_normalize(intent)
                row["normalized_time_scope"] = normalized
                row["normalization_error"] = normalization_error
                differences = _semantic_differences(
                    case, cats, intent, normalized, normalization_error
                )
                row["semantic_differences"] = differences
                row["semantic_success"] = not differences
                if normalization_error is None:
                    try:
                        row["eloquent_like"] = eloquent_like(intent)
                        row["render_error"] = None
                    except Exception as exc:
                        row["eloquent_like"] = None
                        row["render_error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
                else:
                    row["eloquent_like"] = None
                    row["render_error"] = "skipped because temporal normalization is invalid"
            except Exception as exc:
                row.update(
                    {
                        "structured_output_success": bool(row.get("raw_intent")),
                        "semantic_success": False,
                        "semantic_differences": [
                            model.last_failure_class or "MODEL_OR_TRANSPORT_FAILURE"
                        ],
                        "exception_class": type(exc).__name__,
                        "error": str(exc)[:300],
                    }
                )

            row["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            rows.append(row)
            print(
                json.dumps(
                    {
                        "question_id": row.get("question_id"),
                        "structured_output_success": row.get("structured_output_success"),
                        "semantic_success": row.get("semantic_success"),
                        "semantic_differences": row.get("semantic_differences"),
                        "latency_ms": row.get("latency_ms"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    (output / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    failures = Counter(
        difference
        for row in rows
        for difference in row.get("semantic_differences", [])
    )
    metrics = {
        "total": len(rows),
        "structured_output_success_rate": sum(
            bool(row.get("structured_output_success")) for row in rows
        ) / len(rows),
        "semantic_success_rate": sum(
            bool(row.get("semantic_success")) for row in rows
        ) / len(rows),
        "semantic_success_count": sum(
            bool(row.get("semantic_success")) for row in rows
        ),
        "normalization_error_rate": sum(
            bool(row.get("normalization_error")) for row in rows
        ) / len(rows),
        "failure_distribution": dict(failures),
    }
    (output / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": datetime.utcnow().isoformat() + "Z",
                "phase": "2.4.5",
                "model": model_name,
                "source_current_date": SOURCE_DATE.isoformat(),
                "source_timezone": SOURCE_TIMEZONE,
                "cases": len(cases),
                "repetitions": repetitions,
                "semantic_success_primary_gate": True,
                "mcp_executed": False,
                "sql_executed": False,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=ROOT / "evaluation/spikes/semantic_query_dsl_phase245_cases.jsonl",
    )
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    run(load_cases(args.cases), args.repetitions, args.output, args.model)


if __name__ == "__main__":
    main()
